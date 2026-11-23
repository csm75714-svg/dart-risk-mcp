"""보고서 페이지 ⑤ 분석 노트 — 틀 문구가 판정·점수 어휘를 쓰지 않는지 고정한다.

노트는 진단 결과를 정해진 틀에 채운다. 회사가 공시에 쓴 문장(원문 인용)에는
「위험」 같은 낱말이 들어올 수 있지만, 우리가 만든 틀 문장에는 없어야 한다.
"""
import re
from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "docs" / "tool" / "report.html"
SRC = PAGE.read_text(encoding="utf-8")


def _note_block() -> str:
    start = SRC.index("/* ───────────────────────── ⑤ 분석 노트")
    end = SRC.index("async function copy(text, btn)")
    return SRC[start:end]


def test_다섯째_단계가_있다():
    assert 'data-step="5"' in SRC
    assert SRC.count('data-step="5"') >= 2  # 단계 버튼 + 섹션


def test_틀_문구에_판정_어휘가_없다():
    block = _note_block()
    # 주석은 원칙을 설명하느라 금지어를 적으므로 빼고 본다
    code = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
    code = re.sub(r"//[^\n]*", "", code)
    for word in ["고위험", "위험도", "위험 등급", "가장 무거운", "의심된다", "작전", "세력", "점수:"]:
        assert word not in code, word


def test_못_받은_자료를_없다로_적지_않는다():
    block = _note_block()
    assert "받지 못했다" in block
    assert "자료가 없다는 뜻이 아님" in block
