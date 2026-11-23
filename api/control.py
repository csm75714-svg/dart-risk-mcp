"""Vercel Python 함수 진입점 — 보고서 페이지 최대주주변경 원문 표 읽기(/api/control).

api/doc.py와 같은 원칙(얇은 껍데기 · import 실패 보고)이고 다른 점은 하나다:
**서버 키 폴백이 없다.** 보고서 페이지는 이용자 본인 키로만 돈다.

계약:
- GET /api/control?rcept_no=<14자리>
- DART 키는 X-DART-Key 헤더로만 받는다.
"""
import json
import os
import platform
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qsl, urlsplit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_IMPORT_ERROR = ""
try:
    from tool_server.control import handle_control  # noqa: E402
except Exception as exc:  # noqa: BLE001 — 어떤 import 실패든 보고 대상이다
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-DART-Key",
    "Access-Control-Max-Age": "86400",
}


def _send_json(rh: BaseHTTPRequestHandler, status: int, body: dict) -> None:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    rh.send_response(status)
    rh.send_header("Content-Type", "application/json; charset=utf-8")
    rh.send_header("Content-Length", str(len(payload)))
    for k, v in _CORS_HEADERS.items():
        rh.send_header(k, v)
    # 키가 URL에 없고 원문은 불변 공개 데이터라 같은 접수번호는
    # 공유 캐시해도 안전하다.
    rh.send_header("Cache-Control", "public, s-maxage=86400" if status == 200 else "no-store")
    rh.end_headers()
    rh.wfile.write(payload)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):  # noqa: N802 - Vercel 규약
        self.send_response(204)
        for k, v in _CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):  # noqa: N802 - Vercel 규약
        if _IMPORT_ERROR:
            _send_json(self, 500, {
                "error": "서버 초기화에 실패했습니다",
                "detail": _IMPORT_ERROR,
                "python": platform.python_version(),
            })
            return
        try:
            query = dict(parse_qsl(urlsplit(self.path).query))
            api_key = (self.headers.get("X-DART-Key") or "").strip()
            status, body = handle_control(query, api_key)
        except Exception:
            status, body = 500, {"error": "서버 오류가 발생했습니다"}
        _send_json(self, status, body)
