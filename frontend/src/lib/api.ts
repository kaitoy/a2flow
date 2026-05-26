import { type A2UIInlineCatalogSchema, A2UIMiddleware } from "@ag-ui/a2ui-middleware";
import { HttpAgent } from "@ag-ui/client";
import type { Message } from "@ag-ui/core";
import axios, { type AxiosResponse } from "axios";
import type { z } from "zod";
import type {
  AgentSkillCreate,
  AgentSkill as AgentSkillModel,
  AgentSkillUpdate,
  ApiError,
  ApiMeta,
  Session as SessionModel,
  WorkflowCreate,
  Workflow as WorkflowModel,
  WorkflowSession as WorkflowSessionModel,
  WorkflowTaskCreate,
  WorkflowTask as WorkflowTaskModel,
  WorkflowTaskStatus,
  WorkflowTaskUpdate,
  WorkflowUpdate,
} from "@/generated/api/types.gen";
import {
  zCreateAgentSkillApiV1AgentSkillsPostResponse,
  zCreateWorkflowApiV1WorkflowsPostResponse,
  zCreateWorkflowTaskApiV1WorkflowTasksPostResponse,
  zDeleteAgentSkillApiV1AgentSkillsSkillIdDeleteResponse,
  zDeleteSessionApiV1SessionsSessionIdDeleteResponse,
  zDeleteWorkflowApiV1WorkflowsWorkflowIdDeleteResponse,
  zDeleteWorkflowTaskApiV1WorkflowTasksTaskIdDeleteResponse,
  zExecuteWorkflowApiV1WorkflowsWorkflowIdExecutePostResponse,
  zGetAgentSkillApiV1AgentSkillsSkillIdGetResponse,
  zGetSessionApiV1SessionsSessionIdGetResponse,
  zGetSessionMessagesApiV1SessionsSessionIdMessagesGetResponse,
  zGetWorkflowApiV1WorkflowsWorkflowIdGetResponse,
  zGetWorkflowSessionApiV1WorkflowSessionsWsIdGetResponse,
  zGetWorkflowTaskApiV1WorkflowTasksTaskIdGetResponse,
  zListAgentSkillsApiV1AgentSkillsGetResponse,
  zListSessionsApiV1SessionsGetResponse,
  zListWorkflowSessionsApiV1WorkflowSessionsGetResponse,
  zListWorkflowSessionTasksApiV1WorkflowSessionsWsIdWorkflowTasksGetResponse,
  zListWorkflowsApiV1WorkflowsGetResponse,
  zUpdateAgentSkillApiV1AgentSkillsSkillIdPatchResponse,
  zUpdateWorkflowApiV1WorkflowsWorkflowIdPatchResponse,
  zUpdateWorkflowTaskApiV1WorkflowTasksTaskIdPatchResponse,
} from "@/generated/api/zod.gen";
import basicCatalogJson from "../generated/basic_catalog.json";
import logger from "./logger";

const API_BASE = process.env.BACKEND_BASE_URL ?? "http://localhost:8000";

const apiClient = axios.create({
  baseURL: API_BASE,
  headers: {
    "Content-Type": "application/json",
  },
});

let currentUserId = "";

/** Set the user ID injected into every outgoing request as the ``X-User-Id`` header. */
export function setApiUserId(userId: string): void {
  currentUserId = userId;
}

apiClient.interceptors.request.use((config) => {
  if (currentUserId) {
    config.headers.set("X-User-Id", currentUserId);
  }
  return config;
});

/** Re-export the generated envelope types so call sites do not import from ``@/generated``. */
export type { ApiError, ApiMeta };

/** Generic API response envelope wrapping typed data or an error body. */
export interface ApiResponse<T> {
  meta: ApiMeta;
  data: T | null;
  error: ApiError | null;
}

