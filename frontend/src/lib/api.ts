import { type A2UIInlineCatalogSchema, A2UIMiddleware } from "@ag-ui/a2ui-middleware";
import { HttpAgent } from "@ag-ui/client";
import type { Message } from "@ag-ui/core";
import axios, { type AxiosRequestConfig, type AxiosResponse } from "axios";
import type { z } from "zod";
import type {
  AgentSkillCreate,
  AgentSkill as AgentSkillModel,
  AgentSkillUpdate,
  ApiError,
  ApiMeta,
  Approval as ApprovalModel,
  ApprovalStatus,
  ApprovalUpdate,
  AvatarConfig,
  LoginRequest,
  McpRegistryHeader,
  McpRegistrySearchResult,
  McpRegistryServerEntry,
  McpServerCreate,
  McpServer as McpServerModel,
  McpServerUpdate,
  McpToolInfo,
  Notification as NotificationModel,
  NotificationType,
  Session as SessionModel,
  ToolBinding,
  UserCreate,
  UserRead as UserReadModel,
  UserUpdate,
  WorkflowCreate,
  Workflow as WorkflowModel,
  WorkflowSession as WorkflowSessionModel,
  WorkflowTaskCreate,
  WorkflowTaskRead as WorkflowTaskModel,
  WorkflowTaskStatus,
  WorkflowTaskUpdate,
  WorkflowUpdate,
} from "@/generated/api/types.gen";
import {
  zCreateAgentSkillApiV1AgentSkillsPostResponse,
  zCreateMcpServerApiV1McpServersPostResponse,
  zCreateUserApiV1UsersPostResponse,
  zCreateWorkflowApiV1WorkflowsPostResponse,
  zCreateWorkflowTaskApiV1WorkflowTasksPostResponse,
  zDeleteAgentSkillApiV1AgentSkillsSkillIdDeleteResponse,
  zDeleteMcpServerApiV1McpServersServerIdDeleteResponse,
  zDeleteSessionApiV1SessionsSessionIdDeleteResponse,
  zDeleteUserApiV1UsersUserIdDeleteResponse,
  zDeleteUserAvatarApiV1UsersUserIdAvatarDeleteResponse,
  zDeleteWorkflowApiV1WorkflowsWorkflowIdDeleteResponse,
  zDeleteWorkflowSessionApiV1WorkflowSessionsWsIdDeleteResponse,
  zDeleteWorkflowTaskApiV1WorkflowTasksTaskIdDeleteResponse,
  zExecuteWorkflowApiV1WorkflowsWorkflowIdExecutePostResponse,
  zGetAgentSkillApiV1AgentSkillsSkillIdGetResponse,
  zGetApprovalApiV1ApprovalsApprovalIdGetResponse,
  zGetMcpServerApiV1McpServersServerIdGetResponse,
  zGetSessionApiV1SessionsSessionIdGetResponse,
  zGetSessionMessagesApiV1SessionsSessionIdMessagesGetResponse,
  zGetUserApiV1UsersUserIdGetResponse,
  zGetWorkflowApiV1WorkflowsWorkflowIdGetResponse,
  zGetWorkflowSessionApiV1WorkflowSessionsWsIdGetResponse,
  zGetWorkflowSessionMessagesApiV1WorkflowSessionsWsIdMessagesGetResponse,
  zGetWorkflowTaskApiV1WorkflowTasksTaskIdGetResponse,
  zListAgentSkillsApiV1AgentSkillsGetResponse,
  zListApprovalsApiV1ApprovalsGetResponse,
  zListMcpServersApiV1McpServersGetResponse,
  zListMcpServerToolsApiV1McpServersServerIdToolsGetResponse,
  zListNotificationsApiV1NotificationsGetResponse,
  zListSessionsApiV1SessionsGetResponse,
  zListUsersApiV1UsersGetResponse,
  zListWorkflowSessionsApiV1WorkflowSessionsGetResponse,
  zListWorkflowSessionTasksApiV1WorkflowSessionsWsIdWorkflowTasksGetResponse,
  zListWorkflowsApiV1WorkflowsGetResponse,
  zLoginApiV1AuthLoginPostResponse,
  zLogoutApiV1AuthLogoutPostResponse,
  zMarkNotificationReadApiV1NotificationsNotificationIdPatchResponse,
  zMeApiV1AuthMeGetResponse,
  zResolveApprovalApiV1ApprovalsApprovalIdPatchResponse,
  zSearchMcpRegistryApiV1McpRegistryGetResponse,
  zUpdateAgentSkillApiV1AgentSkillsSkillIdPatchResponse,
  zUpdateMcpServerApiV1McpServersServerIdPatchResponse,
  zUpdateUserApiV1UsersUserIdPatchResponse,
  zUpdateWorkflowApiV1WorkflowsWorkflowIdPatchResponse,
  zUpdateWorkflowTaskApiV1WorkflowTasksTaskIdPatchResponse,
  zUploadUserAvatarApiV1UsersUserIdAvatarPutResponse,
} from "@/generated/api/zod.gen";
import basicCatalogJson from "../generated/basic_catalog.json";
import logger from "./logger";

