import { type A2UIInlineCatalogSchema, A2UIMiddleware } from "@ag-ui/a2ui-middleware";
import { HttpAgent } from "@ag-ui/client";
import type { Message } from "@ag-ui/core";
import axios, { type AxiosResponse } from "axios";
import type {
  AgentSkillCreate,
  AgentSkill as AgentSkillModel,
  AgentSkillUpdate,
  Session as SessionModel,
  WorkflowCreate,
  Workflow as WorkflowModel,
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
  zGetAgentSkillApiV1AgentSkillsSkillIdGetResponse,
  zGetSessionApiV1SessionsSessionIdGetResponse,
  zGetWorkflowApiV1WorkflowsWorkflowIdGetResponse,
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

/** Request metadata returned in every API response envelope. */
export interface ApiMeta {
  request_id: string;
  received_at: string;
  responded_at: string;
}

/** Structured error payload returned in the ``error`` field of an API response. */
export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown> | null;
}

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

/** Unwrap the API response envelope, throwing ``ApiClientError`` if the response contains an error. */
async function unwrap<T>(p: Promise<AxiosResponse<ApiResponse<T>>>): Promise<T> {
  const res = await p;
  const env = res.data;
  if (env.error) {
    throw new ApiClientError(
      env.error.code,
      env.error.message,
      env.error.details,
      env.meta.request_id
    );
  }
  return env.data as T;
}

type AuditedKeys = "id" | "createdAt" | "updatedAt" | "createdBy" | "updatedBy";
type WithAudit<T extends Partial<Record<AuditedKeys, unknown>>> = T &
  Required<Pick<T, AuditedKeys>>;

export type AgentSkill = WithAudit<AgentSkillModel>;
export type Workflow = WithAudit<WorkflowModel>;
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

/** Snapshot of workflow and skill metadata recorded when a workflow is executed. */
export interface WorkflowSession {
  id: string;
  sessionId: string;
  workflowId: string | null;
  workflowName: string;
  workflowPrompt: string;
  workflowDescription: string | null;
  agentSkillId: string;
  agentSkillName: string;
  agentSkillRepoUrl: string;
  agentSkillRepoPath: string;
  skillDir: string;
  userId: string;
  createdAt: string;
  updatedAt: string;
  createdBy: string;
  updatedBy: string;
}

/** Fetch all sessions for the current user (identified by the X-User-Id header). */
export async function listSessions(): Promise<Session[]> {
  const data = await unwrap(apiClient.get<ApiResponse<Session[]>>("/api/v1/sessions"));
  return zListSessionsApiV1SessionsGetResponse.parse(data) as Session[];
}

/** Fetch a single session by ID. */
export async function getSession(sessionId: string): Promise<Session> {
  const data = await unwrap(
    apiClient.get<ApiResponse<Session>>(`/api/v1/sessions/${encodeURIComponent(sessionId)}`)
  );
  return zGetSessionApiV1SessionsSessionIdGetResponse.parse(data) as Session;
}

/** Fetch the full message history for a session (used to restore conversation state). */
export async function getSessionMessages(sessionId: string): Promise<Message[]> {
  return unwrap(
    apiClient.get<ApiResponse<Message[]>>(
      `/api/v1/sessions/${encodeURIComponent(sessionId)}/messages`
    )
  );
}

/** Delete a session and its associated message history. */
export async function deleteSession(sessionId: string): Promise<void> {
  await unwrap(
    apiClient.delete<ApiResponse<null>>(`/api/v1/sessions/${encodeURIComponent(sessionId)}`)
  );
}

/** List agent skills with optional pagination. */
export async function listAgentSkills(limit = 20, offset = 0): Promise<AgentSkill[]> {
  const data = await unwrap(
    apiClient.get<ApiResponse<AgentSkill[]>>("/api/v1/agent-skills", {
      params: { limit, offset },
    })
  );
  return zListAgentSkillsApiV1AgentSkillsGetResponse.parse(data) as AgentSkill[];
}

/** Fetch a single agent skill by ID. */
export async function getAgentSkill(id: string): Promise<AgentSkill> {
  const data = await unwrap(
    apiClient.get<ApiResponse<AgentSkill>>(`/api/v1/agent-skills/${encodeURIComponent(id)}`)
  );
  return zGetAgentSkillApiV1AgentSkillsSkillIdGetResponse.parse(data) as AgentSkill;
}

/** Create a new agent skill. */
export async function createAgentSkill(body: AgentSkillCreate): Promise<AgentSkill> {
  const data = await unwrap(apiClient.post<ApiResponse<AgentSkill>>("/api/v1/agent-skills", body));
  return zCreateAgentSkillApiV1AgentSkillsPostResponse.parse(data) as AgentSkill;
}

/** Apply a partial update to an agent skill. */
export async function updateAgentSkill(id: string, body: AgentSkillUpdate): Promise<AgentSkill> {
  const data = await unwrap(
    apiClient.patch<ApiResponse<AgentSkill>>(`/api/v1/agent-skills/${encodeURIComponent(id)}`, body)
  );
  return zUpdateAgentSkillApiV1AgentSkillsSkillIdPatchResponse.parse(data) as AgentSkill;
}

/** Delete an agent skill by ID. */
export async function deleteAgentSkill(id: string): Promise<void> {
  await unwrap(
    apiClient.delete<ApiResponse<null>>(`/api/v1/agent-skills/${encodeURIComponent(id)}`)
  );
}

