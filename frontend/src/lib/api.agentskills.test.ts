import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/test/msw/server";
import {
  createAgentSkill,
  deleteAgentSkill,
  getAgentSkill,
  listAgentSkills,
  updateAgentSkill,
} from "./api";

const BASE = "http://localhost:8000";

describe("listAgentSkills", () => {
  it("returns parsed skill list", async () => {
    const skills = await listAgentSkills();
    expect(Array.isArray(skills)).toBe(true);
    expect(skills[0].name).toBe("My Skill");
  });

  it("throws on server error", async () => {
    server.use(http.get(`${BASE}/agent-skills`, () => new HttpResponse(null, { status: 500 })));
    await expect(listAgentSkills()).rejects.toThrow("500");
  });
});

describe("getAgentSkill", () => {
  it("returns a single skill", async () => {
    const skill = await getAgentSkill("skill-1");
    expect(skill.id).toBe("skill-1");
  });

  it("throws on 404", async () => {
    server.use(
      http.get(`${BASE}/agent-skills/:skillId`, () => new HttpResponse(null, { status: 404 }))
    );
    await expect(getAgentSkill("missing")).rejects.toThrow("404");
  });
});

describe("createAgentSkill", () => {
  it("returns created skill with id", async () => {
    const skill = await createAgentSkill({
      name: "My Skill",
      repoUrl: "https://github.com/example/repo",
    });
    expect(skill.id).toBe("new-skill-id");
  });

  it("throws on 422", async () => {
    server.use(http.post(`${BASE}/agent-skills`, () => new HttpResponse(null, { status: 422 })));
    await expect(createAgentSkill({ name: "", repoUrl: "" })).rejects.toThrow("422");
  });
});

describe("updateAgentSkill", () => {
  it("PATCHes and returns updated skill", async () => {
    const skill = await updateAgentSkill("skill-1", { name: "Renamed" });
    expect(skill.id).toBe("skill-1");
  });
});

describe("deleteAgentSkill", () => {
  it("resolves on 204", async () => {
    await expect(deleteAgentSkill("skill-1")).resolves.toBeUndefined();
  });

  it("throws on 404", async () => {
    server.use(
      http.delete(`${BASE}/agent-skills/:skillId`, () => new HttpResponse(null, { status: 404 }))
    );
    await expect(deleteAgentSkill("missing")).rejects.toThrow("404");
  });
});
