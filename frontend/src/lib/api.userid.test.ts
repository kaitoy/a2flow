import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { server } from "@/test/msw/server";
import { createAgentSkill, createWorkflow, setApiUserId } from "./api";

const BASE = "http://localhost:8000";

afterEach(() => {
  setApiUserId("");
});

describe("X-User-Id header", () => {
  it("sends X-User-Id when set", async () => {
    let captured: string | null = null;
    server.use(
      http.post(`${BASE}/agent-skills`, ({ request }) => {
        captured = request.headers.get("x-user-id");
        return HttpResponse.json({}, { status: 201 });
      })
    );
    setApiUserId("alice");
    await createAgentSkill({ name: "S", repo_url: "https://x/y" });
    expect(captured).toBe("alice");
  });

  it("omits X-User-Id when unset", async () => {
    let captured: string | null = "preset";
    server.use(
      http.post(`${BASE}/workflows`, ({ request }) => {
        captured = request.headers.get("x-user-id");
        return HttpResponse.json({}, { status: 201 });
      })
    );
    setApiUserId("");
    await createWorkflow({ name: "W", prompt: "P", agent_skill_id: "skill-1" });
    expect(captured).toBeNull();
  });

  it("uses the latest userId after reassignment", async () => {
    let captured: string | null = null;
    server.use(
      http.patch(`${BASE}/agent-skills/:id`, ({ request }) => {
        captured = request.headers.get("x-user-id");
        return HttpResponse.json({}, { status: 200 });
      })
    );
    setApiUserId("alice");
    setApiUserId("bob");
    const { updateAgentSkill } = await import("./api");
    await updateAgentSkill("skill-1", { name: "X" });
    expect(captured).toBe("bob");
  });
});