/** Error thrown when the API returns an error envelope instead of data. */
export class ApiClientError extends Error {
  constructor(
    public code: string,
    message: string,
    public details?: unknown,
    public requestId?: string
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

/**
 * Zod schema shape produced for every wrapped response by ``@hey-api/openapi-ts``.
 * Constrains the helper below so only generated envelope schemas can be passed in.
 */
type EnvelopeSchema = z.ZodObject<{
  meta: z.ZodTypeAny;
  data: z.ZodTypeAny;
  error: z.ZodTypeAny;
}>;

/**
 * Validate an API response against its generated envelope Zod schema and
 * return the inner ``data`` field, throwing ``ApiClientError`` if the
 * envelope carries an error body.
 */
async function fetchEnvelope<S extends EnvelopeSchema>(
  promise: Promise<AxiosResponse<unknown>>,
  schema: S
): Promise<z.infer<S>["data"]> {
  const res = await promise;
  const env = schema.parse(res.data) as {
    meta: ApiMeta;
    data: z.infer<S>["data"];
    error: ApiError | null;
  };
  if (env.error) {
    throw new ApiClientError(
      env.error.code,
      env.error.message,
      env.error.details,
      env.meta.requestId
    );
  }
  return env.data;
}

type AuditedKeys = "id" | "createdAt" | "updatedAt" | "createdBy" | "updatedBy";
type WithAudit<T extends Partial<Record<AuditedKeys, unknown>>> = T &
  Required<Pick<T, AuditedKeys>>;

export type AgentSkill = WithAudit<AgentSkillModel>;
export type Workflow = WithAudit<WorkflowModel>;
export type WorkflowSession = WithAudit<WorkflowSessionModel>;
export type WorkflowTask = WithAudit<WorkflowTaskModel>;
export type Session = SessionModel;
export type {
  AgentSkillCreate,
  AgentSkillUpdate,
  WorkflowCreate,
  WorkflowTaskCreate,
  WorkflowTaskStatus,
  WorkflowTaskUpdate,
  WorkflowUpdate,
};

/** Fetch all sessions for the current user (identified by the X-User-Id header). */
export async function listSessions(): Promise<Session[]> {
  return fetchEnvelope(
    apiClient.get("/api/v1/sessions"),
    zListSessionsApiV1SessionsGetResponse
  ) as Promise<Session[]>;
}

/** Fetch a single session by ID. */
export async function getSession(sessionId: string): Promise<Session> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/sessions/${encodeURIComponent(sessionId)}`),
    zGetSessionApiV1SessionsSessionIdGetResponse
  ) as Promise<Session>;
}

/** Fetch the full message history for a session (used to restore conversation state). */
export async function getSessionMessages(sessionId: string): Promise<Message[]> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/sessions/${encodeURIComponent(sessionId)}/messages`),
    zGetSessionMessagesApiV1SessionsSessionIdMessagesGetResponse
  ) as Promise<Message[]>;
}

/** Delete a session and its associated message history. */
export async function deleteSession(sessionId: string): Promise<void> {
  await fetchEnvelope(
    apiClient.delete(`/api/v1/sessions/${encodeURIComponent(sessionId)}`),
    zDeleteSessionApiV1SessionsSessionIdDeleteResponse
  );
}

/** List agent skills with optional pagination. */
export async function listAgentSkills(limit = 20, offset = 0): Promise<AgentSkill[]> {
  return fetchEnvelope(
    apiClient.get("/api/v1/agent-skills", { params: { limit, offset } }),
    zListAgentSkillsApiV1AgentSkillsGetResponse
  ) as Promise<AgentSkill[]>;
}

/** Fetch a single agent skill by ID. */
export async function getAgentSkill(id: string): Promise<AgentSkill> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/agent-skills/${encodeURIComponent(id)}`),
    zGetAgentSkillApiV1AgentSkillsSkillIdGetResponse
  ) as Promise<AgentSkill>;
}

/** Create a new agent skill. */
export async function createAgentSkill(body: AgentSkillCreate): Promise<AgentSkill> {
  return fetchEnvelope(
    apiClient.post("/api/v1/agent-skills", body),
    zCreateAgentSkillApiV1AgentSkillsPostResponse
  ) as Promise<AgentSkill>;
}

/** Apply a partial update to an agent skill. */
export async function updateAgentSkill(id: string, body: AgentSkillUpdate): Promise<AgentSkill> {
  return fetchEnvelope(
    apiClient.patch(`/api/v1/agent-skills/${encodeURIComponent(id)}`, body),
    zUpdateAgentSkillApiV1AgentSkillsSkillIdPatchResponse
  ) as Promise<AgentSkill>;
}

/** Delete an agent skill by ID. */
export async function deleteAgentSkill(id: string): Promise<void> {
  await fetchEnvelope(
    apiClient.delete(`/api/v1/agent-skills/${encodeURIComponent(id)}`),
    zDeleteAgentSkillApiV1AgentSkillsSkillIdDeleteResponse
  );
}

/** List workflows with optional pagination. */
export async function listWorkflows(limit = 20, offset = 0): Promise<Workflow[]> {
  return fetchEnvelope(
    apiClient.get("/api/v1/workflows", { params: { limit, offset } }),
    zListWorkflowsApiV1WorkflowsGetResponse
  ) as Promise<Workflow[]>;
}

/** Fetch a single workflow by ID. */
export async function getWorkflow(id: string): Promise<Workflow> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/workflows/${encodeURIComponent(id)}`),
    zGetWorkflowApiV1WorkflowsWorkflowIdGetResponse
  ) as Promise<Workflow>;
}

/** Create a new workflow. */
export async function createWorkflow(body: WorkflowCreate): Promise<Workflow> {
  return fetchEnvelope(
    apiClient.post("/api/v1/workflows", body),
    zCreateWorkflowApiV1WorkflowsPostResponse
  ) as Promise<Workflow>;
}

/** Apply a partial update to a workflow. */
export async function updateWorkflow(id: string, body: WorkflowUpdate): Promise<Workflow> {
  return fetchEnvelope(
    apiClient.patch(`/api/v1/workflows/${encodeURIComponent(id)}`, body),
    zUpdateWorkflowApiV1WorkflowsWorkflowIdPatchResponse
  ) as Promise<Workflow>;
}

