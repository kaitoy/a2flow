import { http } from "msw";
import { envelope } from "./envelope";

const BASE = "http://localhost:8000";

const SKILL_1 = {
  id: "skill-1",
  tenantId: "tenant-1",
  name: "my-skill",
  repoUrl: "https://github.com/example/repo",
  repoPath: "",
  description: null,
  syncStatus: "ready",
  syncError: null,
  commitSha: "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
  syncedAt: "2026-01-01T00:00:00Z",
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
  tenantId: "tenant-1",
  roles: [],
  groupRoles: [],
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

export const USER_GROUP_1 = {
  id: "group-1",
  tenantId: "tenant-1",
  name: "Developers",
  description: "People who build workflows",
  roles: ["developer"],
  memberIds: ["user-1"],
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

const TENANT_1 = {
  id: "tenant-1",
  displayName: "Acme Corp",
  name: "acme-corp",
  enabled: true,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

const WORKFLOW_1 = {
  id: "wf-1",
  tenantId: "tenant-1",
  name: "my-workflow",
  description: null,
  generatedDescription: null,
  agentSkillId: "skill-1",
  sessionId: "design-session-id",
  agentSkillCommitSha: "a".repeat(40),
  status: "published",
  generationError: null,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "user",
  updatedBy: "user",
};

const WORKFLOW_EXECUTION_1 = {
  id: "execution-1",
  tenantId: "tenant-1",
  sessionId: "executed-session-id",
  workflowId: "wf-1",
  name: "My Workflow",
  description: null,
  agentSkillId: "skill-1",
  agentSkillName: "My Skill",
  agentSkillRepoUrl: "https://github.com/example/repo",
  agentSkillRepoPath: "",
  skillDir: "/tmp/skill",
  initiatorId: "user",
  status: "completed",
  finishedAt: "2026-01-01T00:05:00Z",
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

const WORKFLOW_TASK_TEMPLATE_1 = {
  id: "tmpl-1",
  workflowId: "wf-1",
  title: "Template Step 1",
  description: null,
  dependsOnIds: [],
  toolBindings: [],
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

const WORKFLOW_TASK_1 = {
  id: "task-1",
  workflowExecutionId: "execution-1",
  title: "Step 1",
  description: null,
  status: "pending",
  dependsOnIds: [],
  toolBindings: [],
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

const APPROVAL_1 = {
  id: "appr-1",
  tenantId: "tenant-1",
  workflowExecutionId: "execution-1",
  workflowTaskId: null,
  title: "Deploy to production",
  description: "The agent wants to deploy. Approve?",
  status: "approved",
  response: "Looks good to me",
  approver: "user-1",
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "owner",
  updatedBy: "owner",
};

export const MCP_SERVER_1 = {
  id: "mcp-1",
  tenantId: "tenant-1",
  name: "my-mcp-server",
  transport: "streamable_http",
  url: "https://mcp.example.com/mcp",
  headers: { Authorization: "Bearer secret" },
  args: [],
  env: {},
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

export const MCP_STDIO_SERVER = {
  id: "mcp-2",
  tenantId: "tenant-1",
  name: "local-files",
  transport: "stdio",
  headers: {},
  command: "npx",
  args: ["-y", "files-mcp@0.3.0"],
  // biome-ignore lint/suspicious/noTemplateCurlyInString: literal secret-reference syntax stored by the API
  env: { API_KEY: "${secret:files-key}" },
  createdAt: "2026-01-02T00:00:00Z",
  updatedAt: "2026-01-02T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

export const MCP_TOOL_1 = {
  name: "search",
  description: "Search the web",
  inputSchema: { type: "object" },
};

// Note: secret responses carry only the entry `keys`, never their values — the
// API is write-only.
export const SECRET_1 = {
  id: "secret-1",
  name: "github-token",
  type: "local",
  keys: ["token"],
  vaultMount: null,
  vaultPath: null,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

export const SECRET_VAULT_1 = {
  id: "secret-2",
  name: "vault-token",
  type: "vault",
  keys: [],
  vaultMount: "secret",
  vaultPath: "myapp/github",
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

export const TAG_1 = {
  id: "tag-1",
  tenantId: "tenant-1",
  name: "production",
  color: "rose",
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

export const TAG_2 = {
  id: "tag-2",
  tenantId: "tenant-1",
  name: "aws",
  color: "amber",
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

  http.post(`${BASE}/api/v1/agent-skills/:skillId/pull`, () =>
    envelope({ ...SKILL_1, syncStatus: "pending" }, 202)
  ),

  http.patch(`${BASE}/api/v1/agent-skills/:skillId`, () => envelope(SKILL_1)),

  http.delete(`${BASE}/api/v1/agent-skills/:skillId`, () => envelope(null)),

  http.get(`${BASE}/api/v1/tenants`, () => envelope([TENANT_1])),

  http.get(`${BASE}/api/v1/tenants/:tenantId`, () => envelope(TENANT_1)),

  http.post(`${BASE}/api/v1/tenants`, () => envelope({ ...TENANT_1, id: "new-tenant-id" }, 201)),

  http.patch(`${BASE}/api/v1/tenants/:tenantId`, () => envelope(TENANT_1)),

  http.delete(`${BASE}/api/v1/tenants/:tenantId`, () => envelope(null)),

  http.get(`${BASE}/api/v1/users`, () => envelope([USER_1])),

  // Batch name resolution: every requested ID resolves to USER_1's display
  // name, mirroring the single-user handler below.
  http.post(`${BASE}/api/v1/users/resolve-names`, async ({ request }) => {
    const { ids } = (await request.json()) as { ids: string[] };
    return envelope(
      ids.map((id) => ({ id, displayName: `${USER_1.firstName} ${USER_1.lastName}` }))
    );
  }),

  http.get(`${BASE}/api/v1/users/:userId`, () => envelope(USER_1)),

  http.post(`${BASE}/api/v1/users`, () => envelope({ ...USER_1, id: "new-user-id" }, 201)),

  http.patch(`${BASE}/api/v1/users/:userId`, () => envelope(USER_1)),

  http.delete(`${BASE}/api/v1/users/:userId`, () => envelope(null)),

  http.put(`${BASE}/api/v1/users/:userId/groups`, () => envelope(USER_1)),

  http.get(`${BASE}/api/v1/users/:userId/groups`, () => envelope([USER_GROUP_1])),

  http.get(`${BASE}/api/v1/user-groups`, () => envelope([USER_GROUP_1])),

  http.get(`${BASE}/api/v1/user-groups/:groupId`, () => envelope(USER_GROUP_1)),

  http.post(`${BASE}/api/v1/user-groups`, () =>
    envelope({ ...USER_GROUP_1, id: "new-group-id" }, 201)
  ),

  http.patch(`${BASE}/api/v1/user-groups/:groupId`, () => envelope(USER_GROUP_1)),

  http.delete(`${BASE}/api/v1/user-groups/:groupId`, () => envelope(null)),

  http.get(`${BASE}/api/v1/workflows`, () => envelope([WORKFLOW_1])),

  http.get(`${BASE}/api/v1/workflows/:id`, () => envelope(WORKFLOW_1)),

  http.post(`${BASE}/api/v1/agent-skills/:skillId/workflows`, () =>
    envelope({ ...WORKFLOW_1, id: "new-wf-id", status: "generating" }, 201)
  ),

  http.patch(`${BASE}/api/v1/workflows/:id`, () => envelope(WORKFLOW_1)),

  http.delete(`${BASE}/api/v1/workflows/:id`, () => envelope(null)),

  http.post(`${BASE}/api/v1/workflows/:id/publish`, () =>
    envelope({ ...WORKFLOW_1, status: "published" })
  ),

  http.post(`${BASE}/api/v1/workflows/:id/generate-description`, () =>
    envelope({ ...WORKFLOW_1, generatedDescription: "A freshly generated summary" })
  ),

  http.post(`${BASE}/api/v1/workflows/:id/discard-changes`, () =>
    envelope({ ...WORKFLOW_1, status: "published" })
  ),

  http.post(`${BASE}/api/v1/workflows/:id/deactivate`, () =>
    envelope({ ...WORKFLOW_1, status: "draft" })
  ),

  http.get(`${BASE}/api/v1/workflows/:id/task-templates`, () =>
    envelope([WORKFLOW_TASK_TEMPLATE_1])
  ),

  http.post(`${BASE}/api/v1/workflow-task-templates`, () =>
    envelope({ ...WORKFLOW_TASK_TEMPLATE_1, id: "new-tmpl-id" }, 201)
  ),

  http.get(`${BASE}/api/v1/workflow-task-templates/:templateId`, () =>
    envelope(WORKFLOW_TASK_TEMPLATE_1)
  ),

  http.patch(`${BASE}/api/v1/workflow-task-templates/:templateId`, () =>
    envelope(WORKFLOW_TASK_TEMPLATE_1)
  ),

  http.delete(`${BASE}/api/v1/workflow-task-templates/:templateId`, () => envelope(null)),

  http.get(`${BASE}/api/v1/workflows/:id/messages`, () => envelope([])),

  http.post(`${BASE}/api/v1/workflows/:id/execute`, () => envelope(WORKFLOW_EXECUTION_1, 201)),

  http.get(`${BASE}/api/v1/workflow-executions`, () => envelope([WORKFLOW_EXECUTION_1])),

  http.get(`${BASE}/api/v1/workflow-executions/:id`, () => envelope(WORKFLOW_EXECUTION_1)),

  http.get(`${BASE}/api/v1/workflow-executions/:executionId/messages`, () => envelope([])),

  http.get(`${BASE}/api/v1/workflow-executions/:executionId/workflow-tasks`, () =>
    envelope([WORKFLOW_TASK_1])
  ),

  http.post(`${BASE}/api/v1/workflow-tasks`, () =>
    envelope({ ...WORKFLOW_TASK_1, id: "new-task-id" }, 201)
  ),

  http.get(`${BASE}/api/v1/workflow-tasks/:taskId`, () => envelope(WORKFLOW_TASK_1)),

  http.patch(`${BASE}/api/v1/workflow-tasks/:taskId`, () => envelope(WORKFLOW_TASK_1)),

  http.delete(`${BASE}/api/v1/workflow-tasks/:taskId`, () => envelope(null)),

  http.get(`${BASE}/api/v1/mcp-servers`, () => envelope([MCP_SERVER_1, MCP_STDIO_SERVER])),

  http.get(`${BASE}/api/v1/mcp-servers/:serverId/tools`, () => envelope([MCP_TOOL_1])),

  http.get(`${BASE}/api/v1/mcp-servers/:serverId`, () => envelope(MCP_SERVER_1)),

  http.post(`${BASE}/api/v1/mcp-servers`, () =>
    envelope({ ...MCP_SERVER_1, id: "new-mcp-id" }, 201)
  ),

  http.patch(`${BASE}/api/v1/mcp-servers/:serverId`, () => envelope(MCP_SERVER_1)),

  http.delete(`${BASE}/api/v1/mcp-servers/:serverId`, () => envelope(null)),

  http.get(`${BASE}/api/v1/tags`, () => envelope([TAG_2, TAG_1])),

  http.get(`${BASE}/api/v1/tags/:tagId`, () => envelope(TAG_1)),

  http.post(`${BASE}/api/v1/tags`, () => envelope({ ...TAG_1, id: "new-tag-id" }, 201)),

  http.patch(`${BASE}/api/v1/tags/:tagId`, () => envelope(TAG_1)),

  http.delete(`${BASE}/api/v1/tags/:tagId`, () => envelope(null)),

  http.put(`${BASE}/api/v1/secrets/:secretId/tags`, () => envelope(SECRET_1)),

  http.put(`${BASE}/api/v1/workflows/:workflowId/tags`, () => envelope(WORKFLOW_1)),

  http.put(`${BASE}/api/v1/mcp-servers/:serverId/tags`, () => envelope(MCP_SERVER_1)),

  http.put(`${BASE}/api/v1/agent-skills/:skillId/tags`, () => envelope(SKILL_1)),

  http.get(`${BASE}/api/v1/secrets`, () => envelope([SECRET_1, SECRET_VAULT_1])),

  http.get(`${BASE}/api/v1/secrets/:secretId`, () => envelope(SECRET_1)),

  // A vault secret's keys are not in its read view (they live in Vault), so the
  // picker reads them from this route for both kinds alike.
  http.get(`${BASE}/api/v1/secrets/:secretId/keys`, ({ params }) =>
    envelope(params.secretId === SECRET_VAULT_1.id ? ["password", "username"] : SECRET_1.keys)
  ),

  http.post(`${BASE}/api/v1/secrets`, () => envelope({ ...SECRET_1, id: "new-secret-id" }, 201)),

  http.patch(`${BASE}/api/v1/secrets/:secretId`, () => envelope(SECRET_1)),

  http.delete(`${BASE}/api/v1/secrets/:secretId`, () => envelope(null)),

  http.get(`${BASE}/api/v1/approvals`, () => envelope([APPROVAL_1])),

  http.get(`${BASE}/api/v1/approvals/:approvalId`, ({ params }) =>
    envelope({ ...APPROVAL_1, id: params.approvalId as string })
  ),

  http.patch(`${BASE}/api/v1/approvals/:approvalId`, async ({ params, request }) => {
    const body = (await request.json()) as { status?: string; response?: string | null };
    return envelope({
      ...APPROVAL_1,
      id: params.approvalId as string,
      status: body.status ?? "pending",
      response: body.response ?? null,
      updatedBy: "alice",
    });
  }),

  http.get(`${BASE}/api/v1/notifications`, () => envelope([])),

  http.patch(`${BASE}/api/v1/notifications/:notificationId`, async ({ params, request }) => {
    // `read` is the only mutable field; echo what the caller asked for so tests
    // that flip it in either direction see a truthful response.
    const body = (await request.json()) as { read?: boolean };
    return envelope({
      id: params.notificationId as string,
      tenantId: "tenant-1",
      userId: "user",
      type: "approval_request",
      title: "Plan ready for approval",
      body: null,
      workflowExecutionId: "execution-1",
      read: body.read ?? true,
      createdAt: "2026-01-01T00:00:00Z",
      updatedAt: "2026-01-01T00:00:00Z",
      createdBy: "",
      updatedBy: "",
    });
  }),

  http.post(`${BASE}/api/v1/notifications/read-all`, () => envelope(null)),

  http.delete(`${BASE}/api/v1/notifications/:notificationId`, () => envelope(null)),

  http.post(`${BASE}/api/v1/auth/login`, () => envelope(USER_1)),

  http.post(`${BASE}/api/v1/auth/logout`, () => envelope(null)),

  http.get(`${BASE}/api/v1/auth/me`, () => envelope({ user: USER_1, impersonatedBy: null })),
];