/**
 * API base URL. Empty by default so the browser talks to the frontend origin
 * and Next.js rewrites proxy `/api/*` to the backend — this keeps the auth
 * cookies same-origin. Override with `NEXT_PUBLIC_API_BASE` only for setups
 * that bypass the proxy.
 */
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

/** Name of the readable CSRF cookie set by the backend at login. */
const CSRF_COOKIE_NAME = "a2flow_csrf";
/** Header the backend expects the CSRF cookie value echoed in on unsafe requests. */
const CSRF_HEADER_NAME = "X-CSRF-Token";
/** HTTP methods that mutate state and therefore require a CSRF token. */
const UNSAFE_METHODS = new Set(["post", "put", "patch", "delete"]);

/** Read a cookie value by name from `document.cookie`, or `null` when absent. */
function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((row) => row.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

const apiClient = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
  headers: {
    "Content-Type": "application/json",
  },
});

apiClient.interceptors.request.use((config) => {
  if (UNSAFE_METHODS.has((config.method ?? "get").toLowerCase())) {
    const token = readCookie(CSRF_COOKIE_NAME);
    if (token) config.headers.set(CSRF_HEADER_NAME, token);
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // Redirect to the login page when a request is rejected for lack of a valid
    // session — except the login request itself, which surfaces 401 inline.
    const url: string = error?.config?.url ?? "";
    if (
      typeof window !== "undefined" &&
      error?.response?.status === 401 &&
      !url.endsWith("/auth/login") &&
      window.location.pathname !== "/login"
    ) {
      window.location.assign("/login");
    }
    return Promise.reject(error);
  }
);

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
export type Approval = WithAudit<ApprovalModel>;
export type McpServer = WithAudit<McpServerModel>;
export type Notification = WithAudit<NotificationModel>;
export type User = WithAudit<UserReadModel>;
export type Workflow = WithAudit<WorkflowModel>;
export type WorkflowSession = WithAudit<WorkflowSessionModel>;
export type WorkflowTask = WithAudit<WorkflowTaskModel>;
export type Session = SessionModel;
export type {
  AgentSkillCreate,
  AgentSkillUpdate,
  ApprovalStatus,
  ApprovalUpdate,
  AvatarConfig,
  LoginRequest,
  McpRegistryHeader,
  McpRegistrySearchResult,
  McpRegistryServerEntry,
  McpServerCreate,
  McpServerUpdate,
  McpToolInfo,
  NotificationType,
  ToolBinding,
  UserCreate,
  UserUpdate,
  WorkflowCreate,
  WorkflowTaskCreate,
  WorkflowTaskStatus,
  WorkflowTaskUpdate,
  WorkflowUpdate,
};

/** A single server-side sort directive: order by `field`, descending when set. */
export interface SortSpec {
  /** camelCase field name to sort by (matches the model field exposed by the API). */
  field: string;
  /** When true, sort descending; otherwise ascending. */
  descending: boolean;
}

/** A single server-side filter directive applied as `field:op:value`. */
export interface FilterSpec {
  /** camelCase field name to filter on. */
  field: string;
  /** Comparison operator: one of `eq`/`ne`/`lt`/`lte`/`gt`/`gte`/`like`/`in`. */
  op: string;
  /** Value to compare against (for `in`, a comma-separated list). */
  value: string;
}

/** Pagination plus optional server-side sort and filters for a list endpoint. */
export interface ListQuery {
  /** Page size (1–1000). Defaults to 20. */
  limit?: number;
  /** Number of records to skip. Defaults to 0. */
  offset?: number;
  /** Single-column sort directive, or null/undefined for the server default order. */
  sort?: SortSpec | null;
  /** Filter directives, combined with AND. */
  filters?: FilterSpec[];
}

/**
 * Build the axios request config (query params + serializer) for a list call.
 *
 * Encodes `sort` into the `s` param (`-` prefix for descending) and `filters`
 * into repeated `q` params (`field:op:value`). `indexes: null` makes axios emit
 * repeated keys without brackets (`q=a&q=b`), matching FastAPI's list-query shape.
 */
function listConfig({
  limit = 20,
  offset = 0,
  sort = null,
  filters = [],
}: ListQuery = {}): Pick<AxiosRequestConfig, "params" | "paramsSerializer"> {
  const params: Record<string, unknown> = { limit, offset };
  if (sort) params.s = `${sort.descending ? "-" : ""}${sort.field}`;
  if (filters.length > 0) params.q = filters.map((f) => `${f.field}:${f.op}:${f.value}`);
  return { params, paramsSerializer: { indexes: null } };
}

/**
 * Authenticate with username and password. On success the backend sets the
 * session and CSRF cookies and returns the logged-in user.
 */
export async function login(username: string, password: string): Promise<User> {
  return fetchEnvelope(
    apiClient.post("/api/v1/auth/login", { username, password }),
    zLoginApiV1AuthLoginPostResponse
  ) as Promise<User>;
}

/** Revoke the current session and clear the auth cookies. */
export async function logout(): Promise<void> {
  await fetchEnvelope(apiClient.post("/api/v1/auth/logout"), zLogoutApiV1AuthLogoutPostResponse);
}

/** Fetch the currently authenticated user, or throw if the session is invalid. */
export async function getMe(): Promise<User> {
  return fetchEnvelope(
    apiClient.get("/api/v1/auth/me"),
    zMeApiV1AuthMeGetResponse
  ) as Promise<User>;
}

/** Fetch all sessions for the current user (resolved from the session cookie). */
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

/** List agent skills with optional pagination, sort, and filters. */
export async function listAgentSkills(query: ListQuery = {}): Promise<AgentSkill[]> {
  return fetchEnvelope(
    apiClient.get("/api/v1/agent-skills", listConfig(query)),
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

/** List registered MCP servers with optional pagination, sort, and filters. */
export async function listMcpServers(query: ListQuery = {}): Promise<McpServer[]> {
  return fetchEnvelope(
    apiClient.get("/api/v1/mcp-servers", listConfig(query)),
    zListMcpServersApiV1McpServersGetResponse
  ) as Promise<McpServer[]>;
}

/** Fetch a single registered MCP server by ID. */
export async function getMcpServer(id: string): Promise<McpServer> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/mcp-servers/${encodeURIComponent(id)}`),
    zGetMcpServerApiV1McpServersServerIdGetResponse
  ) as Promise<McpServer>;
}

/** Register a new remote MCP server. */
export async function createMcpServer(body: McpServerCreate): Promise<McpServer> {
  return fetchEnvelope(
    apiClient.post("/api/v1/mcp-servers", body),
    zCreateMcpServerApiV1McpServersPostResponse
  ) as Promise<McpServer>;
}

/** Apply a partial update to a registered MCP server. ``headers`` replaces the full set. */
export async function updateMcpServer(id: string, body: McpServerUpdate): Promise<McpServer> {
  return fetchEnvelope(
    apiClient.patch(`/api/v1/mcp-servers/${encodeURIComponent(id)}`, body),
    zUpdateMcpServerApiV1McpServersServerIdPatchResponse
  ) as Promise<McpServer>;
}

/** Delete a registered MCP server. Fails while WorkflowTask tool bindings still reference it. */
export async function deleteMcpServer(id: string): Promise<void> {
  await fetchEnvelope(
    apiClient.delete(`/api/v1/mcp-servers/${encodeURIComponent(id)}`),
    zDeleteMcpServerApiV1McpServersServerIdDeleteResponse
  );
}

/** Fetch the tools advertised by a registered MCP server (live query to the server). */
export async function listMcpServerTools(id: string): Promise<McpToolInfo[]> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/mcp-servers/${encodeURIComponent(id)}/tools`),
    zListMcpServerToolsApiV1McpServersServerIdToolsGetResponse
  ) as Promise<McpToolInfo[]>;
}

