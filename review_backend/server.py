"""HTTP API for the risk review assistant prototype.

Run:
    python -m review_backend.server --port 8787
"""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Tuple

from .ad_compliance import check_ad_compliance
from .qwen_client import extract_image_text, get_qwen_configured, get_qwen_status


ROOT_DIR = Path(__file__).resolve().parents[1]


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(body)


def _html_response(handler: BaseHTTPRequestHandler, path: Path) -> None:
    body = path.read_bytes()
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> Tuple[Dict[str, Any], str]:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}, ""
    raw = handler.rfile.read(length).decode("utf-8")
    if not raw.strip():
        return {}, raw
    return json.loads(raw), raw


class ReviewHandler(BaseHTTPRequestHandler):
    server_version = "RiskReviewBackend/0.1"

    def do_OPTIONS(self) -> None:  # noqa: N802
        _json_response(self, HTTPStatus.NO_CONTENT, {})

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/", "/compliance"}:
            _html_response(self, ROOT_DIR / "ad-compliance-agent.html")
            return
        if self.path == "/health":
            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "ok": True,
                    "qwen_configured": get_qwen_configured(),
                    "qwen": get_qwen_status(),
                    "endpoints": [
                        "GET /compliance",
                        "POST /api/ad-compliance/check",
                        "POST /api/ad-compliance/extract-image-text",
                    ],
                },
            )
            return
        _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            payload, _ = _read_json(self)
            if self.path == "/api/ad-compliance/check":
                self._check_ad_compliance(payload)
                return
            if self.path == "/api/ad-compliance/extract-image-text":
                self._extract_image_text(payload)
                return
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})
        except json.JSONDecodeError:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
        except Exception as exc:  # pragma: no cover - runtime safety for prototype API
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def _check_ad_compliance(self, payload: Dict[str, Any]) -> None:
        result = check_ad_compliance(payload)
        _json_response(self, HTTPStatus.OK, result)

    def _extract_image_text(self, payload: Dict[str, Any]) -> None:
        image_data_url = str(payload.get("imageDataUrl") or "")
        if not image_data_url:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "missing_image"})
            return
        if not get_qwen_configured():
            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "source": "manual",
                    "extracted_text": "",
                    "confidence": "low",
                    "notes": ["未配置 DEEPSEEK_API_KEY、QWEN_API_KEY 或 DASHSCOPE_API_KEY，请手动粘贴图片文字后检查。"],
                },
            )
            return
        try:
            result = extract_image_text(image_data_url)
            result.setdefault("source", "vision-model")
            _json_response(self, HTTPStatus.OK, result)
        except Exception as exc:  # pragma: no cover - external model/runtime guard
            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "source": "qwen-vision-error",
                    "extracted_text": "",
                    "confidence": "low",
                    "notes": [f"视觉模型调用失败：{exc}"],
                },
            )

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Run risk review backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), ReviewHandler)
    print(f"Risk review backend listening on http://{args.host}:{args.port}")
    print("Set DEEPSEEK_API_KEY, QWEN_API_KEY or DASHSCOPE_API_KEY to enable vision OCR.")
    server.serve_forever()


if __name__ == "__main__":
    main()