/** List workflows with optional pagination. */
export async function listWorkflows(limit = 20, offset = 0): Promise<Workflow[]> {
  const data = await unwrap(
    apiClient.get<ApiResponse<Workflow[]>>("/api/v1/workflows", {
      params: { limit, offset },
    })
  );
  return zListWorkflowsApiV1WorkflowsGetResponse.parse(data) as Workflow[];
}

/** Fetch a single workflow by ID. */
export async function getWorkflow(id: string): Promise<Workflow> {
  const data = await unwrap(
    apiClient.get<ApiResponse<Workflow>>(`/api/v1/workflows/${encodeURIComponent(id)}`)
  );
  return zGetWorkflowApiV1WorkflowsWorkflowIdGetResponse.parse(data) as Workflow;
}

/** Create a new workflow. */
export async function createWorkflow(body: WorkflowCreate): Promise<Workflow> {
  const data = await unwrap(apiClient.post<ApiResponse<Workflow>>("/api/v1/workflows", body));
  return zCreateWorkflowApiV1WorkflowsPostResponse.parse(data) as Workflow;
}

/** Apply a partial update to a workflow. */
export async function updateWorkflow(id: string, body: WorkflowUpdate): Promise<Workflow> {
  const data = await unwrap(
    apiClient.patch<ApiResponse<Workflow>>(`/api/v1/workflows/${encodeURIComponent(id)}`, body)
  );
  return zUpdateWorkflowApiV1WorkflowsWorkflowIdPatchResponse.parse(data) as Workflow;
}

/** Delete a workflow by ID. */
export async function deleteWorkflow(id: string): Promise<void> {
  await unwrap(apiClient.delete<ApiResponse<null>>(`/api/v1/workflows/${encodeURIComponent(id)}`));
}

/** Execute a workflow, creating a WorkflowSession that links the ADK session to the workflow. */
export async function executeWorkflow(id: string): Promise<WorkflowSession> {
  const data = await unwrap(
    apiClient.post<ApiResponse<WorkflowSession>>(
      `/api/v1/workflows/${encodeURIComponent(id)}/execute`
    )
  );
  logger.info(
    { workflowSessionId: (data as WorkflowSession).id, workflowId: id },
    "workflow executed"
  );
  return data as WorkflowSession;
}

/** Fetch a WorkflowSession record by ID. */
export async function getWorkflowSession(id: string): Promise<WorkflowSession> {
  return unwrap(
    apiClient.get<ApiResponse<WorkflowSession>>(
      `/api/v1/workflow-sessions/${encodeURIComponent(id)}`
    )
  );
}

/** List WorkflowSession records (newest first) with optional pagination. */
export async function listWorkflowSessions(limit = 20, offset = 0): Promise<WorkflowSession[]> {
  const data = await unwrap(
    apiClient.get<ApiResponse<WorkflowSession[]>>("/api/v1/workflow-sessions", {
      params: { limit, offset },
    })
  );
  return zListWorkflowSessionsApiV1WorkflowSessionsGetResponse.parse(data) as WorkflowSession[];
}

/** List the WorkflowTasks belonging to the given WorkflowSession (position ASC). */
export async function listWorkflowTasks(
  workflowSessionId: string,
  limit = 20,
  offset = 0
): Promise<WorkflowTask[]> {
  const data = await unwrap(
    apiClient.get<ApiResponse<WorkflowTask[]>>(
      `/api/v1/workflow-sessions/${encodeURIComponent(workflowSessionId)}/workflow-tasks`,
      { params: { limit, offset } }
    )
  );
  return zListWorkflowSessionTasksApiV1WorkflowSessionsWsIdWorkflowTasksGetResponse.parse(
    data
  ) as WorkflowTask[];
}

/** Fetch a single WorkflowTask by ID. */
export async function getWorkflowTask(taskId: string): Promise<WorkflowTask> {
  const data = await unwrap(
    apiClient.get<ApiResponse<WorkflowTask>>(`/api/v1/workflow-tasks/${encodeURIComponent(taskId)}`)
  );
  return zGetWorkflowTaskApiV1WorkflowTasksTaskIdGetResponse.parse(data) as WorkflowTask;
}

/** Create a new WorkflowTask under the workflow session given in ``body.workflowSessionId``. */
export async function createWorkflowTask(body: WorkflowTaskCreate): Promise<WorkflowTask> {
  const data = await unwrap(
    apiClient.post<ApiResponse<WorkflowTask>>("/api/v1/workflow-tasks", body)
  );
  return zCreateWorkflowTaskApiV1WorkflowTasksPostResponse.parse(data) as WorkflowTask;
}

/** Apply a partial update to a WorkflowTask. ``workflowSessionId`` is not updatable. */
export async function updateWorkflowTask(
  taskId: string,
  body: WorkflowTaskUpdate
): Promise<WorkflowTask> {
  const data = await unwrap(
    apiClient.patch<ApiResponse<WorkflowTask>>(
      `/api/v1/workflow-tasks/${encodeURIComponent(taskId)}`,
      body
    )
  );
  return zUpdateWorkflowTaskApiV1WorkflowTasksTaskIdPatchResponse.parse(data) as WorkflowTask;
}

/** Delete a WorkflowTask by ID. */
export async function deleteWorkflowTask(taskId: string): Promise<void> {
  await unwrap(
    apiClient.delete<ApiResponse<null>>(`/api/v1/workflow-tasks/${encodeURIComponent(taskId)}`)
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