/**
 * Search the official MCP registry for registrable (streamable-HTTP) servers.
 *
 * @param params - Optional `search` substring (matched against server names) and
 *   `cursor` for the next page (from a previous result's `nextCursor`).
 * @returns A page of registry servers plus the cursor for the next page.
 */
export async function searchMcpRegistry(
  params: { search?: string; cursor?: string } = {}
): Promise<McpRegistrySearchResult> {
  return fetchEnvelope(
    apiClient.get("/api/v1/mcp-registry", { params }),
    zSearchMcpRegistryApiV1McpRegistryGetResponse
  ) as Promise<McpRegistrySearchResult>;
}

/** List users with optional pagination, sort, and filters. */
export async function listUsers(query: ListQuery = {}): Promise<User[]> {
  return fetchEnvelope(
    apiClient.get("/api/v1/users", listConfig(query)),
    zListUsersApiV1UsersGetResponse
  ) as Promise<User[]>;
}

/** Fetch a single user by ID. */
export async function getUser(id: string): Promise<User> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/users/${encodeURIComponent(id)}`),
    zGetUserApiV1UsersUserIdGetResponse
  ) as Promise<User>;
}

/** Create a new user. */
export async function createUser(body: UserCreate): Promise<User> {
  return fetchEnvelope(
    apiClient.post("/api/v1/users", body),
    zCreateUserApiV1UsersPostResponse
  ) as Promise<User>;
}

/** Apply a partial update to a user. A blank password leaves it unchanged. */
export async function updateUser(id: string, body: UserUpdate): Promise<User> {
  return fetchEnvelope(
    apiClient.patch(`/api/v1/users/${encodeURIComponent(id)}`, body),
    zUpdateUserApiV1UsersUserIdPatchResponse
  ) as Promise<User>;
}

/** Delete a user by ID. */
export async function deleteUser(id: string): Promise<void> {
  await fetchEnvelope(
    apiClient.delete(`/api/v1/users/${encodeURIComponent(id)}`),
    zDeleteUserApiV1UsersUserIdDeleteResponse
  );
}

/** Join a user's first and last name into a single display string. */
export function formatUserName(user: Pick<User, "firstName" | "lastName">): string {
  return `${user.firstName} ${user.lastName}`.trim();
}

/**
 * Build the URL serving a user's uploaded avatar image, or `null` when the user
 * has no custom avatar (callers then render a generated default).
 *
 * The `avatarUpdatedAt` timestamp is appended as a cache-busting query so a
 * freshly uploaded image replaces any previously cached one.
 */
export function avatarUrl(user: Pick<User, "id" | "avatarUpdatedAt">): string | null {
  if (!user.avatarUpdatedAt) return null;
  const version = encodeURIComponent(user.avatarUpdatedAt);
  return `${API_BASE}/api/v1/users/${encodeURIComponent(user.id)}/avatar?v=${version}`;
}

/**
 * Upload (or replace) a user's custom avatar image and return the updated user.
 *
 * The file is sent as multipart form data; the `Content-Type` is cleared so the
 * browser sets it with the correct multipart boundary.
 */
export async function uploadUserAvatar(id: string, file: File): Promise<User> {
  const form = new FormData();
  form.append("file", file);
  return fetchEnvelope(
    apiClient.put(`/api/v1/users/${encodeURIComponent(id)}/avatar`, form, {
      headers: { "Content-Type": null },
    }),
    zUploadUserAvatarApiV1UsersUserIdAvatarPutResponse
  ) as Promise<User>;
}

/** Remove a user's custom avatar, reverting them to the generated default. */
export async function deleteUserAvatar(id: string): Promise<User> {
  return fetchEnvelope(
    apiClient.delete(`/api/v1/users/${encodeURIComponent(id)}/avatar`),
    zDeleteUserAvatarApiV1UsersUserIdAvatarDeleteResponse
  ) as Promise<User>;
}

/**
 * Resolve a set of user IDs to their display names ("First Last").
 *
 * Each unique ID is fetched individually via {@link getUser} (which resolves
 * soft-deleted users too), so names still render for users that have been
 * soft-deleted. IDs that cannot be fetched are omitted, letting callers fall
 * back to the raw ID.
 */
export async function getUserNames(ids: Iterable<string>): Promise<Map<string, string>> {
  const unique = [...new Set([...ids].filter(Boolean))];
  const entries = await Promise.all(
    unique.map(async (id): Promise<[string, string] | null> => {
      try {
        return [id, formatUserName(await getUser(id))];
      } catch {
        return null;
      }
    })
  );
  return new Map(entries.filter((e): e is [string, string] => e !== null));
}

/** List workflows with optional pagination, sort, and filters. */
export async function listWorkflows(query: ListQuery = {}): Promise<Workflow[]> {
  return fetchEnvelope(
    apiClient.get("/api/v1/workflows", listConfig(query)),
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

/**
 * Fetch the chat history of a WorkflowSession's ADK session.
 *
 * Unlike {@link getSessionMessages}, the history is keyed by the workflow
 * session's owner on the backend, so any viewer (for example a designated
 * approver) sees the same conversation instead of a separate, empty session.
 */
export async function getWorkflowSessionMessages(wsId: string): Promise<Message[]> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/workflow-sessions/${encodeURIComponent(wsId)}/messages`),
    zGetWorkflowSessionMessagesApiV1WorkflowSessionsWsIdMessagesGetResponse
  ) as Promise<Message[]>;
}

