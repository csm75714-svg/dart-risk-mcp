/**
 * 사이트 비밀번호 — Vercel Routing Middleware (2026-11-23)
 *
 * 이 배포(포크)는 운영자와 운영자가 허락한 사람만 쓴다. 모든 경로(뷰어·보고서
 * 페이지·/api/*) 앞에서 HTTP Basic 인증을 요구한다. 비밀번호를 아는 사람만 들어온다.
 *
 * - 비밀번호는 코드에 두지 않는다. Vercel 환경변수 `SITE_PASSWORD`에서 읽는다.
 * - 아이디는 묻지만 검사하지 않는다(`SITE_USER`를 정하면 그것도 검사한다).
 * - ⚠ **비밀번호가 설정되지 않으면 잠근다(fail-closed).** 설정을 빠뜨린 배포가
 *   조용히 열려 버리면 「막았다」고 믿는 사람만 남는다.
 * - 브라우저는 한 번 로그인하면 같은 사이트의 fetch(/api/...)에도 자격 증명을
 *   자동으로 붙인다 — 페이지 코드는 바꿀 필요가 없다.
 */

const REALM = "DART report";

function unauthorized(message) {
  return new Response(message, {
    status: 401,
    headers: {
      "WWW-Authenticate": `Basic realm="${REALM}", charset="UTF-8"`,
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

/** "Basic base64(user:pass)" → { user, pass } | null. UTF-8 비밀번호도 읽는다. */
export function parseBasic(header) {
  if (!header || !/^Basic\s+/i.test(header)) return null;
  let decoded;
  try {
    const bin = atob(header.replace(/^Basic\s+/i, "").trim());
    decoded = new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
  } catch (e) {
    return null;
  }
  const i = decoded.indexOf(":");
  if (i < 0) return null;
  return { user: decoded.slice(0, i), pass: decoded.slice(i + 1) };
}

/** 길이에 따라 일찍 끝나지 않는 비교(타이밍으로 비밀번호를 한 글자씩 맞히는 것을 막는다). */
export function safeEqual(a, b) {
  const x = new TextEncoder().encode(String(a));
  const y = new TextEncoder().encode(String(b));
  let diff = x.length ^ y.length;
  const n = Math.max(x.length, y.length);
  for (let k = 0; k < n; k++) diff |= (x[k] || 0) ^ (y[k] || 0);
  return diff === 0;
}

export function checkAuth(header, env) {
  const password = (env.SITE_PASSWORD || "").trim();
  if (!password) return "unset";
  const cred = parseBasic(header);
  if (!cred) return "missing";
  const user = (env.SITE_USER || "").trim();
  if (user && !safeEqual(cred.user, user)) return "wrong";
  return safeEqual(cred.pass, password) ? "ok" : "wrong";
}

export default function middleware(request) {
  const verdict = checkAuth(request.headers.get("authorization"), process.env);
  if (verdict === "ok") {
    // 요청을 그대로 진행시킨다(@vercel/functions의 next()와 같은 신호).
    return new Response(null, { headers: { "x-middleware-next": "1" } });
  }
  if (verdict === "unset") {
    return new Response(
      "사이트 비밀번호가 아직 설정되지 않아 잠겨 있습니다. Vercel 프로젝트 Settings → Environment Variables에 SITE_PASSWORD를 넣고 다시 배포하세요.",
      { status: 503, headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" } },
    );
  }
  return unauthorized("비밀번호가 필요합니다.");
}
