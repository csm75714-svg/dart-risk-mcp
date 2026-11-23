"""최대주주변경 공시 원문 표 읽기 — 보고서 작성 페이지의 /api/control 몸통.

`/api/grep`은 낱말이 든 **문장**을 돌려준다. 최대주주변경 공시는 문장이 아니라
「변경전 최대주주등 · 소유주식수 · 소유비율 / 변경후 … / 변경사유 / 인수자금
조달방법(자기자금·차입금·차입처·담보)」 **표**라서 문장 검색으로는 칸이
흩어진다. 이 함수는 MCP 도구가 쓰는 core 파서(`parse_control_change_detail`)를
그대로 불러 칸을 돌려준다 — 파서를 JS로 복제하지 않는다(복제하면 core가
바뀔 때 화면만 조용히 낡는다).

정정 공시: 원문 머리에 「정정신고(보고)」가 있고 정정 대비표 뒤에 본문 전체가
다시 온다. 대비표의 「정정전」 값을 읽지 않도록 **마지막 「변경내용」부터**
파싱하고, 응답에 `amended: true`를 실어 화면이 그 사실을 밝히게 한다.

신뢰 경계는 /api/grep과 같다 — 키는 X-DART-Key 헤더로만 받고 서버 키 폴백은
없다. 원문·응답을 저장하지 않는다.
"""
import re

from dart_risk_mcp.core.dart_client import (
    _is_amended_document,
    classify_holder_type,
    fetch_document_text,
    parse_control_change_detail,
    strip_holder_suffix,
)

_RCEPT_RE = re.compile(r"^\d{14}$")
_BODY_START_RE = re.compile(r"1\.\s*변경\s*내용")
MAX_CHARS = 15000  # 정정 공시는 대비표가 앞에 붙어 본문이 뒤로 밀린다

_FETCH_FAILED_MSG = (
    "DART에서 공시 원문을 받지 못했습니다. 잠시 후 다시 시도하거나 "
    "DART 원문 링크를 이용하세요."
)


def parse_control_text(text: str) -> dict:
    """원문 텍스트 → 표 칸. 정정 공시면 마지막 본문부터 읽는다."""
    amended = _is_amended_document(text)
    body = text
    if amended:
        starts = [m.start() for m in _BODY_START_RE.finditer(text)]
        if starts:
            body = text[starts[-1]:]
    d = parse_control_change_detail(body)
    found = bool(d.get("new_holder"))
    out = {"amended": amended, "found": found, **d}
    if found:
        out["new_holder_base"] = strip_holder_suffix(d["new_holder"])
        out["holder_type"] = classify_holder_type(d["new_holder"])
    return out


def handle_control(query: dict, api_key: str) -> tuple[int, dict]:
    """(status, body). query 예: {"rcept_no": "20261112900875"}."""
    if not api_key:
        return 400, {"error": "X-DART-Key 헤더가 필요합니다 — 보고서 페이지에서 본인 DART 키를 입력하세요"}
    rcept_no = (query.get("rcept_no") or "").strip()
    if not _RCEPT_RE.match(rcept_no):
        return 400, {"error": "rcept_no는 14자리 숫자여야 합니다"}
    try:
        text = fetch_document_text(rcept_no, api_key, max_chars=MAX_CHARS)
    except Exception:
        return 502, {"error": _FETCH_FAILED_MSG}
    if not text:
        return 502, {"error": _FETCH_FAILED_MSG}
    return 200, {"rcept_no": rcept_no, **parse_control_text(text)}
