"""보고서 페이지 — 최대주주변경 원문 표(/api/control)·대량보유 보고·원문 문장 정리.

모아라이프플러스(2026-11) 묶음에서 나온 세 가지를 고정한다.
1) 「자금 사용 목적 변경」 규칙이 [기재정정] 제목만으로 23건을 잡았다 — 제목이
   말하는 것은 「정정했다」까지라 라벨을 「자금조달 결정 정정」으로 낮췄다.
2) 「회사 설명」에 표 조각(「| 운영자금 (원) | - |」)이 그대로 실렸다 — cleanHit.
3) 새 최대주주·인수자금이 원문 표에 있는데 문장 검색으로는 칸이 흩어졌다 —
   core 파서를 그대로 부르는 /api/control과 majorstock.json(대량보유 보고).
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import tests.test_control_change_detail as fx
import tool_server.control as ctl

ROOT = Path(__file__).resolve().parents[1]
REPORT = (ROOT / "docs" / "tool" / "report.html").read_text(encoding="utf-8")


# ── /api/control ────────────────────────────────────────────────────────────

def test_키가_없으면_400이고_서버_키로_대신하지_않는다():
    status, body = ctl.handle_control({"rcept_no": "20261112900875"}, "")
    assert status == 400 and "X-DART-Key" in body["error"]
    src = (ROOT / "tool_server" / "control.py").read_text(encoding="utf-8")
    assert "DART_API_KEY" not in src and "_api_key" not in src


def test_접수번호_형식이_틀리면_400():
    assert ctl.handle_control({"rcept_no": "123"}, "k")[0] == 400


def test_원문을_못_받으면_502이고_없다고_말하지_않는다(monkeypatch):
    monkeypatch.setattr(ctl, "fetch_document_text", lambda *a, **k: "")
    status, body = ctl.handle_control({"rcept_no": "20261112900875"}, "k")
    assert status == 502 and "받지 못했습니다" in body["error"]


def test_원문_표를_칸으로_돌려준다(monkeypatch):
    monkeypatch.setattr(ctl, "fetch_document_text", lambda *a, **k: fx._ATLASLINK_TEXT)
    status, body = ctl.handle_control({"rcept_no": "20260709900615"}, "k")
    assert status == 200 and body["found"] and not body["amended"]
    assert body["new_holder"] == "미래산업 주식회사 외 4인"
    assert body["new_ratio"] == 39.16
    assert body["self_fund"] == 11191984000
    assert body["new_holder_base"] == "미래산업 주식회사"
    assert body["holder_type"] == "주식회사"


def test_정정_공시는_대비표의_정정전_값이_아니라_뒤의_본문을_읽는다():
    amend = ("정정신고(보고) 정정일자 2026-11-20 1. 정정관련 공시서류 최대주주변경 "
             "1. 변경내용 변경전 최대주주등 갑 소유비율(%) 1.00 변경후 최대주주등 을 "
             "소유비율(%) 2.00 ") + fx._ATLASLINK_TEXT
    out = ctl.parse_control_text(amend)
    assert out["amended"] is True
    assert out["new_holder"] == "미래산업 주식회사 외 4인"


def test_표가_없으면_found_False():
    assert ctl.parse_control_text("최대주주 변경을 수반하는 주식담보제공계약 체결")["found"] is False


# ── 릴레이·배포 ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", ["api/[endpoint].js", "relay/worker.js", "scripts/dev_relay.py"])
def test_대량보유_엔드포인트가_세_릴레이에_모두_있다(path):
    assert '"majorstock.json"' in (ROOT / path).read_text(encoding="utf-8")


def test_대량보유는_캐시하지_않는다():
    js = (ROOT / "api" / "[endpoint].js").read_text(encoding="utf-8")
    block = js[js.index("NO_CACHE_ENDPOINTS"):]
    block = block[:block.index("]);")]
    assert '"majorstock.json"' in block


def test_control_함수가_배포에_들어간다():
    assert (ROOT / "api" / "control.py").exists()
    ignore = (ROOT / ".vercelignore").read_text(encoding="utf-8")
    assert "!api" in ignore and "!tool_server" in ignore


# ── 보고서 페이지 ────────────────────────────────────────────────────────────

def test_자금조달_정정을_용도_변경이라_부르지_않는다():
    m = re.search(r'\{ id: "fundchange", label: "([^"]+)"', REPORT)
    assert m and m.group(1) == "자금조달 결정 정정"
    assert "자금 사용 목적 변경" not in REPORT


def _cut_fn(name: str) -> str:
    i = REPORT.index(f"function {name}(")
    depth, j = 0, REPORT.index("{", i)
    while True:
        c = REPORT[j]
        depth += c == "{"
        depth -= c == "}"
        j += 1
        if depth == 0:
            return REPORT[i:j]


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
def test_cleanHit_표_조각을_거른다():
    cases = ["| 운영자금 (원) | - |", "| - | - |", "| 1 | 2 |",
             "| 변경사유 | 주식담보대출계약에 따른 담보제공 주식의 반대매매 |",
             "회사는 운영자금으로 사용할 예정이다."]
    code = _cut_fn("cleanHit") + f"\nconsole.log(JSON.stringify({json.dumps(cases, ensure_ascii=False)}.map(cleanHit)));"
    out = json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout)
    assert out[0] is None and out[1] is None and out[2] is None
    assert out[3] == "변경사유 · 주식담보대출계약에 따른 담보제공 주식의 반대매매"
    assert out[4] == cases[4]


def test_회사_설명과_거래_구조가_cleanHit을_거친다():
    facts = REPORT[REPORT.index("function buildFacts("):]
    facts = facts[:facts.index("// 4) 재무")]
    assert "cleanHit(" in facts
    assert "cleanHit(h.text)" in REPORT[REPORT.index('$("#btnStruct").onclick'):]


def test_표를_못_읽으면_없다고_쓰지_않는다():
    assert "표가 없다는 뜻이 아니라 열지 못한 것입니다" in REPORT
    assert "내용이 없다는 뜻이 아님" in REPORT


def test_대량보유_보고자를_최대주주라_단정하지_않는다():
    assert REPORT.count("최대주주와 같은 사람이 아닐 수 있") >= 2
    assert "최대주주와 다를 수 있음" in REPORT


def test_controlDetail은_이용자_키만_보낸다():
    fn = _cut_fn("controlDetail")
    assert '"X-DART-Key": key()' in fn and "/api/control" in fn


# ── 정정 대비표 · 리픽싱 최저조정가액 (꼭 필요한 두 가지만 덧붙임) ─────────────

from tool_server.grep import MAX_AMEND_ROWS, find_amend_table  # noqa: E402

_AMEND_MD = """정정신고(보고)
| 3. 정정사유 | 납입일 변경 |
| 정 정 항 목 | 정 정 전 | 정 정 후 |
| --- | --- | --- |
| 5. 자금조달의 목적 - 운영자금 | 5,000,000,000 | 3,000,000,000 |
|  - 채무상환자금 | - | 2,000,000,000 |

