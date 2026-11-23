"""사이트 비밀번호 미들웨어(middleware.js) — node로 직접 돌려 동작을 고정한다.

배포가 비밀번호 없이 열려 버리는 경로 셋을 막는다:
① 미들웨어 파일이 .vercelignore에 걸려 배포에서 빠지는 것
② SITE_PASSWORD를 빠뜨렸는데 열리는 것(fail-closed여야 한다)
③ 틀린 비밀번호·형식이 깨진 헤더가 통과하는 것
"""
import json
import pathlib
import shutil
import subprocess
import tempfile

import pytest

ROOT = pathlib.Path(__file__).parent.parent
NODE = shutil.which("node")

_HARNESS = r"""
const mod = await import(process.argv[2]);
const cases = JSON.parse(process.argv[3]);
const out = [];
for (const c of cases) {
  for (const k of ["SITE_PASSWORD", "SITE_USER"]) delete process.env[k];
  Object.assign(process.env, c.env);
  const headers = new Headers();
  if (c.auth !== null) headers.set("authorization", c.auth);
  const r = mod.default(new Request("https://x.test/report.html", { headers }));
  out.push({ status: r.status, next: r.headers.get("x-middleware-next"),
             www: r.headers.get("www-authenticate") });
}
console.log(JSON.stringify(out));
"""


def _b(user, pw):
    import base64
    return "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()


@pytest.mark.skipif(not NODE, reason="node 없음")
def test_미들웨어_동작():
    cases = [
        {"env": {}, "auth": None},                                   # 0 비밀번호 미설정 → 잠금
        {"env": {}, "auth": _b("a", "x")},                           # 1 미설정이면 무엇을 줘도 잠금
        {"env": {"SITE_PASSWORD": "pw1"}, "auth": None},             # 2 헤더 없음 → 401
        {"env": {"SITE_PASSWORD": "pw1"}, "auth": _b("누구", "pw1")},  # 3 맞음 → 통과(아이디 무관)
        {"env": {"SITE_PASSWORD": "pw1"}, "auth": _b("a", "pw2")},   # 4 틀림 → 401
        {"env": {"SITE_PASSWORD": "pw1"}, "auth": "Basic !!!"},      # 5 깨진 헤더 → 401
        {"env": {"SITE_PASSWORD": "pw1"}, "auth": "Bearer pw1"},     # 6 다른 방식 → 401
        {"env": {"SITE_PASSWORD": "pw1", "SITE_USER": "me"}, "auth": _b("you", "pw1")},  # 7 아이디 지정 시 검사
        {"env": {"SITE_PASSWORD": "비번한글"}, "auth": _b("a", "비번한글")},  # 8 UTF-8 비밀번호
        {"env": {"SITE_PASSWORD": "pw1"}, "auth": _b("a", "pw1x")},  # 9 접두 일치는 통과 못 함
    ]
    with tempfile.TemporaryDirectory() as d:
        mjs = pathlib.Path(d) / "mw.mjs"
        shutil.copy(ROOT / "middleware.js", mjs)
        h = pathlib.Path(d) / "h.mjs"
        h.write_text(_HARNESS, encoding="utf-8")
        r = subprocess.run([NODE, str(h), mjs.as_uri(), json.dumps(cases)],
                           capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    st = [o["status"] for o in out]
    assert st == [503, 503, 401, 200, 401, 401, 401, 401, 200, 401]
    assert out[3]["next"] == "1" and out[8]["next"] == "1"
    assert all(o["next"] is None for i, o in enumerate(out) if i not in (3, 8))
    assert "Basic" in out[2]["www"]


def test_미들웨어가_배포에서_빠지지_않는다():
    lines = (ROOT / ".vercelignore").read_text(encoding="utf-8").splitlines()
    assert "/*" in lines
    assert "!middleware.js" in lines
    assert lines.index("!middleware.js") > lines.index("/*")


def test_비밀번호를_코드에_두지_않는다():
    src = (ROOT / "middleware.js").read_text(encoding="utf-8")
    assert "process.env" in src and "SITE_PASSWORD" in src
