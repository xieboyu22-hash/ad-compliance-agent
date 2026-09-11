"""Qwen-compatible LLM client for the risk review assistant.

This module uses the OpenAI-compatible DashScope HTTP API with only Python's
standard library, so the prototype can run without installing extra packages.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_MODEL = "qwen-plus"
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
ENV_LOADED = False


def load_env(path: str | Path = ".env") -> None:
    """Load simple KEY=value pairs from a local .env file if present."""

    global ENV_LOADED
    if ENV_LOADED:
        return
    ENV_LOADED = True
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get_qwen_configured() -> bool:
    load_env()
    return bool(os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY"))


def get_qwen_status() -> Dict[str, Any]:
    load_env()
    api_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    return {
        "configured": bool(api_key),
        "model": os.getenv("QWEN_MODEL", DEFAULT_MODEL),
        "base_url": os.getenv("QWEN_BASE_URL", DEFAULT_BASE_URL),
        "temperature": float(os.getenv("QWEN_TEMPERATURE", "0.2")),
    }


def _chat_completion(messages: List[Dict[str, Any]], model: Optional[str] = None) -> str:
    load_env()
    api_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("QWEN_API_KEY or DASHSCOPE_API_KEY is not configured")

    base_url = os.getenv("QWEN_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    payload = {
        "model": model or os.getenv("QWEN_MODEL", DEFAULT_MODEL),
        "messages": messages,
        "temperature": float(os.getenv("QWEN_TEMPERATURE", "0.2")),
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Qwen HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Qwen request failed: {exc.reason}") from exc

    return data["choices"][0]["message"]["content"] or ""


def extract_image_text(image_data_url: str) -> Dict[str, Any]:
    """Extract marketing copy from a poster image with a Qwen vision model."""

    if not image_data_url.startswith("data:image/"):
        raise ValueError("imageDataUrl must be a data:image/* URL")

    content = _chat_completion(
        [
            {
                "role": "system",
                "content": (
                    "你是广告海报 OCR 助手。只提取图片中可见文字，不做合规判断。"
                    "按阅读顺序输出，保留价格、日期、活动规则、角标和免责声明。"
                    "如果文字模糊或无法辨认，明确写出无法辨认的位置。只返回 JSON。"
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "task": "提取这张广告海报中的所有可见文字",
                                "output_schema": {
                                    "extracted_text": "string",
                                    "confidence": "high | medium | low",
                                    "notes": ["string"],
                                },
                            },
                            ensure_ascii=False,
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            },
        ],
        model=os.getenv("QWEN_VISION_MODEL", "qwen-vl-plus"),
    )
    data = _extract_json(content)
    return {
        "extracted_text": str(data.get("extracted_text") or "").strip(),
        "confidence": str(data.get("confidence") or "medium"),
        "notes": data.get("notes") if isinstance(data.get("notes"), list) else [],
    }


def _extract_json(text: str) -> Dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end >= start:
        stripped = stripped[start : end + 1]
    return json.loads(stripped)


def generate_review_items(
    document_text: str,
    review_rules: Optional[str] = None,
    max_items: int = 7,
) -> List[Dict[str, Any]]:
    """Generate high/low risk review items with Qwen."""

    system = (
        "你是项目申报书审查助手。请根据审查规则和正文内容输出修改项。"
        "要求：先输出高风险，再输出低风险；不要输出评分、分数、加分。"
        "只返回 JSON，不要解释。"
    )
    user = {
        "review_rules": review_rules or "按项目申报材料质量、证据充分性、结构清晰度进行高低风险审查。",
        "document_text": document_text[:12000],
        "max_items": max_items,
        "output_schema": {
            "items": [
                {
                    "id": "string",
                    "priority": "high | low",
                    "title": "string",
                    "issue": "string",
                    "suggestion": "string",
                    "target_section": "string",
                }
            ]
        },
    }
    content = _chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ]
    )
    data = _extract_json(content)
    items = data.get("items", [])
    if not isinstance(items, list):
        raise ValueError("Qwen response field 'items' must be a list")
    return items


def generate_fix(item: Dict[str, Any], document_text: str = "") -> Dict[str, Any]:
    """Generate a one-click fix suggestion with Qwen."""

    system = (
        "你是项目申报书修改助手。请根据修改项生成可直接插入或替换的内容。"
        "不要输出评分或加分，只说明本轮已处理的风险。只返回 JSON。"
    )
    user = {
        "item": item,
        "document_text": document_text[:8000],
        "output_schema": {
            "status": "fixed",
            "summary": "string",
            "revised_text": "string",
        },
    }
    content = _chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ]
    )
    data = _extract_json(content)
    return {
        "status": data.get("status", "fixed"),
        "summary": data.get("summary", "已完成本轮风险项处理。"),
        "revised_text": data.get("revised_text", ""),
    }


def polish_workflow_with_qwen(workflow: Dict[str, Any], max_items: int = 6) -> Dict[str, Any]:
    """Ask Qwen to refine deterministic workflow results as an expert reviewer."""

    system = (
        "你是数据要素×大赛申报书写作专家，擅长根据评分细则梳理申报书逻辑、"
        "目录结构、证据链和正式但不生硬的中文行文。请避免AI味，不编造事实。"
        "硬性规则：只能使用输入workflow中的原文事实、目录和证据线索；不得虚构附件编号、政府认证、审计报告、协议、推荐函、"
        "获奖、审批通过、第三方机构名称或任何原文未给出的事实。缺证据时必须写“待补充证据”。"
        "必须保留高风险和低风险两类输出，先高风险后低风险。只返回JSON，不要解释。"
    )
    user = {
        "task": "基于确定性解析结果，优化材料准备、目录生成、内容编制、原文对比和skill优化建议。",
        "workflow": workflow,
        "max_items": max_items,
        "style_rules": [
            "先指出最该改的高风险项，再给低风险项",
            "按问题-数据-机制-成效-证据组织改写建议",
            "不输出评分、分数、加分",
            "不编造事实，缺证据时标注待补充证据",
            "不要发明附件编号、审计报告、政府认证、推荐函、第三方机构或协议名称",
            "draft必须像申报书正文，不要写咨询口吻的“建议在……中补充”开头",
            "每条draft尽量引用不同的原文事实，避免所有条目重复同一个规模数据",
        ],
        "output_schema": {
            "expert_summary": "string",
            "risk_items": [
                {
                    "id": "string",
                    "priority": "high | low",
                    "target_section": "string",
                    "title": "string",
                    "issue": "string",
                    "suggestion": "string",
                    "draft": "string",
                }
            ],
            "outline_advice": ["string"],
            "comparison_notes": ["string"],
            "skill_optimization": ["string"],
        },
    }
    content = _chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)[:50000]},
        ]
    )
    return _extract_json(content)
