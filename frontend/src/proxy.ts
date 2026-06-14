/**
 * @module proxy — Edge route guard based on the presence of the session cookie.
 *
 * Next.js proxy runs on the server and can read the HttpOnly session
 * cookie. It only checks for the cookie's presence (not validity); the
 * `AuthProvider` then confirms the session with `/auth/me` and the axios 401
 * interceptor handles sessions that turn out to be invalid.
 */
import { type NextRequest, NextResponse } from "next/server";

/** Name of the HttpOnly session cookie set by the backend at login. */
const SESSION_COOKIE_NAME = "a2flow_session";

/**
 * Redirect unauthenticated visitors to `/login` and authenticated visitors away
 * from `/login`.
 *
 * @param request - The incoming request.
 * @returns A redirect response, or `NextResponse.next()` to continue.
 */
export function proxy(request: NextRequest): NextResponse {
  const hasSession = request.cookies.has(SESSION_COOKIE_NAME);
  const { pathname } = request.nextUrl;
  const isLogin = pathname === "/login";

  if (!hasSession && !isLogin) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }
  if (hasSession && isLogin) {
    const url = request.nextUrl.clone();
    url.pathname = "/new-session";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // Run on all paths except Next internals, the API proxy, and static assets.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\..*).*)"],
};