/** Delete a workflow by ID. */
export async function deleteWorkflow(id: string): Promise<void> {
  await fetchEnvelope(
    apiClient.delete(`/api/v1/workflows/${encodeURIComponent(id)}`),
    zDeleteWorkflowApiV1WorkflowsWorkflowIdDeleteResponse
  );
}

/** Execute a workflow, creating a WorkflowSession that links the ADK session to the workflow. */
export async function executeWorkflow(id: string): Promise<WorkflowSession> {
  const session = (await fetchEnvelope(
    apiClient.post(`/api/v1/workflows/${encodeURIComponent(id)}/execute`),
    zExecuteWorkflowApiV1WorkflowsWorkflowIdExecutePostResponse
  )) as WorkflowSession;
  logger.info({ workflowSessionId: session.id, workflowId: id }, "workflow executed");
  return session;
}

/** Fetch a WorkflowSession record by ID. */
export async function getWorkflowSession(id: string): Promise<WorkflowSession> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/workflow-sessions/${encodeURIComponent(id)}`),
    zGetWorkflowSessionApiV1WorkflowSessionsWsIdGetResponse
  ) as Promise<WorkflowSession>;
}

/** List WorkflowSession records (newest first) with optional pagination. */
export async function listWorkflowSessions(limit = 20, offset = 0): Promise<WorkflowSession[]> {
  return fetchEnvelope(
    apiClient.get("/api/v1/workflow-sessions", { params: { limit, offset } }),
    zListWorkflowSessionsApiV1WorkflowSessionsGetResponse
  ) as Promise<WorkflowSession[]>;
}

/** List the WorkflowTasks belonging to the given WorkflowSession (position ASC). */
export async function listWorkflowTasks(
  workflowSessionId: string,
  limit = 20,
  offset = 0
): Promise<WorkflowTask[]> {
  return fetchEnvelope(
    apiClient.get(
      `/api/v1/workflow-sessions/${encodeURIComponent(workflowSessionId)}/workflow-tasks`,
      { params: { limit, offset } }
    ),
    zListWorkflowSessionTasksApiV1WorkflowSessionsWsIdWorkflowTasksGetResponse
  ) as Promise<WorkflowTask[]>;
}

/** Fetch a single WorkflowTask by ID. */
export async function getWorkflowTask(taskId: string): Promise<WorkflowTask> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/workflow-tasks/${encodeURIComponent(taskId)}`),
    zGetWorkflowTaskApiV1WorkflowTasksTaskIdGetResponse
  ) as Promise<WorkflowTask>;
}

/** Create a new WorkflowTask under the workflow session given in ``body.workflowSessionId``. */
export async function createWorkflowTask(body: WorkflowTaskCreate): Promise<WorkflowTask> {
  return fetchEnvelope(
    apiClient.post("/api/v1/workflow-tasks", body),
    zCreateWorkflowTaskApiV1WorkflowTasksPostResponse
  ) as Promise<WorkflowTask>;
}

/** Apply a partial update to a WorkflowTask. ``workflowSessionId`` is not updatable. */
export async function updateWorkflowTask(
  taskId: string,
  body: WorkflowTaskUpdate
): Promise<WorkflowTask> {
  return fetchEnvelope(
    apiClient.patch(`/api/v1/workflow-tasks/${encodeURIComponent(taskId)}`, body),
    zUpdateWorkflowTaskApiV1WorkflowTasksTaskIdPatchResponse
  ) as Promise<WorkflowTask>;
}

/** Delete a WorkflowTask by ID. */
export async function deleteWorkflowTask(taskId: string): Promise<void> {
  await fetchEnvelope(
    apiClient.delete(`/api/v1/workflow-tasks/${encodeURIComponent(taskId)}`),
    zDeleteWorkflowTaskApiV1WorkflowTasksTaskIdDeleteResponse
  );
}

/**
 * Create an HttpAgent for the general chat endpoint, pre-configured with the A2UI middleware
 * so the agent can render interactive surfaces via the RENDER_A2UI tool.
 */
export function createChatAgent(sessionId: string): HttpAgent {
  const agent = new HttpAgent({
    url: `${API_BASE}/api/v1/agent`,
    threadId: sessionId,
    headers: currentUserId ? { "X-User-Id": currentUserId } : {},
  });
  agent.use(
    new A2UIMiddleware({
      injectA2UITool: true,
      schema: basicCatalogJson as unknown as A2UIInlineCatalogSchema,
    })
  );
  return agent;
}

/**
 * Create an HttpAgent scoped to a specific workflow session endpoint, pre-configured
 * with the A2UI middleware so the agent can render interactive surfaces.
 */
export function createWorkflowSessionAgent(
  workflowSessionId: string,
  sessionId: string
): HttpAgent {
  const agent = new HttpAgent({
    url: `${API_BASE}/api/v1/workflow-sessions/${encodeURIComponent(workflowSessionId)}/agent`,
    threadId: sessionId,
    headers: currentUserId ? { "X-User-Id": currentUserId } : {},
  });
  agent.use(
    new A2UIMiddleware({
      injectA2UITool: true,
      schema: basicCatalogJson as unknown as A2UIInlineCatalogSchema,
    })
  );
  return agent;
}
