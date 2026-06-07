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

const USER_1 = {
  id: "user-1",
  username: "alice",
  firstName: "Alice",
  lastName: "Smith",
  email: "alice@example.com",
  enabled: true,
  emailVerified: false,
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

const WORKFLOW_SESSION_1 = {
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
};

const WORKFLOW_TASK_1 = {
  id: "task-1",
  workflowSessionId: "ws-1",
  title: "Step 1",
  description: null,
  status: "pending",
  position: 0,
  dependsOnIds: [],
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

export const handlers = [
  http.get(`${BASE}/api/v1/sessions`, () =>
    envelope([
      { id: "sess-1", userId: "user", lastUpdateTime: "2026-05-10T12:00:01.000Z" },
      { id: "sess-2", userId: "user", lastUpdateTime: "2026-05-10T12:00:00.000Z" },
    ])
  ),

  http.get(`${BASE}/api/v1/sessions/:sessionId/messages`, () => envelope([])),

  http.get(`${BASE}/api/v1/sessions/:sessionId`, ({ params }) =>
    envelope({
      id: params.sessionId as string,
      userId: "user",
      lastUpdateTime: "2026-05-10T12:00:02.000Z",
    })
  ),

  http.delete(`${BASE}/api/v1/sessions/:sessionId`, () => envelope(null)),

  http.post(`${BASE}/api/v1/sessions`, () =>
    envelope(
      {
        id: "new-session-id",
        userId: "user",
        lastUpdateTime: "2026-05-10T12:00:00.000Z",
      },
      201
    )
  ),

  http.get(`${BASE}/api/v1/agent-skills`, () => envelope([SKILL_1])),

  http.get(`${BASE}/api/v1/agent-skills/:skillId`, () => envelope(SKILL_1)),

  http.post(`${BASE}/api/v1/agent-skills`, () => envelope({ ...SKILL_1, id: "new-skill-id" }, 201)),

  http.patch(`${BASE}/api/v1/agent-skills/:skillId`, () => envelope(SKILL_1)),

  http.delete(`${BASE}/api/v1/agent-skills/:skillId`, () => envelope(null)),

  http.get(`${BASE}/api/v1/users`, () => envelope([USER_1])),

  http.get(`${BASE}/api/v1/users/:userId`, () => envelope(USER_1)),

  http.post(`${BASE}/api/v1/users`, () => envelope({ ...USER_1, id: "new-user-id" }, 201)),

  http.patch(`${BASE}/api/v1/users/:userId`, () => envelope(USER_1)),

  http.delete(`${BASE}/api/v1/users/:userId`, () => envelope(null)),

  http.get(`${BASE}/api/v1/workflows`, () => envelope([WORKFLOW_1])),

  http.get(`${BASE}/api/v1/workflows/:id`, () => envelope(WORKFLOW_1)),

  http.post(`${BASE}/api/v1/workflows`, () => envelope({ ...WORKFLOW_1, id: "new-wf-id" }, 201)),

  http.patch(`${BASE}/api/v1/workflows/:id`, () => envelope(WORKFLOW_1)),

  http.delete(`${BASE}/api/v1/workflows/:id`, () => envelope(null)),

  http.post(`${BASE}/api/v1/workflows/:id/execute`, () =>
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

  http.get(`${BASE}/api/v1/workflow-sessions`, () => envelope([WORKFLOW_SESSION_1])),

  http.get(`${BASE}/api/v1/workflow-sessions/:id`, () => envelope(WORKFLOW_SESSION_1)),

  http.get(`${BASE}/api/v1/workflow-sessions/:wsId/workflow-tasks`, () =>
    envelope([WORKFLOW_TASK_1])
  ),

  http.post(`${BASE}/api/v1/workflow-tasks`, () =>
    envelope({ ...WORKFLOW_TASK_1, id: "new-task-id" }, 201)
  ),

  http.get(`${BASE}/api/v1/workflow-tasks/:taskId`, () => envelope(WORKFLOW_TASK_1)),

  http.patch(`${BASE}/api/v1/workflow-tasks/:taskId`, () => envelope(WORKFLOW_TASK_1)),

  http.delete(`${BASE}/api/v1/workflow-tasks/:taskId`, () => envelope(null)),
];
