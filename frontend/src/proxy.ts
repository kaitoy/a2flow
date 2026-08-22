/**
 * @module proxy — Next.js proxy: backend API forwarding plus a session-cookie
 * route guard. Always runs on the Node.js runtime (Next.js forbids
 * configuring otherwise for this file).
 *
 * `/api/*` and `/openapi.json` are rewritten to `BACKEND_BASE_URL`, read from
 * `process.env` when this module loads (container/process start), not baked
 * in at build time — this is what makes `BACKEND_BASE_URL` configurable via
 * `compose.yml`'s `frontend.environment` without rebuilding the image. Every
 * other path is gated on the HttpOnly session cookie's presence (not
 * validity); the `AuthProvider` then confirms the session with `/auth/me`
 * and the axios 401 interceptor handles sessions that turn out to be
 * invalid.
 */
import { type NextRequest, NextResponse } from "next/server";

/** Name of the HttpOnly session cookie set by the backend at login. */
const SESSION_COOKIE_NAME = "a2flow_session";

/**
 * Backend origin `/api/*` and `/openapi.json` are proxied to. Keeping the
 * browser on the frontend origin makes the auth cookies same-origin, so
 * `HttpOnly` + `SameSite=Lax` work as intended.
 */
const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL ?? "http://localhost:8000";

/**
 * Builds the backend destination for an `/api/*` or `/openapi.json` request,
 * preserving path and query string.
 *
 * @param pathname - Incoming request pathname, e.g. `/api/v1/agent`.
 * @param search - Incoming request query string, including leading `?` if present.
 * @param backendBaseUrl - Backend origin to rewrite to.
 * @returns The absolute destination URL.
 */
export function buildBackendRewriteUrl(
  pathname: string,
  search: string,
  backendBaseUrl: string
): URL {
  return new URL(`${pathname}${search}`, backendBaseUrl);
}

/**
 * Proxies `/api/*` and `/openapi.json` to the backend, and redirects
 * unauthenticated visitors to `/login` and authenticated visitors away
 * from `/login` for every other path.
 *
 * @param request - The incoming request.
 * @returns A rewrite or redirect response, or `NextResponse.next()` to continue.
 */
export function proxy(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;

  if (pathname.startsWith("/api/") || pathname === "/openapi.json") {
    return NextResponse.rewrite(
      buildBackendRewriteUrl(pathname, request.nextUrl.search, BACKEND_BASE_URL)
    );
  }

  const hasSession = request.cookies.has(SESSION_COOKIE_NAME);
  const isLogin = pathname === "/login";

  if (!hasSession && !isLogin) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }
  if (hasSession && isLogin) {
    const url = request.nextUrl.clone();
    url.pathname = "/sessions/new";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    // App pages: gate on session-cookie presence. Excludes Next internals,
    // static assets, and (handled above instead) /api/* and /openapi.json.
    "/((?!api|_next/static|_next/image|favicon.ico|.*\\..*).*)",
    // Backend API + generated OpenAPI doc: proxied to BACKEND_BASE_URL.
    "/api/:path*",
    "/openapi.json",
  ],
};
