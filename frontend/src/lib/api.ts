import { type A2UIInlineCatalogSchema, A2UIMiddleware } from "@ag-ui/a2ui-middleware";
import { HttpAgent } from "@ag-ui/client";
import type { Message } from "@ag-ui/core";
import axios, { type AxiosResponse } from "axios";
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

export interface SessionInfo {
  id: string;
  user_id: string;
  last_update_time: string;
}

export async function listSessions(userId: string): Promise<SessionInfo[]> {
  return unwrap(
    apiClient.get<ApiResponse<SessionInfo[]>>("/sessions", {
      params: { user_id: userId },
    })
  );
}

export async function getSessionMessages(sessionId: string, userId: string): Promise<Message[]> {
  return unwrap(
    apiClient.get<ApiResponse<Message[]>>(`/sessions/${encodeURIComponent(sessionId)}/messages`, {
      params: { user_id: userId },
    })
  );
}

export async function createSession(userId: string): Promise<string> {
  const session = await unwrap(
    apiClient.post<ApiResponse<{ id: string }>>("/sessions", {
      user_id: userId,
    })
  );
  logger.info({ sessionId: session.id }, "session created");
  return session.id;
}

export interface AgentSkill {
  id: string;
  name: string;
  repo_url: string;
  repo_path: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  created_by: string;
  updated_by: string;
}

export interface AgentSkillCreate {
  name: string;
  repo_url: string;
  repo_path?: string;
  description?: string | null;
}

export interface AgentSkillUpdate {
  name?: string;
  repo_url?: string;
  repo_path?: string;
  description?: string | null;
}

export async function listAgentSkills(limit = 20, offset = 0): Promise<AgentSkill[]> {
  return unwrap(
    apiClient.get<ApiResponse<AgentSkill[]>>("/agent-skills", {
      params: { limit, offset },
    })
  );
}

export async function getAgentSkill(id: string): Promise<AgentSkill> {
  return unwrap(apiClient.get<ApiResponse<AgentSkill>>(`/agent-skills/${encodeURIComponent(id)}`));
}

export async function createAgentSkill(body: AgentSkillCreate): Promise<AgentSkill> {
  return unwrap(apiClient.post<ApiResponse<AgentSkill>>("/agent-skills", body));
}

export async function updateAgentSkill(id: string, body: AgentSkillUpdate): Promise<AgentSkill> {
  return unwrap(
    apiClient.patch<ApiResponse<AgentSkill>>(`/agent-skills/${encodeURIComponent(id)}`, body)
  );
}

export async function deleteAgentSkill(id: string): Promise<void> {
  await unwrap(apiClient.delete<ApiResponse<null>>(`/agent-skills/${encodeURIComponent(id)}`));
}

export interface Workflow {
  id: string;
  name: string;
  prompt: string;
  description: string | null;
  agent_skill_id: string;
  created_at: string;
  updated_at: string;
  created_by: string;
  updated_by: string;
}

export interface WorkflowCreate {
  name: string;
  prompt: string;
  description?: string | null;
  agent_skill_id: string;
}

export interface WorkflowUpdate {
  name?: string;
  prompt?: string;
  description?: string | null;
  agent_skill_id?: string;
}

export async function listWorkflows(limit = 20, offset = 0): Promise<Workflow[]> {
  return unwrap(
    apiClient.get<ApiResponse<Workflow[]>>("/workflows", {
      params: { limit, offset },
    })
  );
}

export async function getWorkflow(id: string): Promise<Workflow> {
  return unwrap(apiClient.get<ApiResponse<Workflow>>(`/workflows/${encodeURIComponent(id)}`));
}

export async function createWorkflow(body: WorkflowCreate): Promise<Workflow> {
  return unwrap(apiClient.post<ApiResponse<Workflow>>("/workflows", body));
}

export async function updateWorkflow(id: string, body: WorkflowUpdate): Promise<Workflow> {
  return unwrap(
    apiClient.patch<ApiResponse<Workflow>>(`/workflows/${encodeURIComponent(id)}`, body)
  );
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
