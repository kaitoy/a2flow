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
    expect(res.headers.get("location")).toBe("http://localhost:3000/login?next=%2Fsessions%2Fnew");
  });

  it("keeps the query of the page asked for in next", () => {
    const res = proxy(new NextRequest("http://localhost:3000/workflows?tab=a"));
    expect(res.headers.get("location")).toBe(
      "http://localhost:3000/login?next=%2Fworkflows%3Ftab%3Da"
    );
  });

  it("sends a visitor at the welcome page to a plain /login", () => {
    const res = proxy(new NextRequest("http://localhost:3000/"));
    expect(res.headers.get("location")).toBe("http://localhost:3000/login");
  });

  it("sends an authenticated visitor at /login to the page in next", () => {
    const request = new NextRequest("http://localhost:3000/login?next=%2Fworkflows%3Ftab%3Da");
    request.cookies.set("a2flow_session", "abc");
    expect(proxy(request).headers.get("location")).toBe("http://localhost:3000/workflows?tab=a");
  });

  it("ignores a next that leaves the site", () => {
    const request = new NextRequest("http://localhost:3000/login?next=%2F%2Fevil.example");
    request.cookies.set("a2flow_session", "abc");
    expect(proxy(request).headers.get("location")).toBe("http://localhost:3000/");
  });

  it("redirects authenticated visitors away from /login to the welcome page", () => {
    const request = new NextRequest("http://localhost:3000/login");
    request.cookies.set("a2flow_session", "abc");
    const res = proxy(request);
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe("http://localhost:3000/");
  });

  it.each([false, true])("lets /signed-out through with session=%s", (withSession) => {
    const request = new NextRequest("http://localhost:3000/signed-out");
    if (withSession) request.cookies.set("a2flow_session", "abc");
    const res = proxy(request);
    expect(res.headers.get("location")).toBeNull();
  });

  it("passes through authenticated requests to non-login pages", () => {
    const request = new NextRequest("http://localhost:3000/sessions/new");
    request.cookies.set("a2flow_session", "abc");
    const res = proxy(request);
    expect(res.headers.get("x-middleware-rewrite")).toBeNull();
    expect(res.headers.get("location")).toBeNull();
  });
});
