import { http } from "msw";
import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { GET } from "./route";

vi.mock("@scalar/nextjs-api-reference", () => ({
  ApiReference: () => async () => new Response("scalar-mock", { status: 200 }),
}));

const BASE = "http://localhost:8000";

/** Mock `/auth/me` to report a signed-in user holding the given roles. */
function mockMe(roles: string[]) {
  server.use(
    http.get(`${BASE}/api/v1/auth/me`, () =>
      envelope({ user: { id: "u1", roles, groupRoles: [] }, impersonatedBy: null })
    )
  );
}

function makeRequest() {
  const request = new NextRequest("http://localhost:3000/api-doc");
  request.cookies.set("a2flow_session", "abc");
  return request;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("GET /api-doc", () => {
  it("serves the reference for an admin", async () => {
    mockMe(["admin"]);
    const res = await GET(makeRequest());
    expect(res.status).toBe(200);
  });

  it("serves the reference for a super_admin", async () => {
    mockMe(["super_admin"]);
    const res = await GET(makeRequest());
    expect(res.status).toBe(200);
  });

  it.each(["developer", "requester", "approver"])("returns 403 for a %s", async (role) => {
    mockMe([role]);
    const res = await GET(makeRequest());
    expect(res.status).toBe(403);
  });

  it("forwards the caller's session cookie to the backend /auth/me request", async () => {
    mockMe(["admin"]);
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    await GET(makeRequest());

    const meCall = fetchSpy.mock.calls.find(([input]) => input === `${BASE}/api/v1/auth/me`);
    expect(meCall).toBeDefined();
    const init = meCall?.[1] as RequestInit | undefined;
    expect((init?.headers as Record<string, string> | undefined)?.cookie).toBe(
      "a2flow_session=abc"
    );
  });

  it("redirects to /login when the session cookie is missing", async () => {
    server.use(
      http.get(`${BASE}/api/v1/auth/me`, () =>
        envelopeErr("UNAUTHENTICATED", "Not authenticated", 401)
      )
    );
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const request = new NextRequest("http://localhost:3000/api-doc");

    const res = await GET(request);

    expect(res.status).toBeGreaterThanOrEqual(300);
    expect(res.status).toBeLessThan(400);
    expect(res.headers.get("location")).toContain("/login");

    const meCall = fetchSpy.mock.calls.find(([input]) => input === `${BASE}/api/v1/auth/me`);
    const init = meCall?.[1] as RequestInit | undefined;
    expect((init?.headers as Record<string, string> | undefined)?.cookie).toBe("");
  });

  it("redirects to /login when the session cookie is invalid", async () => {
    server.use(
      http.get(`${BASE}/api/v1/auth/me`, () =>
        envelopeErr("UNAUTHENTICATED", "Not authenticated", 401)
      )
    );
    const res = await GET(makeRequest());
    expect(res.status).toBeGreaterThanOrEqual(300);
    expect(res.status).toBeLessThan(400);
    expect(res.headers.get("location")).toContain("/login");
  });
});
