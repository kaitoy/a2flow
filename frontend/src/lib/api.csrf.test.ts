import { http } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { createAgentSkill, listAgentSkills } from "./api";

const BASE = "http://localhost:8000";

const SKILL = {
  id: "skill-1",
  name: "S",
  repoUrl: "https://x/y",
  repoPath: "",
  description: null,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

afterEach(() => {
  document.cookie = "a2flow_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
});

describe("CSRF token header", () => {
  it("sends X-CSRF-Token from the cookie on unsafe requests", async () => {
    document.cookie = "a2flow_csrf=tok-123; path=/";
    let captured: string | null = null;
    server.use(
      http.post(`${BASE}/api/v1/agent-skills`, ({ request }) => {
        captured = request.headers.get("x-csrf-token");
        return envelope(SKILL, 201);
      })
    );
    await createAgentSkill({ name: "S", repoUrl: "https://x/y" });
    expect(captured).toBe("tok-123");
  });

  it("does not send X-CSRF-Token on safe requests", async () => {
    document.cookie = "a2flow_csrf=tok-123; path=/";
    let captured: string | null = "preset";
    server.use(
      http.get(`${BASE}/api/v1/agent-skills`, ({ request }) => {
        captured = request.headers.get("x-csrf-token");
        return envelope([SKILL]);
      })
    );
    await listAgentSkills();
    expect(captured).toBeNull();
  });
});
