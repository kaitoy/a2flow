// @vitest-environment-options {"happyDOM":{"url":"http://localhost:3000"}}
/**
 * Cross-origin API access: the setup where `NEXT_PUBLIC_API_BASE` points the
 * browser straight at the backend instead of the same-origin proxy. The page
 * here lives on :3000 while the API base is :8000, so happy-dom preflights the
 * request and lets it through only if the preflight's
 * `Access-Control-Allow-Origin` matches the page, as the backend's
 * `CORSMiddleware` answers for its default `CORS_ORIGINS`.
 *
 * happy-dom models only that much of CORS: its preflight reaches the handler
 * without `Origin` or `Access-Control-Request-*` headers, and it checks neither
 * `Access-Control-Allow-Headers` nor `Access-Control-Allow-Credentials`. Those
 * parts are covered by the backend's own CORS tests.
 */
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { createAgentSkill } from "./api";

const BASE = "http://localhost:8000";
const PAGE_ORIGIN = "http://localhost:3000";

const SKILL = {
  id: "skill-1",
  tenantId: "tenant-1",
  name: "S",
  repoUrl: "https://x/y",
  repoPath: "",
  description: null,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

/** Serve `POST /agent-skills` behind CORS that allows `allowedOrigin`, recording the call order. */
function useCorsBackend(allowedOrigin: string) {
  const calls: string[] = [];
  const cors = {
    "Access-Control-Allow-Origin": allowedOrigin,
    "Access-Control-Allow-Credentials": "true",
  };
  server.use(
    http.options(`${BASE}/api/v1/agent-skills`, () => {
      calls.push("OPTIONS");
      return new HttpResponse(null, {
        status: 204,
        headers: { ...cors, "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE" },
      });
    }),
    http.post(`${BASE}/api/v1/agent-skills`, () => {
      calls.push("POST");
      const response = envelope(SKILL, 201);
      for (const [name, value] of Object.entries(cors)) response.headers.set(name, value);
      return response;
    })
  );
  return calls;
}

afterEach(() => {
  // biome-ignore lint/suspicious/noDocumentCookie: the test sets the CSRF cookie the interceptor reads
  document.cookie = "a2flow_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
});

describe("cross-origin API access", () => {
  it("preflights the request, then sends it when the backend allows the page's origin", async () => {
    // biome-ignore lint/suspicious/noDocumentCookie: the test sets the CSRF cookie the interceptor reads
    document.cookie = "a2flow_csrf=tok-123; path=/";
    const calls = useCorsBackend(PAGE_ORIGIN);

    const skill = await createAgentSkill({ name: "S", repoUrl: "https://x/y" });

    expect(calls).toEqual(["OPTIONS", "POST"]);
    expect(skill.id).toBe("skill-1");
  });

  it("never sends the request when the backend allows another origin", async () => {
    // biome-ignore lint/suspicious/noDocumentCookie: the test sets the CSRF cookie the interceptor reads
    document.cookie = "a2flow_csrf=tok-123; path=/";
    const calls = useCorsBackend("https://other.example");

    await expect(createAgentSkill({ name: "S", repoUrl: "https://x/y" })).rejects.toThrow();
    expect(calls).toEqual(["OPTIONS"]);
  });
});
