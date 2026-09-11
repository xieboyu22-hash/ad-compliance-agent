"""Deterministic ad compliance checker for consumer marketing materials."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence


@dataclass(frozen=True)
class Rule:
    rule_id: str
    name: str
    requirement: str

    @property
    def label(self) -> str:
        return f"{self.rule_id} {self.name}"


RULES: Dict[str, Rule] = {
    "A-01": Rule("A-01", "绝对化用语", "禁止“最佳、第一、唯一、100%”等无法证明的绝对化表述。"),
    "A-02": Rule("A-02", "数据宣传", "数据必须有来源、统计口径和时间范围。"),
    "A-03": Rule("A-03", "优惠有效期", "折扣、满减、赠品等必须写明起止日期。"),
    "A-04": Rule("A-04", "优惠限制", "必须披露适用商品/渠道、名额、叠加限制等主要条件。"),
    "A-05": Rule("A-05", "效果承诺", "不得承诺未经验证的健康、美容、性能或收益效果。"),
    "A-06": Rule("A-06", "敏感词", "“治疗、治愈、无副作用、零风险、稳赚”等必须拦截并人工复核。"),
    "A-07": Rule("A-07", "对比贬损", "不得贬损竞品或作无法证明的全面优越比较。"),
    "A-08": Rule("A-08", "免费/零元", "有押金、运费、自动续费等必要费用时必须显著披露。"),
    "A-09": Rule("A-09", "背书评价", "用户评价、专家/机构背书需有真实性与授权依据。"),
    "A-10": Rule("A-10", "证据不足", "图片文字模糊、截图不全时，不得判定完整合规，应要求原文件或完整页面。"),
}


ABSOLUTE_TERMS = [
    "最佳",
    "最好",
    "最强",
    "最高级",
    "顶级",
    "极致",
    "第一",
    "全国第一",
    "全网第一",
    "行业第一",
    "唯一",
    "首个",
    "首选",
    "100%",
    "百分百",
    "永久",
    "永不",
]

DISCOUNT_PATTERNS = [
    r"\d+\s*折",
    r"满\s*\d+\s*减\s*\d+",
    r"立减\s*\d+",
    r"直降\s*\d+",
    r"买一送一",
    r"赠品",
    r"送\s*\d+",
    r"限时",
    r"限量",
    r"优惠",
    r"特价",
]

SENSITIVE_TERMS = [
    "治疗",
    "治愈",
    "根治",
    "药到病除",
    "无副作用",
    "零风险",
    "稳赚",
    "保本",
    "包赚",
    "躺赚",
    "无风险",
]

EFFECT_TERMS = [
    "见效",
    "有效",
    "改善",
    "修复",
    "逆龄",
    "抗衰",
    "美白",
    "祛斑",
    "瘦身",
    "减脂",
    "降脂",
    "降糖",
    "提升免疫",
    "收益",
    "回报",
    "转化率",
    "性能提升",
]

PROMISE_TERMS = [
    "保证",
    "承诺",
    "必",
    "一定",
    "即可",
    "立刻",
    "马上",
    "7天",
    "一周",
    "永久",
    "无效退款",
]

COMPARE_PATTERNS = [
    r"吊打",
    r"碾压",
    r"秒杀",
    r"完胜",
    r"远超",
    r"优于",
    r"超过同行",
    r"比.+更好",
    r"比.+更强",
    r"竞品.+不",
    r"同行.+不",
]

FREE_PATTERNS = [r"免费", r"零元", r"0\s*元", r"不要钱", r"白送", r"免费领取"]

ENDORSEMENT_TERMS = [
    "用户一致好评",
    "真实用户好评",
    "专家推荐",
    "专家背书",
    "权威认证",
    "机构认证",
    "官方认证",
    "达人推荐",
    "明星同款",
    "医生推荐",
    "国家级",
]


def check_ad_compliance(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Check marketing material against the provided A-01 to A-10 rules."""

    material_type = str(payload.get("materialType") or "other")
    content_text = str(payload.get("contentText") or "")
    image_notes = str(payload.get("imageNotes") or "")
    image_included = bool(payload.get("imageIncluded"))
    image_quality = str(payload.get("imageQuality") or "clear")
    custom_rules = payload.get("customRules") or []

    text = "\n".join(part.strip() for part in [content_text, image_notes] if part.strip())
    items: List[Dict[str, Any]] = []

    if not text.strip() and not image_included:
        items.append(
            _item(
                risk_text="未提供可检查的宣传内容",
                risk_type="证据不足",
                rule_id="A-10",
                risk_level="无法判断",
                suggestion="请提供完整文案、原图、活动页链接截图或可识别的图片文字后再检查。",
                need_manual_review=True,
                reason="当前输入为空，无法完成第一轮合规判断。",
            )
        )
    elif image_included and not text.strip():
        items.append(
            _item(
                risk_text="已上传图片，但未提供可识别文字",
                risk_type="证据不足",
                rule_id="A-10",
                risk_level="无法判断",
                suggestion="请补充图片 OCR 文字、原始设计文件或完整页面；发布前需人工复核图片全部内容。",
                need_manual_review=True,
                reason="系统无法仅凭图片文件名判断广告语、优惠条件和免责声明是否完整。",
            )
        )

    if image_included and image_quality in {"blurred", "cropped", "blocked"}:
        quality_label = {"blurred": "图片文字模糊", "cropped": "截图不完整", "blocked": "关键信息被遮挡"}[image_quality]
        items.append(
            _item(
                risk_text=quality_label,
                risk_type="证据不足",
                rule_id="A-10",
                risk_level="无法判断",
                suggestion="请提供高清原图或完整活动页面；当前材料不得判定为完整合规。",
                need_manual_review=True,
                reason="题目规则 A-10 要求图片模糊、截图不全时应要求原文件或完整页面。",
            )
        )

    if text.strip():
        items.extend(_check_absolute_terms(text))
        items.extend(_check_data_claims(text))
        items.extend(_check_discount_validity(text))
        items.extend(_check_discount_limits(text))
        items.extend(_check_effect_promises(text))
        items.extend(_check_sensitive_terms(text))
        items.extend(_check_comparisons(text))
        items.extend(_check_free_claims(text))
        items.extend(_check_endorsements(text))
        items.extend(_check_custom_rules(text, custom_rules))

    items = _dedupe_items(items)
    items.sort(key=_sort_key)

    summary = {
        "high": sum(1 for item in items if item["risk_level"] == "高"),
        "medium": sum(1 for item in items if item["risk_level"] == "中"),
        "low": sum(1 for item in items if item["risk_level"] == "低"),
        "uncertain": sum(1 for item in items if item["risk_level"] == "无法判断"),
        "total": len(items),
    }
    manual_review_required = any(item["need_manual_review"] for item in items)
    is_compliant = not items
    publish_decision = _publish_decision(summary, is_compliant, manual_review_required)
    rule_coverage = _build_rule_coverage(items, custom_rules)
    missing_evidence = _build_missing_evidence(items)
    revision_example = _build_revision_example(text, items, material_type)

    return {
        "agent": "广告宣传材料合规检查助手",
        "material_type": material_type,
        "is_compliant": is_compliant,
        "publish_decision": publish_decision,
        "decision_reason": _decision_reason(summary, publish_decision),
        "manual_review_required": manual_review_required,
        "overall_conclusion": _overall_conclusion(summary, is_compliant, manual_review_required),
        "summary": summary,
        "rules_source": _rules_source(custom_rules),
        "rule_coverage": rule_coverage,
        "missing_evidence": missing_evidence,
        "revision_example": revision_example,
        "items": items,
    }


