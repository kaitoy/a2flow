import { type A2UIInlineCatalogSchema, A2UIMiddleware } from "@ag-ui/a2ui-middleware";
import { HttpAgent } from "@ag-ui/client";
import type { Message } from "@ag-ui/core";
import axios from "axios";
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

export interface SessionInfo {
  session_id: string;
  user_id: string;
  last_update_time: number;
}

export async function listSessions(userId: string): Promise<SessionInfo[]> {
  const response = await apiClient.get<SessionInfo[]>("/sessions", {
    params: { user_id: userId },
  });
  return response.data;
}

export async function getSessionMessages(sessionId: string, userId: string): Promise<Message[]> {
  const response = await apiClient.get<Message[]>(
    `/sessions/${encodeURIComponent(sessionId)}/messages`,
    { params: { user_id: userId } }
  );
  return response.data;
}

export async function createSession(userId: string): Promise<string> {
  const response = await apiClient.post<{ session_id: string }>("/sessions", {
    user_id: userId,
  });
  logger.info({ sessionId: response.data.session_id }, "session created");
  return response.data.session_id;
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
  const response = await apiClient.get<AgentSkill[]>("/agent-skills", {
    params: { limit, offset },
  });
  return response.data;
}

export async function getAgentSkill(id: string): Promise<AgentSkill> {
  const response = await apiClient.get<AgentSkill>(`/agent-skills/${encodeURIComponent(id)}`);
  return response.data;
}

export async function createAgentSkill(body: AgentSkillCreate): Promise<AgentSkill> {
  const response = await apiClient.post<AgentSkill>("/agent-skills", body);
  return response.data;
}

export async function updateAgentSkill(id: string, body: AgentSkillUpdate): Promise<AgentSkill> {
  const response = await apiClient.patch<AgentSkill>(
    `/agent-skills/${encodeURIComponent(id)}`,
    body
  );
  return response.data;
}

export async function deleteAgentSkill(id: string): Promise<void> {
  await apiClient.delete(`/agent-skills/${encodeURIComponent(id)}`);
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
  const response = await apiClient.get<Workflow[]>("/workflows", {
    params: { limit, offset },
  });
  return response.data;
}

export async function getWorkflow(id: string): Promise<Workflow> {
  const response = await apiClient.get<Workflow>(`/workflows/${encodeURIComponent(id)}`);
  return response.data;
}

export async function createWorkflow(body: WorkflowCreate): Promise<Workflow> {
  const response = await apiClient.post<Workflow>("/workflows", body);
  return response.data;
}

export async function updateWorkflow(id: string, body: WorkflowUpdate): Promise<Workflow> {
  const response = await apiClient.patch<Workflow>(`/workflows/${encodeURIComponent(id)}`, body);
  return response.data;
}

export async function deleteWorkflow(id: string): Promise<void> {
  await apiClient.delete(`/workflows/${encodeURIComponent(id)}`);
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