본문 | 이어짐"""


def test_정정_대비표를_칸으로_읽는다():
    a = find_amend_table(_AMEND_MD)
    assert a["reason"] == "납입일 변경"
    assert a["rows"][0] == {"item": "5. 자금조달의 목적 - 운영자금", "before": "5,000,000,000", "after": "3,000,000,000"}
    assert a["total"] == 2


def test_정정전_정정후가_둘_다_없는_표는_읽지_않는다():
    assert find_amend_table("| 항목 | 정정전 |\n| a | b |")["rows"] == []


def test_정정_대비표_상한은_건수를_밝힌다():
    body = "\n".join(f"| 항목{i} | {i} | {i+1} |" for i in range(MAX_AMEND_ROWS + 5))
    a = find_amend_table("| 항목 | 정정전 | 정정후 |\n| --- | --- | --- |\n" + body)
    assert len(a["rows"]) == MAX_AMEND_ROWS and a["total"] == MAX_AMEND_ROWS + 5
    assert "행 생략" in REPORT


def test_grep_응답에_정정_대비표가_실린다(monkeypatch):
    import tool_server.grep as g
    monkeypatch.setattr(g, "fetch_full_text", lambda *a: (_AMEND_MD, ["a.xml"]))
    status, body = g.handle_grep({"rcept_no": "20261120900976", "q": "운영자금"}, "k")
    assert status == 200 and body["amend"]["total"] == 2


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
def test_최저조정가액_비율은_소수_두_자리다():
    code = (_cut_fn("toNum") + "\n" + _cut_fn("refixFloor")
            + '\nconsole.log(refixFloor({act_mktprcfl_cvprc_lwtrsprc:"1,203",cv_prc:"1,719"}));'
            + '\nconsole.log(refixFloor({cv_prc:"1,719"}));')
    out = subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout.split("\n")
    assert out[0] == "1,203원 (69.98%)" and out[1] == "-"


def test_최저조정가액은_진단_노트_묶음_세_곳에_있다():
    # 세 곳 모두 cbRowCells(진단·노트)·cbBundleLine(기사 묶음)을 거친다 — 철회·미기재 처리가 한 곳에 있다
    assert REPORT.count("cbRowCells(b, D,") == 2 and REPORT.count("cbBundleLine(b, D)") == 1
    assert "refixFloor(b)" in REPORT[REPORT.index("const cbRowCells"):REPORT.index("/* ───────────────────────── ③ 팩트시트")]
