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
  WorkflowUpdate,
} from "@/generated/api/types.gen";
import {
  zCreateAgentSkillAgentSkillsPostResponse,
  zCreateSessionSessionsPostResponse,
  zCreateWorkflowWorkflowsPostResponse,
  zGetAgentSkillAgentSkillsSkillIdGetResponse,
  zGetWorkflowWorkflowsWorkflowIdGetResponse,
  zListAgentSkillsAgentSkillsGetResponse,
  zListSessionsSessionsGetResponse,
  zListWorkflowsWorkflowsGetResponse,
  zUpdateAgentSkillAgentSkillsSkillIdPatchResponse,
  zUpdateWorkflowWorkflowsWorkflowIdPatchResponse,
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

export function setApiUserId(userId: string): void {
  currentUserId = userId;
}

apiClient.interceptors.request.use((config) => {
  if (currentUserId) {
    config.headers.set("X-User-Id", currentUserId);
  }
  return config;
});

export interface ApiMeta {
  request_id: string;
  received_at: string;
  responded_at: string;
}

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown> | null;
}

export interface ApiResponse<T> {
  meta: ApiMeta;
  data: T | null;
  error: ApiError | null;
}

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
export type Session = SessionModel;
export type { AgentSkillCreate, AgentSkillUpdate, WorkflowCreate, WorkflowUpdate };

export async function listSessions(userId: string): Promise<Session[]> {
  const data = await unwrap(
    apiClient.get<ApiResponse<Session[]>>("/sessions", {
      params: { user_id: userId },
    })
  );
  return zListSessionsSessionsGetResponse.parse(data) as Session[];
}

export async function getSessionMessages(sessionId: string, userId: string): Promise<Message[]> {
  return unwrap(
    apiClient.get<ApiResponse<Message[]>>(`/sessions/${encodeURIComponent(sessionId)}/messages`, {
      params: { user_id: userId },
    })
  );
}

export async function createSession(userId: string): Promise<string> {
  const data = await unwrap(apiClient.post<ApiResponse<Session>>("/sessions", { userId }));
  const session = zCreateSessionSessionsPostResponse.parse(data) as Session;
  logger.info({ sessionId: session.id }, "session created");
  return session.id;
}

export async function listAgentSkills(limit = 20, offset = 0): Promise<AgentSkill[]> {
  const data = await unwrap(
    apiClient.get<ApiResponse<AgentSkill[]>>("/agent-skills", {
      params: { limit, offset },
    })
  );
  return zListAgentSkillsAgentSkillsGetResponse.parse(data) as AgentSkill[];
}

export async function getAgentSkill(id: string): Promise<AgentSkill> {
  const data = await unwrap(
    apiClient.get<ApiResponse<AgentSkill>>(`/agent-skills/${encodeURIComponent(id)}`)
  );
  return zGetAgentSkillAgentSkillsSkillIdGetResponse.parse(data) as AgentSkill;
}

export async function createAgentSkill(body: AgentSkillCreate): Promise<AgentSkill> {
  const data = await unwrap(apiClient.post<ApiResponse<AgentSkill>>("/agent-skills", body));
  return zCreateAgentSkillAgentSkillsPostResponse.parse(data) as AgentSkill;
}

export async function updateAgentSkill(id: string, body: AgentSkillUpdate): Promise<AgentSkill> {
  const data = await unwrap(
    apiClient.patch<ApiResponse<AgentSkill>>(`/agent-skills/${encodeURIComponent(id)}`, body)
  );
  return zUpdateAgentSkillAgentSkillsSkillIdPatchResponse.parse(data) as AgentSkill;
}

export async function deleteAgentSkill(id: string): Promise<void> {
  await unwrap(apiClient.delete<ApiResponse<null>>(`/agent-skills/${encodeURIComponent(id)}`));
}

export async function listWorkflows(limit = 20, offset = 0): Promise<Workflow[]> {
  const data = await unwrap(
    apiClient.get<ApiResponse<Workflow[]>>("/workflows", {
      params: { limit, offset },
    })
  );
  return zListWorkflowsWorkflowsGetResponse.parse(data) as Workflow[];
}

export async function getWorkflow(id: string): Promise<Workflow> {
  const data = await unwrap(
    apiClient.get<ApiResponse<Workflow>>(`/workflows/${encodeURIComponent(id)}`)
  );
  return zGetWorkflowWorkflowsWorkflowIdGetResponse.parse(data) as Workflow;
}

export async function createWorkflow(body: WorkflowCreate): Promise<Workflow> {
  const data = await unwrap(apiClient.post<ApiResponse<Workflow>>("/workflows", body));
  return zCreateWorkflowWorkflowsPostResponse.parse(data) as Workflow;
}

export async function updateWorkflow(id: string, body: WorkflowUpdate): Promise<Workflow> {
  const data = await unwrap(
    apiClient.patch<ApiResponse<Workflow>>(`/workflows/${encodeURIComponent(id)}`, body)
  );
  return zUpdateWorkflowWorkflowsWorkflowIdPatchResponse.parse(data) as Workflow;
}

export async function deleteWorkflow(id: string): Promise<void> {
  await unwrap(apiClient.delete<ApiResponse<null>>(`/workflows/${encodeURIComponent(id)}`));
}

export function createChatAgent(sessionId: string): HttpAgent {
  const agent = new HttpAgent({
    url: `${API_BASE}/agent`,
    threadId: sessionId,
  });
  agent.use(
    new A2UIMiddleware({
      injectA2UITool: true,
      schema: basicCatalogJson as unknown as A2UIInlineCatalogSchema,
    })
  );
  return agent;
}