/** List WorkflowSession records (newest first) with optional pagination, sort, and filters. */
export async function listWorkflowSessions(query: ListQuery = {}): Promise<WorkflowSession[]> {
  return fetchEnvelope(
    apiClient.get("/api/v1/workflow-sessions", listConfig(query)),
    zListWorkflowSessionsApiV1WorkflowSessionsGetResponse
  ) as Promise<WorkflowSession[]>;
}

/** Delete a WorkflowSession by ID, along with its tasks and ADK chat session. */
export async function deleteWorkflowSession(id: string): Promise<void> {
  await fetchEnvelope(
    apiClient.delete(`/api/v1/workflow-sessions/${encodeURIComponent(id)}`),
    zDeleteWorkflowSessionApiV1WorkflowSessionsWsIdDeleteResponse
  );
}

/**
 * List the WorkflowTasks belonging to the given WorkflowSession (position ASC by
 * default) with optional pagination, sort, and filters.
 */
export async function listWorkflowTasks(
  workflowSessionId: string,
  query: ListQuery = {}
): Promise<WorkflowTask[]> {
  return fetchEnvelope(
    apiClient.get(
      `/api/v1/workflow-sessions/${encodeURIComponent(workflowSessionId)}/workflow-tasks`,
      listConfig(query)
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
 * Fetch the current user's notifications (newest first). When ``unreadOnly`` is
 * true only unread notifications are returned, which the toolbar bell uses to
 * compute its unread badge.
 */
export async function listNotifications(
  unreadOnly = false,
  limit = 20,
  offset = 0
): Promise<Notification[]> {
  return fetchEnvelope(
    apiClient.get("/api/v1/notifications", {
      params: { unread_only: unreadOnly, limit, offset },
    }),
    zListNotificationsApiV1NotificationsGetResponse
  ) as Promise<Notification[]>;
}

/** Mark a single notification as read and return the updated record. */
export async function markNotificationRead(id: string): Promise<Notification> {
  return fetchEnvelope(
    apiClient.patch(`/api/v1/notifications/${encodeURIComponent(id)}`),
    zMarkNotificationReadApiV1NotificationsNotificationIdPatchResponse
  ) as Promise<Notification>;
}

/** List approval requests (newest first) with optional pagination, sort, and filters. */
export async function listApprovals(query: ListQuery = {}): Promise<Approval[]> {
  return fetchEnvelope(
    apiClient.get("/api/v1/approvals", listConfig(query)),
    zListApprovalsApiV1ApprovalsGetResponse
  ) as Promise<Approval[]>;
}

/** Fetch a single approval request by ID. */
export async function getApproval(id: string): Promise<Approval> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/approvals/${encodeURIComponent(id)}`),
    zGetApprovalApiV1ApprovalsApprovalIdGetResponse
  ) as Promise<Approval>;
}

/**
 * Resolve an approval request, recording the decision and an optional comment.
 * Used by the in-chat approval controls to write the approver's choice directly.
 */
export async function resolveApproval(
  id: string,
  status: ApprovalStatus,
  response?: string
): Promise<Approval> {
  return fetchEnvelope(
    apiClient.patch(`/api/v1/approvals/${encodeURIComponent(id)}`, { status, response }),
    zResolveApprovalApiV1ApprovalsApprovalIdPatchResponse
  ) as Promise<Approval>;
}

/**
 * HttpAgent variant that sends the auth session cookie and the CSRF token with
 * each streaming request. The agent endpoints are POSTs, so they need both the
 * cookie (`credentials: "include"`) and the double-submit `X-CSRF-Token` header.
 */
class CredentialedHttpAgent extends HttpAgent {
  /** Augment the base fetch config with credentials and the CSRF header. */
  protected requestInit(input: Parameters<HttpAgent["requestInit"]>[0]): RequestInit {
    const init = super.requestInit(input);
    const csrf = readCookie(CSRF_COOKIE_NAME);
    return {
      ...init,
      credentials: "include",
      headers: {
        ...(init.headers as Record<string, string> | undefined),
        ...(csrf ? { [CSRF_HEADER_NAME]: csrf } : {}),
      },
    };
  }
}

/**
 * Create an HttpAgent for the general chat endpoint, pre-configured with the A2UI middleware
 * so the agent can render interactive surfaces via the RENDER_A2UI tool.
 */
export function createChatAgent(sessionId: string): HttpAgent {
  const agent = new CredentialedHttpAgent({
    url: `${API_BASE}/api/v1/agent`,
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

/**
 * Create an HttpAgent scoped to a specific workflow session endpoint, pre-configured
 * with the A2UI middleware so the agent can render interactive surfaces.
 */
export function createWorkflowSessionAgent(
  workflowSessionId: string,
  sessionId: string
): HttpAgent {
  const agent = new CredentialedHttpAgent({
    url: `${API_BASE}/api/v1/workflow-sessions/${encodeURIComponent(workflowSessionId)}/agent`,
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
