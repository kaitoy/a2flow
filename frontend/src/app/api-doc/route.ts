/**
 * @module api-doc — Scalar API reference viewer.
 *
 * Renders an interactive OpenAPI reference at `/api-doc`. The spec is fetched
 * in-browser from `/openapi.json`, which `next.config.ts` rewrites to the
 * FastAPI backend's live spec. `proxy.ts` requires a session cookie to reach
 * this route at all; the `GET` handler below additionally requires the
 * `admin` or `super_admin` role, since this route has no read/write split to
 * fall back to like the admin section's other pages.
 */

import { ApiReference } from "@scalar/nextjs-api-reference";
import { type NextRequest, NextResponse } from "next/server";
import { hasRole, Role } from "@/lib/roles";

/** Scalar configuration pointing at the backend's live OpenAPI document. */
const config = {
  url: "/openapi.json",
  // Browser tab / document title for the reference page.
  pageTitle: "A2Flow API Reference",
  // Hide the "Ask AI" assistant (Scalar Agent).
  agent: {
    disabled: true,
  },
};

/** Underlying handler that serves the Scalar API reference HTML page. */
const serveReference = ApiReference(config);

/** Backend origin for server-to-server calls, mirroring `next.config.ts`'s rewrite target. */
const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL ?? "http://localhost:8000";

/**
 * Route handler that serves the Scalar API reference to admins and super
 * admins only. Forwards the incoming session cookie to the backend's
 * `/auth/me` to resolve the caller's roles (no CSRF token is required since
 * this is a `GET`), redirecting to `/login` if the session is missing or
 * invalid, and responding `403` for any other authenticated role.
 */
export async function GET(request: NextRequest): Promise<Response> {
  const meResponse = await fetch(`${BACKEND_BASE_URL}/api/v1/auth/me`, {
    headers: { cookie: request.headers.get("cookie") ?? "" },
  });
  if (!meResponse.ok) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  const { data } = await meResponse.json();
  if (!hasRole(data.user, Role.ADMIN)) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  return serveReference();
}
