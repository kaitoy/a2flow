import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";
import { buildBackendRewriteUrl, proxy } from "./proxy";

describe("buildBackendRewriteUrl", () => {
  it("preserves the path and query string against the given backend origin", () => {
    const url = buildBackendRewriteUrl("/api/v1/agent", "?x=1", "http://backend:8000");
    expect(url.toString()).toBe("http://backend:8000/api/v1/agent?x=1");
  });

  it("handles an empty query string", () => {
    const url = buildBackendRewriteUrl("/openapi.json", "", "http://backend:8000");
    expect(url.toString()).toBe("http://backend:8000/openapi.json");
  });
});

describe("proxy", () => {
  it("rewrites /api/* to the backend, bypassing the session check", () => {
    const request = new NextRequest("http://localhost:3000/api/v1/agent?x=1");
    const res = proxy(request);
    expect(res.headers.get("x-middleware-rewrite")).toBe("http://localhost:8000/api/v1/agent?x=1");
  });

  it("rewrites /openapi.json to the backend, bypassing the session check", () => {
    const request = new NextRequest("http://localhost:3000/openapi.json");
    const res = proxy(request);
    expect(res.headers.get("x-middleware-rewrite")).toBe("http://localhost:8000/openapi.json");
  });

  it("redirects unauthenticated visitors to /login", () => {
    const request = new NextRequest("http://localhost:3000/sessions/new");
    const res = proxy(request);
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe("http://localhost:3000/login");
  });

  it("redirects authenticated visitors away from /login to the welcome page", () => {
    const request = new NextRequest("http://localhost:3000/login");
    request.cookies.set("a2flow_session", "abc");
    const res = proxy(request);
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe("http://localhost:3000/admin");
  });

  it("passes through authenticated requests to non-login pages", () => {
    const request = new NextRequest("http://localhost:3000/sessions/new");
    request.cookies.set("a2flow_session", "abc");
    const res = proxy(request);
    expect(res.headers.get("x-middleware-rewrite")).toBeNull();
    expect(res.headers.get("location")).toBeNull();
  });
});
