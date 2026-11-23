"""보고서 페이지 — 기사 묶음 세 군데 정리 (모아라이프플러스 2026-11-23 묶음에서 나온 것).

1) 「회사가 공시에 적은 설명」에 표 머리·칸 이름·이름·숫자 줄이 실렸다 → isProse로 문장만.
   같은 말(「2. 변경사유 · 담보권실행으로 인한 변경」 ↔ 「변경 사유: 담보권실행으로 인한 변경」)은 한 번만.
2) 철회된 13회차 전환사채가 「권면총액 - · 전환가액 - · 최저조정가액 -」로 나왔다 → cbState가 이유를 밝힌다.
3) 「공시로 확인된 사실」 앞 줄들이 같은 공시를 유형마다 되풀이했다 → 같은 공시는 한 줄로 묶는다.
   제목의 칸 맞춤 공백(「기타시장안내              (…)」)과 여러 줄 보고 사유도 접는다.
아래 문자열은 전부 그 묶음에 실제로 나온 값이다.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPORT = (ROOT / "docs" / "tool" / "report.html").read_text(encoding="utf-8")
node = pytest.mark.skipif(not shutil.which("node"), reason="node 없음")


def _cut(name: str) -> str:
    for head in (f"function {name}(", f"const {name} = "):
        if head in REPORT:
            i = REPORT.index(head)
            break
    else:
        raise AssertionError(name)
    if head.startswith("const"):
        return REPORT[i:REPORT.index("\n", i)]
    depth, j = 0, REPORT.index("{", i)
    while True:
        depth += REPORT[j] == "{"
        depth -= REPORT[j] == "}"
        j += 1
        if depth == 0:
            return REPORT[i:j]


def _run(names, expr):
    code = "\n".join(_cut(n) for n in names) + f"\nconsole.log(JSON.stringify({expr}));"
    return json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout)


# ── 1) 회사 설명은 문장만 ───────────────────────────────────────────────────

DROP = [
    "3. 자금조달의 목적 · 시설자금 (원)",
    "항 목 · 정정사유 · 정 정 전 · 정 정 후",
    "윤상호 · 변경전 최대주주의 특수관계인 · 150,000 · 0.71 · 150,000 · 0.71",
    "임00 · 변경후 최대주주의 특수관계인 · 420,000 · 1.93 · 2026.11.16주주명부 기준",
    "-인수자금 조달방법 · 자기자금(원)",
]
KEEP = [
    "6.기타 투자판단에 참고할 사항 · - 주식담보대출계약에 따른 담보제공 주식의 반대대매로 최대주주 변경의 건 입니다.",
    "변경사유 · 주식담보대출계약에 따른 담보제공 주식의 반대매매",
    "회사는 운영자금으로 사용할 예정이다.",
]


@node
def test_표_머리와_데이터_줄은_회사_설명이_아니다():
    out = _run(["isProse"], json.dumps(DROP + KEEP, ensure_ascii=False) + ".map(isProse)")
    assert out == [False] * len(DROP) + [True] * len(KEEP)


@node
def test_같은_말은_한_번만():
    out = _run(["sameText"], '[sameText("2. 변경사유 · 담보권실행으로 인한 변경", "담보권실행으로 인한 변경"),'
                             ' sameText("운영자금", "채무상환자금")]')
    assert out == [True, False]


def test_팩트시트가_문장_검사와_중복_검사를_거친다():
    facts = REPORT[REPORT.index("function buildFacts("):]
    facts = facts[:facts.index("// 4) 재무")]
    assert "isProse(text)" in facts and "sameText(t, h.text)" in facts
    assert 'sameText(f.text, x.reason)' in facts   # 원문 표의 변경 사유와 문장 검색이 겹치면 하나만


# ── 2) 전환사채 철회·미기재 ────────────────────────────────────────────────

CB_NAMES = ["toNum", "fmtDe", "cbState"]
D = {
    "docs": [{"rcept_no": "20261113001253", "rcept_dt": "20261113", "report_nm": "[기재정정]주요사항보고서(전환사채권발행결정)"}],
    "deep": [{"d": {"rcept_no": "20261113001253"}, "g": {"amend": {"rows": [
        {"item": "전환사채발행결정 · 계약철회", "before": "전환사채권 발행결정", "after": "전환사채권 발행결정 철회"}]}}}],
}


@node
def test_정정으로_철회된_전환사채는_철회라고_적는다():
    out = _run(CB_NAMES, f'cbState({{bd_tm:"13", bd_fta:"-", cv_prc:"-", rcept_no:"20261113001253"}}, {json.dumps(D, ensure_ascii=False)})')
    assert out == {"note": "발행 결정 철회 (2026.11.13 정정 공시)", "withdrawn": True}


@node
def test_철회_근거가_없으면_미기재로_밝히고_없다고_하지_않는다():
    out = _run(CB_NAMES, 'cbState({bd_tm:"14", bd_fta:"-", cv_prc:"-", rcept_no:"20261201000001"}, {docs:[], deep:[]})')
    assert out["withdrawn"] is False and "원문 확인" in out["note"]


@node
def test_조건이_있으면_그대로_적는다():
    assert _run(CB_NAMES, 'cbState({bd_fta:"18,000,000,000", cv_prc:"1,719", rcept_no:"1"}, {docs:[], deep:[]})') is None


def test_세_곳_모두_같은_처리를_쓴다():
    assert "cbBundleLine(b, D)" in REPORT[REPORT.index("function articleBundle") - 3000:]
    assert REPORT.count("cbRowCells(b, D,") == 2


# ── 3) 같은 공시 되풀이·제목 공백·보고 사유 줄바꿈 ─────────────────────────

def test_유형별_사실은_같은_공시를_한_줄로_묶는다():
    facts = REPORT[REPORT.index("function buildFacts("):]
    facts = facts[:facts.index("// 2) 정정 비율")]
    assert "byDoc" in facts and "가운데 가장 최근 공시다" in facts
    assert "같은 유형 공시" not in REPORT   # 「같은 유형 23건」·「같은 유형 33건」이 한 공시에 붙던 문구


@node
def test_제목의_칸_맞춤_공백을_접는다():
    out = _run(["tidyTitle"], '["기타시장안내              (상장적격성 실질심사 관련 안내)", "[기재정정]최대주주변경               "].map(tidyTitle)')
    assert out == ["기타시장안내 (상장적격성 실질심사 관련 안내)", "[기재정정]최대주주변경"]


@node
def test_여러_줄_보고_사유를_한_줄로():
    out = _run(["tidyLines"], "tidyLines(" + json.dumps("- 반대매매에 따른 장내 매도\n- 반대매매로 인한 주식담보계약 해지", ensure_ascii=False) + ")")
    assert out == "반대매매에 따른 장내 매도 / 반대매매로 인한 주식담보계약 해지"


def test_공시_목록과_대량보유를_불러올_때_정리한다():
    assert "report_nm: tidyTitle(d.report_nm), rules: classify" in REPORT
    assert "report_resn: tidyLines(x.report_resn)" in REPORT


@node
def test_숫자로_끝나는_익명_이름에도_조사를_고른다():
    out = _run(["lastSyl", "josa", "josaRo"], '[josaRo("임00"), josa("임00","은","는"), josaRo("모아데이타"), josa("KB","은","는")]')
    assert out == ["으로", "은", "로", "은(는)"]


def test_인수자금_칸이_모두_비면_그렇게_적는다():
    assert "인수자금 조달방법 칸(자기자금·차입금·차입처·담보 내역)은 모두 비어 있다" in REPORT
