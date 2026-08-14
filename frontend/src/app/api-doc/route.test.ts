import { http } from "msw";
import { NextRequest } from "next/server";
import { describe, expect, it, vi } from "vitest";
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
  return new NextRequest("http://localhost:3000/api-doc", {
    headers: { cookie: "a2flow_session=abc" },
  });
}

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

  it("redirects to /login when the session is missing or invalid", async () => {
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
