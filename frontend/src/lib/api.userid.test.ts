import { http } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { createAgentSkill, createWorkflow, setApiUserId } from "./api";

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

const WORKFLOW = {
  id: "wf-1",
  name: "W",
  prompt: "P",
  description: null,
  agentSkillId: "skill-1",
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

afterEach(() => {
  setApiUserId("");
});

describe("X-User-Id header", () => {
  it("sends X-User-Id when set", async () => {
    let captured: string | null = null;
    server.use(
      http.post(`${BASE}/api/v1/agent-skills`, ({ request }) => {
        captured = request.headers.get("x-user-id");
        return envelope(SKILL, 201);
      })
    );
    setApiUserId("alice");
    await createAgentSkill({ name: "S", repoUrl: "https://x/y" });
    expect(captured).toBe("alice");
  });

  it("omits X-User-Id when unset", async () => {
    let captured: string | null = "preset";
    server.use(
      http.post(`${BASE}/api/v1/workflows`, ({ request }) => {
        captured = request.headers.get("x-user-id");
        return envelope(WORKFLOW, 201);
      })
    );
    setApiUserId("");
    await createWorkflow({ name: "W", prompt: "P", agentSkillId: "skill-1" });
    expect(captured).toBeNull();
  });

  it("uses the latest userId after reassignment", async () => {
    let captured: string | null = null;
    server.use(
      http.patch(`${BASE}/api/v1/agent-skills/:id`, ({ request }) => {
        captured = request.headers.get("x-user-id");
        return envelope(SKILL);
      })
    );
    setApiUserId("alice");
    setApiUserId("bob");
    const { updateAgentSkill } = await import("./api");
    await updateAgentSkill("skill-1", { name: "X" });
    expect(captured).toBe("bob");
  });
});
