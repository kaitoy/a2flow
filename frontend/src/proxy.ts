/**
 * @module proxy — Next.js proxy: backend API forwarding plus a session-cookie
 * route guard. Always runs on the Node.js runtime (Next.js forbids
 * configuring otherwise for this file).
 *
 * `/api/*` and `/openapi.json` are rewritten to `BACKEND_BASE_URL`, read from
 * `process.env` when this module loads (container/process start), not baked
 * in at build time — this is what makes `BACKEND_BASE_URL` configurable via
 * `compose.yml`'s `frontend.environment` without rebuilding the image. In the
 * Docker Compose stack the browser's `/api/*` requests never reach this
 * rewrite: the `ingress` service (Envoy) routes them to the backend by path,
 * keeping long-lived SSE streams off this server. The rewrite is for runs
 * without such an ingress, e.g. `pnpm dev` against a local backend. Every
 * other path is gated on the HttpOnly session cookie's presence (not
 * validity); the `AuthProvider` then confirms the session with `/auth/me`
 * and the API client's 401 handling sends sessions that turn out to be
 * invalid back to the login page.
 */
import { type NextRequest, NextResponse } from "next/server";
import { loginPath, safeNextPath } from "@/lib/next-path";

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
 * Redirect to `target`, a path with an optional query, on the request's own
 * origin.
 */
function redirectTo(request: NextRequest, target: string): NextResponse {
  const url = request.nextUrl.clone();
  const [path, query = ""] = target.split("?", 2);
  url.pathname = path;
  url.search = query ? `?${query}` : "";
  return NextResponse.redirect(url);
}

/**
 * Proxies `/api/*` and `/openapi.json` to the backend, and redirects
 * unauthenticated visitors to `/login` -- asking it to return to the page they
 * asked for -- and authenticated visitors away from `/login` and `/signup`
 * (which are open only without a session) for every other path.
 * `/signed-out`, where signing out lands, and `/signup/verify`, where a
 * sign-up confirmation link lands in whatever browser opens it, are open to both.
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

  if (pathname === "/signed-out" || pathname === "/signup/verify") {
    return NextResponse.next();
  }

  const hasSession = request.cookies.has(SESSION_COOKIE_NAME);
  const isLogin = pathname === "/login" || pathname === "/signup";

  if (!hasSession && !isLogin) {
    return redirectTo(request, loginPath(pathname + request.nextUrl.search));
  }
  if (hasSession && isLogin) {
    // Where the login form would have sent this visitor: the page it was asked
    // to return to, else the welcome page, which every authenticated role can
    // reach (whereas `/sessions/new` is super_admin-only).
    return redirectTo(request, safeNextPath(request.nextUrl.searchParams.get("next")));
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
