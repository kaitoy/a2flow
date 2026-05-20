import { http } from "msw";
import { envelope } from "./envelope";

const BASE = "http://localhost:8000";

const SKILL_1 = {
  id: "skill-1",
  name: "My Skill",
  repoUrl: "https://github.com/example/repo",
  repoPath: "",
  description: null,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

const WORKFLOW_1 = {
  id: "wf-1",
  name: "My Workflow",
  prompt: "Do the thing",
  description: null,
  agentSkillId: "skill-1",
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

export const handlers = [
  http.get(`${BASE}/sessions`, () =>
    envelope([
      { id: "sess-1", userId: "user", lastUpdateTime: "2026-05-10T12:00:01.000Z" },
      { id: "sess-2", userId: "user", lastUpdateTime: "2026-05-10T12:00:00.000Z" },
    ])
  ),

  http.get(`${BASE}/sessions/:sessionId/messages`, () => envelope([])),

  http.post(`${BASE}/sessions`, () =>
    envelope(
      {
        id: "new-session-id",
        userId: "user",
        lastUpdateTime: "2026-05-10T12:00:00.000Z",
      },
      201
    )
  ),

  http.get(`${BASE}/agent-skills`, () => envelope([SKILL_1])),

  http.get(`${BASE}/agent-skills/:skillId`, () => envelope(SKILL_1)),

  http.post(`${BASE}/agent-skills`, () => envelope({ ...SKILL_1, id: "new-skill-id" }, 201)),

  http.patch(`${BASE}/agent-skills/:skillId`, () => envelope(SKILL_1)),

  http.delete(`${BASE}/agent-skills/:skillId`, () => envelope(null)),

  http.get(`${BASE}/workflows`, () => envelope([WORKFLOW_1])),

  http.get(`${BASE}/workflows/:id`, () => envelope(WORKFLOW_1)),

  http.post(`${BASE}/workflows`, () => envelope({ ...WORKFLOW_1, id: "new-wf-id" }, 201)),

  http.patch(`${BASE}/workflows/:id`, () => envelope(WORKFLOW_1)),

  http.delete(`${BASE}/workflows/:id`, () => envelope(null)),

  http.post(`${BASE}/workflows/:id/execute`, () =>
    envelope(
      {
        id: "ws-1",
        sessionId: "executed-session-id",
        workflowId: "wf-1",
        workflowName: "My Workflow",
        workflowPrompt: "Do the thing",
        workflowDescription: null,
        agentSkillId: "skill-1",
        agentSkillName: "My Skill",
        agentSkillRepoUrl: "https://github.com/example/repo",
        agentSkillRepoPath: "",
        skillDir: "/tmp/skill",
        userId: "user",
        createdAt: "2026-01-01T00:00:00Z",
        updatedAt: "2026-01-01T00:00:00Z",
        createdBy: "",
        updatedBy: "",
      },
      201
    )
  ),

  http.get(`${BASE}/workflow-sessions/:id`, () =>
    envelope({
      id: "ws-1",
      sessionId: "executed-session-id",
      workflowId: "wf-1",
      workflowName: "My Workflow",
      workflowPrompt: "Do the thing",
      workflowDescription: null,
      agentSkillId: "skill-1",
      agentSkillName: "My Skill",
      agentSkillRepoUrl: "https://github.com/example/repo",
      agentSkillRepoPath: "",
      skillDir: "/tmp/skill",
      userId: "user",
      createdAt: "2026-01-01T00:00:00Z",
      updatedAt: "2026-01-01T00:00:00Z",
      createdBy: "",
      updatedBy: "",
    })
  ),
];