def _check_absolute_terms(text: str) -> List[Dict[str, Any]]:
    terms = _matching_terms(text, ABSOLUTE_TERMS)
    if not terms:
        return []
    return [
        _item(
            risk_text=_snippet(text, terms[0]),
            risk_type="绝对化用语",
            rule_id="A-01",
            risk_level="高",
            suggestion=f"删除或改写“{'、'.join(terms)}”，改为可证明、可限定范围的表达，并补充依据。",
            need_manual_review=True,
            reason="命中无法直接证明的绝对化广告表述。",
        )
    ]


def _check_data_claims(text: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    data_matches = list(re.finditer(r"\d+(?:\.\d+)?\s*(?:%|％|倍|万|元|人|天|小时|分钟|款|件|单|名)", text))
    if not data_matches:
        return items

    has_source = _contains_any(text, ["来源", "数据来自", "统计", "调研", "报告", "样本", "口径", "截至", "期间"])
    has_time = bool(re.search(r"\d{4}\s*年|\d{1,2}\s*月\s*\d{1,2}\s*日|\d{4}[-./]\d{1,2}|\d+\s*天|近\d+", text))
    if has_source and has_time:
        return items

    first_claim = _snippet(text, data_matches[0].group(0))
    missing = []
    if not has_source:
        missing.append("数据来源/统计口径")
    if not has_time:
        missing.append("时间范围")
    items.append(
        _item(
            risk_text=first_claim,
            risk_type="数据宣传",
            rule_id="A-02",
            risk_level="中",
            suggestion=f"补充{ '、'.join(missing) }；无法提供依据时删除或弱化数据表达。",
            need_manual_review=True,
            reason="文案含具体数据，但未完整说明来源、统计口径和时间范围。",
        )
    )
    return items


def _check_discount_validity(text: str) -> List[Dict[str, Any]]:
    if not _matches_any(text, DISCOUNT_PATTERNS):
        return []
    has_date_range = bool(
        re.search(r"起止|有效期|截止|截至|到期|至\s*\d{1,2}\s*月|\d{1,2}\s*月\s*\d{1,2}\s*日", text)
    )
    if has_date_range:
        return []
    return [
        _item(
            risk_text=_first_matching_snippet(text, DISCOUNT_PATTERNS),
            risk_type="优惠有效期",
            rule_id="A-03",
            risk_level="中",
            suggestion="补充优惠活动起止日期，例如“活动时间：2026年9月10日00:00至2026年9月20日23:59”。",
            need_manual_review=False,
            reason="文案出现折扣、满减、赠品或限时优惠，但未写明起止日期。",
        )
    ]


def _check_discount_limits(text: str) -> List[Dict[str, Any]]:
    if not _matches_any(text, DISCOUNT_PATTERNS):
        return []
    has_limit = _contains_any(text, ["适用", "仅限", "渠道", "门店", "商品", "名额", "库存", "数量有限", "不可叠加", "每人", "限购"])
    if has_limit:
        return []
    return [
        _item(
            risk_text=_first_matching_snippet(text, DISCOUNT_PATTERNS),
            risk_type="优惠限制披露不足",
            rule_id="A-04",
            risk_level="中",
            suggestion="补充适用商品、适用渠道、名额/库存、是否可与其他优惠叠加等主要限制条件。",
            need_manual_review=False,
            reason="文案存在优惠信息，但未披露主要适用条件或限制。",
        )
    ]


def _check_effect_promises(text: str) -> List[Dict[str, Any]]:
    hits: List[tuple[str, str]] = []
    for effect in _matching_terms(text, EFFECT_TERMS):
        around = _snippet(text, effect)
        has_promise = _contains_any(around, PROMISE_TERMS) or bool(re.search(r"\d+\s*天", around))
        if has_promise:
            hits.append((effect, around))
    if not hits:
        return []
    return [
        _item(
            risk_text=hits[0][1],
            risk_type="效果承诺",
            rule_id="A-05",
            risk_level="高",
            suggestion=f"删除“{'、'.join(hit[0] for hit in hits)}”相关确定性效果承诺，改为基于已验证证据的客观描述，并补充适用条件和验证依据。",
            need_manual_review=True,
            reason="命中健康、美容、性能或收益效果的确定性承诺。",
        )
    ]


def _check_sensitive_terms(text: str) -> List[Dict[str, Any]]:
    terms = _matching_terms(text, SENSITIVE_TERMS)
    if not terms:
        return []
    return [
        _item(
            risk_text=_snippet(text, terms[0]),
            risk_type="敏感词",
            rule_id="A-06",
            risk_level="高",
            suggestion=f"删除“{'、'.join(terms)}”等高风险表述；如确需表达，应提交资质、证明材料并人工复核。",
            need_manual_review=True,
            reason="题目规则明确要求该类词汇必须拦截并人工复核。",
        )
    ]


def _check_comparisons(text: str) -> List[Dict[str, Any]]:
    if not _matches_any(text, COMPARE_PATTERNS):
        return []
    has_evidence = _contains_any(text, ["来源", "报告", "测试", "统计", "样本", "第三方", "公证", "依据"])
    return [
        _item(
            risk_text=_first_matching_snippet(text, COMPARE_PATTERNS),
            risk_type="对比贬损",
            rule_id="A-07",
            risk_level="高" if not has_evidence else "中",
            suggestion="删除贬损竞品或全面优越比较；如需对比，应限定指标、样本、时间范围和数据来源。",
            need_manual_review=True,
            reason="文案存在竞品比较或优越性描述，需确认是否可证明且不构成贬损。",
        )
    ]


def _check_free_claims(text: str) -> List[Dict[str, Any]]:
    if not _matches_any(text, FREE_PATTERNS):
        return []
    has_fee_disclosure = _contains_any(text, ["押金", "运费", "续费", "自动续费", "手续费", "服务费", "到期", "取消"])
    if has_fee_disclosure:
        return []
    return [
        _item(
            risk_text=_first_matching_snippet(text, FREE_PATTERNS),
            risk_type="免费/零元费用披露不足",
            rule_id="A-08",
            risk_level="中",
            suggestion="如存在押金、运费、自动续费或其他必要费用，需在同屏显著披露；否则明确说明领取条件。",
            need_manual_review=True,
            reason="出现免费/零元表达，但未说明是否存在必要费用或后续收费条件。",
        )
    ]


def _check_endorsements(text: str) -> List[Dict[str, Any]]:
    has_authorization = _contains_any(text, ["授权", "真实", "可查", "证书编号", "资质", "来源", "采访", "评价原文"])
    terms = _matching_terms(text, ENDORSEMENT_TERMS)
    if not terms or has_authorization:
        return []
    return [
        _item(
            risk_text=_snippet(text, terms[0]),
            risk_type="背书评价依据不足",
            rule_id="A-09",
            risk_level="中",
            suggestion=f"补充“{'、'.join(terms)}”相关评价真实性、专家/机构资质、授权证明和可追溯来源；无法提供时删除背书表述。",
            need_manual_review=True,
            reason="用户评价、专家或机构背书未见真实性与授权依据。",
        )
    ]


def _check_custom_rules(text: str, custom_rules: Any) -> List[Dict[str, Any]]:
    if not isinstance(custom_rules, list):
        return []

    items: List[Dict[str, Any]] = []
    for index, raw_rule in enumerate(custom_rules, start=1):
        if not isinstance(raw_rule, dict):
            continue
        name = str(raw_rule.get("name") or f"自定义规则{index}").strip()
        requirement = str(raw_rule.get("requirement") or "").strip()
        risk_level = str(raw_rule.get("riskLevel") or "中").strip()
        if risk_level not in {"高", "中", "低", "无法判断"}:
            risk_level = "中"

        keywords = _split_keywords(str(raw_rule.get("keywords") or ""))
        if not name and not requirement:
            continue
        if not keywords:
            continue

        hits = [keyword for keyword in keywords if keyword and keyword in text]
        if not hits:
            continue

        rule_id = f"B-{index:02d}"
        items.append(
            {
                "risk_text": _snippet(text, hits[0]),
                "risk_type": name or "自定义业务规则",
                "rule_id": rule_id,
                "rule": f"{rule_id} {name or '自定义业务规则'}",
                "rule_requirement": requirement or f"命中自定义关键词：{'、'.join(hits)}",
                "risk_level": risk_level,
                "level_reason": _level_reason(rule_id, risk_level),
                "suggestion": "请按新增业务规则修改该表述；如规则解释或适用范围不明确，建议提交人工审核。",
                "rewrite_example": _rewrite_example(rule_id),
                "evidence_needed": _evidence_needed(rule_id),
                "need_manual_review": True,
                "manual_review_reason": _manual_review_reason(rule_id, True),
                "reason": f"命中新增规则关键词：{'、'.join(hits)}。",
            }
        )
    return items


def _item(
    *,
    risk_text: str,
    risk_type: str,
    rule_id: str,
    risk_level: str,
    suggestion: str,
    need_manual_review: bool,
    reason: str,
) -> Dict[str, Any]:
    rule = RULES[rule_id]
    return {
        "risk_text": risk_text.strip(),
        "risk_type": risk_type,
        "rule_id": rule.rule_id,
        "rule": rule.label,
        "rule_requirement": rule.requirement,
        "risk_level": risk_level,
        "level_reason": _level_reason(rule_id, risk_level),
        "suggestion": suggestion,
        "rewrite_example": _rewrite_example(rule_id),
        "evidence_needed": _evidence_needed(rule_id),
        "need_manual_review": need_manual_review,
        "manual_review_reason": _manual_review_reason(rule_id, need_manual_review),
        "reason": reason,
    }


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    return any(needle in text for needle in needles)


def _split_keywords(raw_keywords: str) -> List[str]:
    parts = re.split(r"[,，、\n;；]+", raw_keywords)
    return [part.strip() for part in parts if part.strip()]


def _matching_terms(text: str, terms: Sequence[str]) -> List[str]:
    matched = [term for term in terms if term in text]
    matched.sort(key=len, reverse=True)
    filtered: List[str] = []
    for term in matched:
        if any(term != existing and term in existing for existing in filtered):
            continue
        filtered.append(term)
    return filtered


def _matches_any(text: str, patterns: Sequence[str]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _first_matching_snippet(text: str, patterns: Sequence[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _snippet(text, match.group(0))
    return text[:80]


def _snippet(text: str, needle: str, radius: int = 24) -> str:
    index = text.find(needle)
    if index < 0:
        match = re.search(re.escape(needle), text)
        index = match.start() if match else 0
    start = max(0, index - radius)
    end = min(len(text), index + len(needle) + radius)
    snippet = text[start:end].replace("\n", " ").strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


def _dedupe_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for item in items:
        key = (item["rule_id"], item["risk_type"], item["risk_text"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _sort_key(item: Dict[str, Any]) -> tuple[int, str]:
    level_order = {"高": 0, "无法判断": 1, "中": 2, "低": 3}
    return (level_order.get(item["risk_level"], 9), item["rule_id"])


def _publish_decision(summary: Dict[str, int], is_compliant: bool, manual_review_required: bool) -> str:
    if is_compliant:
        return "可进入发布流程"
    if summary["high"]:
        return "禁止发布，修改后人工复核"
    if summary["uncertain"]:
        return "无法判断，补充材料后复核"
    if manual_review_required:
        return "建议人工复核后发布"
    return "修改后可发布"


def _decision_reason(summary: Dict[str, int], publish_decision: str) -> str:
    if summary["total"] == 0:
        return "未命中题目规则 A-01 至 A-10 的明显风险。"
    parts = []
    if summary["high"]:
        parts.append(f"高风险 {summary['high']} 条")
    if summary["uncertain"]:
        parts.append(f"无法判断 {summary['uncertain']} 条")
    if summary["medium"]:
        parts.append(f"中风险 {summary['medium']} 条")
    if summary["low"]:
        parts.append(f"低风险 {summary['low']} 条")
    return f"{publish_decision}：当前材料命中{'、'.join(parts)}。"


def _overall_conclusion(summary: Dict[str, int], is_compliant: bool, manual_review_required: bool) -> str:
    if is_compliant:
        return "未发现命中题目规则的明显风险，可进入下一发布流程。"
    if summary["high"]:
        return "存在高风险广告表述，发布前必须修改并人工审核。"
    if summary["uncertain"]:
        return "存在无法判断项，需补充原始材料或人工复核后再发布。"
    if manual_review_required:
        return "存在需人工确认的合规风险，建议复核依据材料后再发布。"
    return "存在中低风险问题，建议按规则补充信息后再发布。"


def _rules_source(custom_rules: Any) -> str:
    custom_count = len(custom_rules) if isinstance(custom_rules, list) else 0
    if custom_count:
        return f"题目截图提供的广告审核规则 A-01 至 A-10，另含 {custom_count} 条页面新增业务规则"
    return "题目截图提供的广告审核规则 A-01 至 A-10"


def _build_rule_coverage(items: List[Dict[str, Any]], custom_rules: Any) -> List[Dict[str, Any]]:
    hit_rule_ids = {item["rule_id"] for item in items}
    coverage = [
        {
            "rule_id": rule.rule_id,
            "rule": rule.label,
            "status": "命中" if rule.rule_id in hit_rule_ids else "已检查未命中",
            "requirement": rule.requirement,
        }
        for rule in RULES.values()
    ]
    if isinstance(custom_rules, list):
        for index, raw_rule in enumerate(custom_rules, start=1):
            if not isinstance(raw_rule, dict):
                continue
            name = str(raw_rule.get("name") or f"自定义规则{index}").strip()
            requirement = str(raw_rule.get("requirement") or "").strip()
            rule_id = f"B-{index:02d}"
            coverage.append(
                {
                    "rule_id": rule_id,
                    "rule": f"{rule_id} {name or '自定义业务规则'}",
                    "status": "命中" if rule_id in hit_rule_ids else "已检查未命中",
                    "requirement": requirement or "页面新增业务规则。",
                }
            )
    return coverage


def _build_missing_evidence(items: List[Dict[str, Any]]) -> List[str]:
    evidence: List[str] = []
    for item in items:
        evidence.extend(item.get("evidence_needed") or [])
    deduped: List[str] = []
    for item in evidence:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _build_revision_example(text: str, items: List[Dict[str, Any]], material_type: str) -> Dict[str, Any]:
    if not text.strip():
        return {
            "title": "完整修改实例",
            "text": "请先补充【完整宣传文案/图片 OCR 文字/活动页面截图】，再生成可发布版本。",
            "placeholders": ["完整宣传文案", "图片 OCR 文字", "活动页面截图"],
        }

    hit_rule_ids = {item["rule_id"] for item in items}
    product = _infer_product(text)
    tone = _detect_copy_tone(text, material_type)
    lines = _tone_matched_revision_lines(product, tone, hit_rule_ids, items)

    text_example = "\n".join(lines)
    return {
        "title": "完整修改实例",
        "material_type": material_type,
        "tone": tone["label"],
        "style_note": tone["note"],
        "text": text_example,
        "placeholders": _extract_placeholders(text_example),
        "usage_note": "【】中的内容需要业务方补充真实数据、证明材料或活动条件后才能发布。",
    }


def _infer_product(text: str) -> str:
    match = re.search(r"([\u4e00-\u9fa5A-Za-z0-9]{2,16})?(精华|面霜|饮品|课程|服务|会员|套装|产品|活动)", text)
    if match:
        suffix = match.group(2)
        if suffix == "活动":
            return "本次活动"
        return f"本{suffix}产品" if suffix not in {"产品", "服务", "会员"} else f"本{suffix}"
    return "本产品"


def _detect_copy_tone(text: str, material_type: str) -> Dict[str, str]:
    if material_type == "moments":
        return {"kind": "social", "label": "朋友圈文案风", "note": "保留朋友圈的轻推荐、分享感和行动提示，但避免夸张承诺与无依据背书。"}
    if material_type == "poster":
        return {"kind": "poster", "label": "海报短句口吻", "note": "保留短句卖点和活动节奏，弱化绝对化与功效承诺。"}
    if material_type == "landing_page":
        return {"kind": "landing", "label": "活动页说明口吻", "note": "保留清晰的信息层级，补齐规则、费用和证据。"}
    if _contains_any(text, ["直播", "今晚", "下单", "拍下", "直播间", "主播", "冲", "抢"]):
        return {"kind": "live", "label": "直播促销口吻", "note": "保留即时活动感和行动号召，但补齐活动条件。"}
    if _contains_any(text, ["海报", "限时", "新品", "焕新", "领取"]):
        return {"kind": "poster", "label": "海报短句口吻", "note": "保留短句卖点和活动节奏，弱化绝对化与功效承诺。"}
    if _contains_any(text, ["分享", "种草", "姐妹", "推荐", "体验"]):
        return {"kind": "social", "label": "朋友圈文案风", "note": "保留朋友圈的轻推荐、分享感和行动提示，但避免夸张承诺与无依据背书。"}
    return {"kind": "neutral", "label": "宣传说明口吻", "note": "保留原文宣传目的，改为可证明、有限定条件的表达。"}


def _tone_matched_revision_lines(
    product: str,
    tone: Dict[str, str],
    hit_rule_ids: set[str],
    items: List[Dict[str, Any]],
) -> List[str]:
    has_effect_or_data = "A-05" in hit_rule_ids or "A-02" in hit_rule_ids
    has_discount = "A-03" in hit_rule_ids or "A-04" in hit_rule_ids
    has_free = "A-08" in hit_rule_ids
    has_endorsement = "A-09" in hit_rule_ids
    has_custom = any(item["rule_id"].startswith("B-") for item in items)
    kind = tone["kind"]

    if kind == "live":
        lines = [f"今晚直播间带来{product}专场，适合【适用人群/使用场景】。"]
        if has_discount:
            lines.append("到手优惠为【优惠内容】，活动时间【开始时间】至【结束时间】，仅限【适用商品/适用渠道】，库存【名额或库存数量】，叠加规则以【叠加限制】为准。")
        if has_effect_or_data:
            lines.append("产品卖点以【数据来源/测试机构】在【统计时间范围】按【测试方法/统计口径】取得的【客观数据结论】为依据，实际体验因人而异。")
        if has_free:
            lines.append("参与前请确认【领取条件】及【运费/押金/服务费/自动续费说明】。")
        if has_endorsement:
            lines.append("涉及评价或推荐内容，以【评价来源】、【授权文件】和【资质证明】为准。")
        if has_custom:
            lines.append("原“【风险词替代表达】”请按品牌规则替换，并保留【内部审批记录】。")
        return lines

    if kind == "poster":
        lines = [f"{product}活动开启", "适合【适用人群/使用场景】"]
        if has_effect_or_data:
            lines.append("基于【数据来源/测试机构】于【统计时间范围】完成的【测试方法/统计口径】，结果为【客观数据结论】")
            lines.append("实际体验因人而异")
        else:
            lines.append("产品信息以页面说明和实物包装为准")
        if has_discount:
            lines.append("活动时间：【开始时间】至【结束时间】")
            lines.append("优惠内容：【优惠内容】；适用范围：【适用商品/适用渠道】；数量限制：【名额或库存数量】；叠加规则：【叠加限制】")
        if has_free:
            lines.append("领取条件：【领取条件】；可能费用：【运费/押金/服务费/自动续费说明】")
        if has_endorsement:
            lines.append("评价/推荐依据：【评价来源/授权文件/资质证明】")
        if has_custom:
            lines.append("品牌规则替代表达：【风险词替代表达】；审批记录：【内部审批记录】")
        return lines

    if kind == "social":
        lines = [f"最近关注到{product}，适合【适用人群/使用场景】的朋友可以了解一下。"]
        if has_effect_or_data:
            lines.append("卖点我会看【数据来源/测试机构】在【统计时间范围】按【测试方法/统计口径】得到的【客观数据结论】，具体体验还是因人而异。")
        else:
            lines.append("感兴趣的话可以先看清楚页面说明、使用方式和适用范围，再决定是否参与。")
        if has_discount:
            lines.append("这次活动是【优惠内容】，时间【开始时间】到【结束时间】，适用【适用商品/适用渠道】，名额【名额或库存数量】，叠加规则看【叠加限制】。")
        if has_free:
            lines.append("领取前记得确认【领取条件】，以及是否涉及【运费/押金/服务费/自动续费说明】。")
        if has_endorsement:
            lines.append("评价或推荐信息以【评价来源】、【授权文件】和【资质证明】为准，我这里不替大家做绝对判断。")
        if has_custom:
            lines.append("原来那句【风险词替代表达】建议换成更稳妥的说法，相关依据保留【内部审批记录】。")
        return lines

    lines = [f"{product}适用于【适用人群/使用场景】。"]
    if has_effect_or_data:
        lines.append(
            "产品相关数据或效果说明基于【数据来源/测试机构】在【统计时间范围】"
            "对【样本量】进行的【测试方法/统计口径】，结果为【客观数据结论】；实际体验因人而异。"
        )
    else:
        lines.append("产品特点请以页面披露信息、实物包装和实际体验为准。")
    if has_discount:
        lines.append(
            "活动时间为【开始时间】至【结束时间】；优惠内容为【优惠内容】；适用商品为【适用商品】；"
            "适用渠道为【适用渠道】；名额/库存为【名额或库存数量】；叠加规则为【是否可与其他优惠叠加】。"
        )
    if has_free:
        lines.append("领取或参与条件为【领取条件】，需支付费用为【运费/押金/服务费/自动续费说明】。")
    if has_endorsement:
        lines.append("用户评价来源为【评价来源】，授权证明为【授权文件】，专家/机构资质为【资质证明】。")
    if has_custom:
        lines.append("请根据新增规则确认【品牌禁用词替代表达/行业资质/内部审批记录】。")
    return lines


def _extract_placeholders(text: str) -> List[str]:
    placeholders = re.findall(r"【([^】]+)】", text)
    deduped: List[str] = []
    for placeholder in placeholders:
        if placeholder not in deduped:
            deduped.append(placeholder)
    return deduped


def _level_reason(rule_id: str, risk_level: str) -> str:
    if risk_level == "无法判断":
        return "当前材料信息不足，不能给出完整合规结论。"
    if rule_id in {"A-01", "A-05", "A-06", "A-07"}:
        return "该类表述投诉和监管关注度高，缺少证明材料时发布风险较高。"
    if risk_level == "高":
        return "该表述命中高风险规则，发布前需要修改并确认依据材料。"
    if risk_level == "中":
        return "该问题通常可通过补充披露信息、证明材料或限定条件降低风险。"
    return "该问题影响较轻，但建议在发布前一并修正。"


def _rewrite_example(rule_id: str) -> str:
    examples = {
        "A-01": "将“全网第一/100%”改为“基于【数据来源】在【统计时间范围】内的【统计口径】结果”。",
        "A-02": "将具体数据改为“据【数据来源】，【统计时间范围】内按【统计口径】统计，结果为【数据】”。",
        "A-03": "补充“活动时间：【开始时间】至【结束时间】”。",
        "A-04": "补充“适用商品：【适用商品】；适用渠道：【适用渠道】；名额：【名额】；叠加规则：【叠加限制】”。",
        "A-05": "将确定性功效改为“可帮助【客观效果】，实际体验因人而异，依据为【验证报告】”。",
        "A-06": "删除敏感词，改为客观描述；确需表达时补充【资质证明/检测报告】并人工复核。",
        "A-07": "将全面比较改为“在【测试条件】下，【具体指标】为【数据】，来源为【报告】”。",
        "A-08": "补充“是否需支付【运费/押金/服务费】；是否涉及【自动续费】；取消方式：【取消方式】”。",
        "A-09": "补充“评价来源：【评价来源】；授权证明：【授权文件】；专家/机构资质：【资质证明】”。",
        "A-10": "补充【高清原图/完整页面/图片 OCR 文字】后再判断。",
    }
    return examples.get(rule_id, "按该业务规则改写，并补充【证明材料/审批记录】。")


def _evidence_needed(rule_id: str) -> List[str]:
    evidence_map = {
        "A-01": ["绝对化表述证明依据", "限定范围说明"],
        "A-02": ["数据来源", "统计口径", "统计时间范围"],
        "A-03": ["优惠开始时间", "优惠结束时间"],
        "A-04": ["适用商品", "适用渠道", "名额或库存", "叠加限制"],
        "A-05": ["验证报告", "适用人群", "效果边界说明"],
        "A-06": ["资质证明", "检测报告", "人工审核记录"],
        "A-07": ["对比测试报告", "样本范围", "第三方依据"],
        "A-08": ["押金说明", "运费说明", "自动续费说明", "取消方式"],
        "A-09": ["评价来源", "授权证明", "专家/机构资质"],
        "A-10": ["高清原图", "完整页面", "图片 OCR 文字"],
    }
    return evidence_map.get(rule_id, ["证明材料", "审批记录"])


def _manual_review_reason(rule_id: str, need_manual_review: bool) -> str:
    if not need_manual_review:
        return "规则命中项可先由业务补充披露信息，再进入下一轮检查。"
    reasons = {
        "A-06": "题目规则明确要求敏感词必须拦截并人工复核。",
        "A-10": "当前材料不完整或不可辨识，需要人工确认原始素材。",
        "A-09": "背书评价需核验证明材料真实性与授权范围。",
        "A-05": "功效承诺需核验验证依据、适用人群和效果边界。",
    }
    return reasons.get(rule_id, "该风险需要确认依据材料或业务适用范围。")
