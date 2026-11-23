"""tool_server.grep — 보고서 페이지 원문 문구 검색 몸통의 단위 테스트.

DART 호출(fetch_full_text)은 모킹한다. 실패 분기는 /api/doc과 같다:
파일 없음=502(못 받음), 텍스트 없음=404(원문 없음).
"""
import tool_server.grep as grep_mod
from tool_server.grep import (
    MAX_HITS_PER_TERM,
    MAX_TERMS,
    find_in_text,
    handle_grep,
    parse_terms,
)

RCEPT = "20260619001880"

# 센서뷰 정정 증권신고서(2026-06-19) 「머.」 문단을 줄인 픽스처.
SAMPLE = (
    "III. 투자위험요소\n"
    "머. 대표주관회사와 투자자간 이해상충 관련 위험\n"
    "당사는 금번 유상증자 이전 대표주관회사인 (주)상상인증권을 인수인으로 하여 "
    "80억원 규모의 무보증 사모사채를 발행한 바 있습니다. 이에 따라 대표주관회사인 "
    "(주)상상인증권이 당사의 채권자지위를 보유하고 있다는 점에서 경제적 이해상충 "
    "가능성이 제기될 수 있습니다.\n"
    "기타 투자위험\n"
)


def test_키가_없으면_400():
    status, body = handle_grep({"rcept_no": RCEPT, "q": "이해상충"}, "")
    assert status == 400 and "X-DART-Key" in body["error"]


def test_접수번호가_틀리면_400():
    status, _ = handle_grep({"rcept_no": "123", "q": "이해상충"}, "k")
    assert status == 400


def test_문구가_없으면_400():
    status, body = handle_grep({"rcept_no": RCEPT, "q": " | "}, "k")
    assert status == 400 and "q" in body["error"]


def test_못_받으면_502(monkeypatch):
    monkeypatch.setattr(grep_mod, "fetch_full_text", lambda *a: ("", []))
    status, _ = handle_grep({"rcept_no": RCEPT, "q": "이해상충"}, "k")
    assert status == 502


def test_예외도_502(monkeypatch):
    def boom(*a):
        raise RuntimeError("net")
    monkeypatch.setattr(grep_mod, "fetch_full_text", boom)
    status, _ = handle_grep({"rcept_no": RCEPT, "q": "이해상충"}, "k")
    assert status == 502


def test_본문이_비면_404(monkeypatch):
    monkeypatch.setattr(grep_mod, "fetch_full_text", lambda *a: ("", ["a.xml"]))
    status, _ = handle_grep({"rcept_no": RCEPT, "q": "이해상충"}, "k")
    assert status == 404


def test_찾은_문장과_제목을_돌려준다(monkeypatch):
    monkeypatch.setattr(grep_mod, "fetch_full_text", lambda *a: (SAMPLE, ["a.xml"]))
    status, body = handle_grep({"rcept_no": RCEPT, "q": "채권자 지위|재작성"}, "k")
    assert status == 200
    hit, miss = body["results"]
    # 원문은 「채권자지위」(붙여 씀) — 공백을 무시하고 찾아야 한다.
    assert hit["count"] == 1
    assert "상상인증권" in hit["hits"][0]["text"]
    assert hit["hits"][0]["heading"].startswith("머.")
    # 없는 문구는 0건으로 돌려준다(빠뜨리지 않는다).
    assert miss == {"term": "재작성", "count": 0, "hits": []}


def test_문구_정리():
    raw = "|".join(["이해상충", "이해상충", "", "x" * 41] + [f"t{i}" for i in range(20)])
    terms = parse_terms(raw)
    assert terms[0] == "이해상충" and terms.count("이해상충") == 1
    assert "x" * 41 not in terms
    assert len(terms) == MAX_TERMS


def test_문장_수는_세되_돌려주는_건_상한까지():
    text = "\n".join(f"{i}번째 문장에 재작성이 있습니다." for i in range(12))
    (r,) = find_in_text(text, ["재작성"])
    assert r["count"] == 12
    assert len(r["hits"]) == MAX_HITS_PER_TERM
