"""공시 원문 문구 검색 — 보고서 작성 페이지(docs/tool/report.html)의 /api/grep 몸통.

/api/doc은 화면 표시용이라 앞 20,000자만 준다. 증권신고서처럼 50만 자가 넘는
문서에서는 투자위험요소 뒤쪽 문단(예: 「대표주관회사와 투자자간 이해상충 관련
위험」)이 그 창 밖에 있다. 이 함수는 **원문 전체**를 서버에서 훑고, 찾은
문장만 짧게 돌려준다 — 브라우저로 내려가는 양은 늘지 않는다.

신뢰 경계는 /api/doc과 같다.
- 키는 X-DART-Key 헤더로만 받는다(api/grep.py). 서버 키 폴백은 **없다** —
  보고서 페이지는 이용자 본인 키로만 돈다(운영자 한도를 쓰지 않는다).
- 문구·응답을 저장하거나 로그로 남기지 않는다.
"""
import re

from dart_risk_mcp.core.dart_client import (
    _decode_zip_file,
    _fetch_document_zip,
    _html_to_structured_text,
)

_RCEPT_RE = re.compile(r"^\d{14}$")

MAX_TERMS = 8           # 한 번에 찾는 문구 수
MAX_TERM_LEN = 40       # 문구 하나의 길이
MAX_HITS_PER_TERM = 5   # 문구당 돌려주는 문장 수
SNIPPET_CHARS = 420     # 문장 하나의 최대 길이

_FETCH_FAILED_MSG = (
    "DART에서 공시 원문을 받지 못했습니다. 잠시 후 다시 시도하거나 "
    "DART 원문 링크를 이용하세요."
)

# 문장 경계 — 「…다.」「…요.」 뒤 공백, 또는 줄바꿈.
_SENT_SPLIT = re.compile(r"(?<=[다요음함됨임]\.)\s+|\n+")
# 제목 줄 — 「가.」「(1)」「1.」「III.」 같은 머리 표지로 시작하는 짧은 줄.
_HEADING_RE = re.compile(
    r"^\s*(?:[IVX]+\.|[0-9]{1,2}\.|[가-하]\.|\([0-9가-하]{1,2}\)|【)[^\n]{0,80}$"
)


def parse_terms(raw: str | None) -> list[str]:
    """`q=문구1|문구2` → 정리된 문구 목록. 빈 값·중복·과다 길이는 버린다."""
    if not raw:
        return []
    out: list[str] = []
    for t in raw.split("|"):
        t = re.sub(r"\s+", " ", t).strip()
        if not t or len(t) > MAX_TERM_LEN or t in out:
            continue
        out.append(t)
        if len(out) >= MAX_TERMS:
            break
    return out


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def find_in_text(text: str, terms: list[str]) -> list[dict]:
    """원문에서 문구별로 들어 있는 문장을 찾는다.

    공시 원문은 표·줄바꿈 때문에 낱말 사이 공백이 들쭉날쭉하다
    (「채권자 지위」↔「채권자지위」). 그래서 **공백을 지운 형태끼리** 비교한다.

    반환: [{"term", "count", "hits": [{"heading", "text", "pos"}]}]
    `count`는 문장 수(잘라 내기 전). `pos`는 원문 안 비율(0~100) — 문서의
    어디쯤인지 감을 주기 위한 값이다.
    """
    lines = text.split("\n")
    sentences: list[tuple[str, str, int]] = []   # (heading, sentence, offset)
    heading = ""
    offset = 0
    for line in lines:
        stripped = line.strip()
        if stripped and _HEADING_RE.match(stripped):
            heading = stripped[:80]
        for sent in _SENT_SPLIT.split(line):
            sent = sent.strip()
            if sent:
                sentences.append((heading, sent, offset))
        offset += len(line) + 1

    total = max(len(text), 1)
    results = []
    for term in terms:
        key = _squash(term)
        hits = []
        count = 0
        for head, sent, off in sentences:
            if key and key in _squash(sent):
                count += 1
                if len(hits) < MAX_HITS_PER_TERM:
                    snippet = sent if len(sent) <= SNIPPET_CHARS else _window(sent, term)
                    hits.append({
                        "heading": head,
                        "text": snippet,
                        "pos": round(off * 100 / total),
                    })
        results.append({"term": term, "count": count, "hits": hits})
    return results


def _window(sent: str, term: str) -> str:
    """긴 문장에서 문구 주변만 잘라 낸다(앞뒤 생략은 「…」)."""
    i = sent.find(term)
    if i < 0:
        i = sent.find(term.split(" ")[0])
    if i < 0:
        return sent[:SNIPPET_CHARS] + "…"
    start = max(0, i - SNIPPET_CHARS // 3)
    end = min(len(sent), start + SNIPPET_CHARS)
    return ("…" if start else "") + sent[start:end] + ("…" if end < len(sent) else "")


def fetch_full_text(rcept_no: str, api_key: str) -> tuple[str, list[str]]:
    """ZIP의 HTML/XML 문서 **전부**를 이어 붙인 구조 보존 텍스트.

    `fetch_disclosure_full`은 가장 큰 파일 하나만 본다. 증권신고서·정정신고서는
    본문이 여러 파일로 나뉘는 일이 있어(정정 대비표가 따로 오는 경우) 전부 훑는다.
    """
    zf = _fetch_document_zip(rcept_no, api_key)
    if not zf:
        return "", []
    try:
        names = zf.namelist()
        docs = [n for n in names if n.lower().endswith((".xml", ".html", ".htm"))]
        docs.sort(key=lambda n: -zf.getinfo(n).file_size)
        parts = []
        for n in docs:
            raw = _decode_zip_file(zf, n)
            if raw:
                parts.append(_html_to_structured_text(raw))
        return "\n".join(parts), names
    finally:
        zf.close()


def handle_grep(query: dict, api_key: str) -> tuple[int, dict]:
    """(status, body). query 예: {"rcept_no": "...", "q": "이해상충|채권자 지위"}."""
    if not api_key:
        return 400, {"error": "X-DART-Key 헤더가 필요합니다 — 보고서 페이지에서 본인 DART 키를 입력하세요"}

    rcept_no = (query.get("rcept_no") or "").strip()
    if not _RCEPT_RE.match(rcept_no):
        return 400, {"error": "rcept_no는 14자리 숫자여야 합니다"}

    terms = parse_terms(query.get("q"))
    if not terms:
        return 400, {"error": "찾을 문구(q)가 필요합니다 — 여러 개는 |로 구분"}

    try:
        text, files = fetch_full_text(rcept_no, api_key)
    except Exception:
        return 502, {"error": _FETCH_FAILED_MSG}

    if not files:
        return 502, {"error": _FETCH_FAILED_MSG}
    if not text:
        return 404, {"error": "공시 원문을 찾을 수 없습니다"}

    return 200, {
        "rcept_no": rcept_no,
        "char_count": len(text),
        "results": find_in_text(text, terms),
    }
