import { type A2UIInlineCatalogSchema, A2UIMiddleware } from "@ag-ui/a2ui-middleware";
import { HttpAgent } from "@ag-ui/client";
import type { Message } from "@ag-ui/core";
import { client } from "@/generated/api/client.gen";
import * as sdk from "@/generated/api/sdk.gen";
import type {
  AgentSkillContent,
  AgentSkillCreate,
  AgentSkillRead as AgentSkillModel,
  AgentSkillUpdate,
  ApiError,
  ApiMeta,
  Approval as ApprovalModel,
  ApprovalRead as ApprovalReadModel,
  ApprovalStatus,
  ApprovalUpdate,
  ApprovedCall,
  AvatarConfig,
  CertificateGrant,
  ExecuteWorkflowRequest,
  GenerateWorkflowRequest,
  ImpersonationEventRead,
  LoginRequest,
  McpCommand,
  McpRegistryEnvVar,
  McpRegistryHeader,
  McpRegistrySearchResult,
  McpRegistryServerEntry,
  McpServerCreate,
  McpServerRead as McpServerModel,
  McpServerUpdate,
  McpToolCertificateRead,
  McpToolInfo,
  McpToolInvocation as McpToolInvocationModel,
  McpToolMockCreate,
  McpToolMockRead as McpToolMockModel,
  McpToolMockUpdate,
  McpTransport,
  MockResponse,
  MockResponseKind,
  Notification as NotificationModel,
  NotificationType,
  NotificationUpdate,
  OutboundEmailRead as OutboundEmailModel,
  SecretCreate,
  SecretRead as SecretModel,
  SecretType,
  SecretUpdate,
  SessionFileRead as SessionFileModel,
  SessionFileOrigin,
  Session as SessionModel,
  SkillSyncStatus,
  SmtpSecurity,
  SystemSettingsRead as SystemSettingsModel,
  SystemSettingsUpdate,
  TagColor,
  TagCreate,
  Tag as TagModel,
  TagUpdate,
  TenantCreate,
  Tenant as TenantModel,
  TenantUpdate,
  ToolBinding,
  UserCreate,
  UserGroupCreate,
  UserGroupRead as UserGroupModel,
  UserGroupUpdate,
  UserRead as UserReadModel,
  UserUpdate,
  WorkflowDesignSource,
  WorkflowExecution as WorkflowExecutionModel,
  WorkflowExecutionStatus,
  WorkflowRead as WorkflowModel,
  WorkflowStatus,
  WorkflowTaskRead as WorkflowTaskModel,
  WorkflowTaskStatus,
  WorkflowTaskTemplateCreate,
  WorkflowTaskTemplateRead as WorkflowTaskTemplateModel,
  WorkflowTaskTemplateUpdate,
  WorkflowTaskUpdate,
  WorkflowUpdate,
} from "@/generated/api/types.gen";
import { store } from "@/store";
import { showToast } from "@/store/toastSlice";
import basicCatalogJson from "../generated/basic_catalog.json";
import { A2UI_CATALOG_ID } from "./a2uiCatalogId";

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
/**
 * Header carrying the tenant a super_admin has selected to act as (see the
 * tenant switcher in `AppHeader`). Ignored server-side for a tenant-scoped
 * user, so it's safe to always attach when a selection exists.
 */
const TENANT_HEADER_NAME = "X-Tenant-Id";
/**
 * Header carrying the user id an admin/super_admin is impersonating (see
 * the impersonation indicator in `AppHeader`). Re-validated by the backend
 * on every request, so a stale value is harmless -- it silently falls back
 * to the real user rather than failing the request.
 */
const IMPERSONATE_HEADER_NAME = "X-Impersonate-User-Id";
/** HTTP methods that mutate state and therefore require a CSRF token. */
const UNSAFE_METHODS = new Set(["post", "put", "patch", "delete"]);

/** Read a cookie value by name from `document.cookie`, or `null` when absent. */
function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((row) => row.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

/**
 * Wraps the platform `fetch` so two identical GETs in flight at once share one
 * network request instead of the backend seeing it twice. The main case this
 * guards against is a list page's mount effect firing twice with identical
 * params -- e.g. under React StrictMode's dev-only mount/cleanup/remount cycle
 * -- but it also covers two independent components (the tenant switcher and
 * the tenants admin page) requesting the same resource at once. Entries are
 * removed as soon as the request settles, so this shares only concurrent
 * requests -- it is not a cache and never serves stale data to a later call.
 * Each awaiter gets its own clone, since a `Response` body reads once.
 */
const inFlightGets = new Map<string, Promise<Response>>();
async function dedupingFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const request = input instanceof Request ? input : new Request(input, init);
  if (request.method !== "GET") return fetch(request);
  const key = request.url;
  let pending = inFlightGets.get(key);
  if (!pending) {
    pending = fetch(request).finally(() => inFlightGets.delete(key));
    inFlightGets.set(key, pending);
  }
  return (await pending).clone();
}

client.setConfig({
  baseUrl: API_BASE,
  credentials: "include",
  fetch: dedupingFetch,
  // Repeated keys without brackets (`q=a&q=b`), matching FastAPI's list-query shape.
  querySerializer: { array: { explode: true, style: "form" } },
});

client.interceptors.request.use((request) => {
  if (UNSAFE_METHODS.has(request.method.toLowerCase())) {
    const token = readCookie(CSRF_COOKIE_NAME);
    if (token) request.headers.set(CSRF_HEADER_NAME, token);
  }
  const tenantId = store.getState().auth.selectedTenantId;
  if (tenantId) request.headers.set(TENANT_HEADER_NAME, tenantId);
  const impersonatedUserId = store.getState().auth.impersonatedUserId;
  if (impersonatedUserId) request.headers.set(IMPERSONATE_HEADER_NAME, impersonatedUserId);
  return request;
});

/** Re-export the generated envelope types so call sites do not import from ``@/generated``. */
export type { ApiError, ApiMeta };

/** Generic API response envelope wrapping typed data or an error body. */
export interface ApiResponse<T> {
  meta: ApiMeta;
  data: T | null;
  error: ApiError | null;
}

/** Error thrown when an API call fails: an error envelope, a non-2xx status, or no response at all. */
export class ApiClientError extends Error {
  constructor(
    public code: string,
    message: string,
    public details?: unknown,
    public requestId?: string,
    /** HTTP status of the response, when one arrived. */
    public status?: number
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

/** Extract a user-facing message from a failed API call. */
export function getApiErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Something went wrong. Please try again.";
}

/** Show a failed API call's message as a red toast. */
function reportApiError(error: unknown): void {
  store.dispatch(showToast({ message: getApiErrorMessage(error), variant: "error" }));
}

/** Backend error code for `ForbiddenError` -- see `backend/repositories/exceptions.py`. */
const FORBIDDEN_CODE = "FORBIDDEN";
const APPROVAL_ALREADY_RESOLVED_CODE = "APPROVAL_ALREADY_RESOLVED";

/**
 * True when `error` is the backend's `ForbiddenError` (HTTP 403, envelope
 * `error.code === "FORBIDDEN"`) -- an authenticated caller who lacks the
 * specific role/ownership grant for an otherwise-existing record. Distinct
 * from a 404 (the record doesn't exist, or isn't visible to this tenant),
 * which this deliberately does not match.
 */
export function isForbiddenError(error: unknown): boolean {
  return error instanceof ApiClientError && error.code === FORBIDDEN_CODE;
}

/**
 * True when `error` is the backend's `ApprovalAlreadyResolvedError` (HTTP 409,
 * envelope `error.code === "APPROVAL_ALREADY_RESOLVED"`) -- someone else
 * decided this approval first. Only reachable for a group-addressed approval,
 * where several eligible members can hold the controls at the same time, so
 * the UI reports "already decided" rather than a generic failure.
 */
export function isApprovalAlreadyResolvedError(error: unknown): boolean {
  return error instanceof ApiClientError && error.code === APPROVAL_ALREADY_RESOLVED_CODE;
}

/** Per-call options accepted by the API functions below. */
export interface CallOptions {
  /**
   * When true, skip the global error toast for a FORBIDDEN (403) failure on
   * this specific request -- the caller renders its own access-denied state
   * instead. Any other failure, including a different 403, still toasts
   * normally. See {@link isForbiddenError}.
   */
  suppressForbiddenToast?: boolean;
}

/**
 * Options for a page's initial-load GET that renders its own
 * {@link isForbiddenError}-driven access-denied state, so the generic error
 * toast should stay silent for a FORBIDDEN failure on that specific request.
 */
export const SUPPRESS_FORBIDDEN_TOAST: CallOptions = { suppressForbiddenToast: true };

/** What a generated SDK call resolves to: the parsed envelope on success, else the error and its response. */
interface SdkResult<T> {
  data?: { meta: ApiMeta; data?: T | null; error?: ApiError | null };
  error?: unknown;
  response?: Response;
}

/**
 * Turn a generated SDK call into the envelope's `data`, or throw an
 * {@link ApiClientError}.
 *
 * Every failure funnels through here: a network error, a non-2xx status (whose
 * body is the same envelope with `error` set), and a 2xx whose envelope still
 * carries an error. A 401 anywhere but the login request means the session
 * expired, so the browser is sent to the login page instead of shown a toast
 * that would only flash mid-navigation.
 */
async function unwrap<T>(call: Promise<SdkResult<T>>, options?: CallOptions): Promise<T> {
  const { data: env, error, response } = await call;
  if (env && !env.error) return env.data as T;
  if (env === undefined && response?.ok) throw error;
  let failure: ApiClientError;
  if (!response) {
    failure = new ApiClientError(
      "NETWORK_ERROR",
      "Unable to reach the server. Please check your connection and try again."
    );
  } else {
    const body = (env ?? error) as SdkResult<unknown>["data"] | null;
    const err = body?.error ?? null;
    failure = new ApiClientError(
      err?.code ?? `HTTP_${response.status}`,
      err?.message ?? `Request failed with status ${response.status}`,
      err?.details,
      body?.meta?.requestId,
      response.status
    );
  }
  const isSessionExpiry =
    typeof window !== "undefined" &&
    failure.status === 401 &&
    !response?.url.endsWith("/auth/login") &&
    window.location.pathname !== "/login";
  if (isSessionExpiry) {
    window.location.assign("/login");
  } else if (!(options?.suppressForbiddenToast && isForbiddenError(failure))) {
    reportApiError(failure);
  }
  throw failure;
}

type AuditedKeys = "id" | "createdAt" | "updatedAt" | "createdBy" | "updatedBy";
type WithAudit<T extends Partial<Record<AuditedKeys, unknown>>> = T &
  Required<Pick<T, AuditedKeys>>;

export type AgentSkill = WithAudit<AgentSkillModel>;
export type Approval = WithAudit<ApprovalModel>;
/**
 * One approval with its `approvedCalls` typed.
 *
 * `GET /approvals/{id}` serializes through the backend's `ApprovalRead`, which
 * restores the declaration's shape that the table class stores as plain JSON.
 * The list endpoint returns {@link Approval}, where `approvedCalls` is opaque —
 * a declaration is detail, and nothing filters or sorts on it.
 */
export type ApprovalDetail = WithAudit<ApprovalReadModel>;
export type McpToolCertificate = WithAudit<McpToolCertificateRead>;
export type McpServer = WithAudit<McpServerModel>;
export type McpToolMock = WithAudit<McpToolMockModel>;
export type McpToolInvocation = WithAudit<McpToolInvocationModel>;
export type Notification = WithAudit<NotificationModel>;
export type OutboundEmail = WithAudit<OutboundEmailModel>;
/**
 * One recorded impersonation session.
 *
 * Not wrapped in `WithAudit` like the rows above: the table skips the shared
 * audit columns entirely, so there is no `createdBy`/`updatedBy` to require —
 * `impersonatorId` is who acted, and `startedAt` is when.
 */
export type ImpersonationEvent = ImpersonationEventRead;
export type Secret = WithAudit<SecretModel>;
export type SystemSettings = WithAudit<SystemSettingsModel>;
export type Tag = WithAudit<TagModel>;
export type Tenant = WithAudit<TenantModel>;
export type User = WithAudit<UserReadModel>;
export type UserGroup = WithAudit<UserGroupModel>;
export type Workflow = WithAudit<WorkflowModel>;
export type WorkflowExecution = WithAudit<WorkflowExecutionModel>;
export type WorkflowTask = WithAudit<WorkflowTaskModel>;
export type WorkflowTaskTemplate = WithAudit<WorkflowTaskTemplateModel>;
export type Session = SessionModel;
/** One file attached to a workflow session, by a participant or by the agent. */
export type SessionFile = WithAudit<SessionFileModel>;
export type {
  AgentSkillContent,
  AgentSkillCreate,
  AgentSkillUpdate,
  ApprovalStatus,
  ApprovalUpdate,
  ApprovedCall,
  AvatarConfig,
  CertificateGrant,
  GenerateWorkflowRequest,
  ImpersonationEventRead,
  LoginRequest,
  McpCommand,
  McpRegistryEnvVar,
  McpRegistryHeader,
  McpRegistrySearchResult,
  McpRegistryServerEntry,
  McpServerCreate,
  McpServerUpdate,
  McpToolCertificateRead,
  McpToolInfo,
  McpToolMockCreate,
  McpToolMockUpdate,
  McpTransport,
  MockResponse,
  MockResponseKind,
  NotificationType,
  SecretCreate,
  SecretType,
  SecretUpdate,
  SessionFileOrigin,
  SkillSyncStatus,
  SmtpSecurity,
  SystemSettingsUpdate,
  TagColor,
  TagCreate,
  TagUpdate,
  TenantCreate,
  TenantUpdate,
  ToolBinding,
  UserCreate,
  UserGroupCreate,
  UserGroupUpdate,
  UserUpdate,
  WorkflowDesignSource,
  WorkflowExecutionStatus,
  WorkflowStatus,
  WorkflowTaskStatus,
  WorkflowTaskTemplateCreate,
  WorkflowTaskTemplateUpdate,
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
  /**
   * Tag ids a record must carry. A record must carry every id listed, so
   * adding one narrows the result. Serialized as a repeated `tag` parameter,
   * separate from `filters`: tags are not a column of any resource, so the
   * `field:op:value` grammar cannot express them.
   */
  tagIds?: string[];
}

/**
 * Build the query params for a list call: `sort` becomes the `s` param (`-`
 * prefix for descending) and `filters` repeated `q` params (`field:op:value`).
 */
function listQuery({
  limit = 20,
  offset = 0,
  sort = null,
  filters = [],
  tagIds = [],
}: ListQuery = {}) {
  return {
    limit,
    offset,
    s: sort ? `${sort.descending ? "-" : ""}${sort.field}` : undefined,
    q: filters.length > 0 ? filters.map((f) => `${f.field}:${f.op}:${f.value}`) : undefined,
    tag: tagIds.length > 0 ? tagIds : undefined,
  };
}

/**
 * Authenticate with username, password, and optional tenant name. On success
 * the backend sets the session and CSRF cookies and returns the logged-in
 * user. `tenantName` disambiguates a tenant-scoped user's username and must
 * be omitted for a platform-scoped user (e.g. `root`).
 */
export async function login(
  username: string,
  password: string,
  tenantName?: string
): Promise<User> {
  return unwrap(
    sdk.loginApiV1AuthLoginPost({
      body: {
        username,
        password,
        tenantName: tenantName || undefined,
      },
    })
  ) as Promise<User>;
}

/** Revoke the current session and clear the auth cookies. */
export async function logout(): Promise<void> {
  await unwrap(sdk.logoutApiV1AuthLogoutPost());
}

/**
 * Result of `getMe`/`login`/the impersonate start-stop endpoints: the
 * effective user, plus the real actor when an impersonation is active.
 */
export interface Me {
  user: User;
  impersonatedBy: User | null;
}

/** Fetch the currently authenticated (effective) user, or throw if the session is invalid. */
export async function getMe(): Promise<Me> {
  return unwrap(sdk.meApiV1AuthMeGet()) as Promise<Me>;
}

/**
 * Start impersonating another user. The backend enforces eligibility (role,
 * tenant, and target-role restrictions); a rejection surfaces as a thrown
 * `ApiClientError` with the usual `FORBIDDEN`/`NOT_FOUND` codes.
 */
export async function startImpersonation(targetUserId: string): Promise<Me> {
  return unwrap(
    sdk.startImpersonationApiV1AuthImpersonatePost({ body: { targetUserId } })
  ) as Promise<Me>;
}

/** Stop impersonating, if currently active; a no-op (never throws for this reason) otherwise. */
export async function stopImpersonation(): Promise<Me> {
  return unwrap(sdk.stopImpersonationApiV1AuthImpersonateDelete()) as Promise<Me>;
}

/** Fetch all sessions for the current user (resolved from the session cookie). */
export async function listSessions(): Promise<Session[]> {
  return unwrap(sdk.listSessionsApiV1SessionsGet()) as Promise<Session[]>;
}

/** Fetch a single session by ID. */
export async function getSession(sessionId: string): Promise<Session> {
  return unwrap(
    sdk.getSessionApiV1SessionsSessionIdGet({ path: { session_id: sessionId } })
  ) as Promise<Session>;
}

/** Fetch the full message history for a session (used to restore conversation state). */
export async function getSessionMessages(sessionId: string): Promise<Message[]> {
  return unwrap(
    sdk.getSessionMessagesApiV1SessionsSessionIdMessagesGet({ path: { session_id: sessionId } })
  ) as Promise<Message[]>;
}

/** Delete a session and its associated message history. */
export async function deleteSession(sessionId: string): Promise<void> {
  await unwrap(sdk.deleteSessionApiV1SessionsSessionIdDelete({ path: { session_id: sessionId } }));
}

/** List agent skills with optional pagination, sort, and filters. */
export async function listAgentSkills(query: ListQuery = {}): Promise<AgentSkill[]> {
  return unwrap(sdk.listAgentSkillsApiV1AgentSkillsGet({ query: listQuery(query) })) as Promise<
    AgentSkill[]
  >;
}

/** Fetch a single agent skill by ID. */
export async function getAgentSkill(id: string, options?: CallOptions): Promise<AgentSkill> {
  return unwrap(
    sdk.getAgentSkillApiV1AgentSkillsSkillIdGet({ path: { skill_id: id } }),
    options
  ) as Promise<AgentSkill>;
}

/** Fetch the raw SKILL.md content of an agent skill's published revision. */
export async function getAgentSkillContent(id: string): Promise<AgentSkillContent> {
  return unwrap(
    sdk.getAgentSkillContentApiV1AgentSkillsSkillIdContentGet({ path: { skill_id: id } })
  ) as Promise<AgentSkillContent>;
}

/** Create a new agent skill. */
export async function createAgentSkill(body: AgentSkillCreate): Promise<AgentSkill> {
  return unwrap(sdk.createAgentSkillApiV1AgentSkillsPost({ body: body })) as Promise<AgentSkill>;
}

/** Apply a partial update to an agent skill. */
export async function updateAgentSkill(id: string, body: AgentSkillUpdate): Promise<AgentSkill> {
  return unwrap(
    sdk.updateAgentSkillApiV1AgentSkillsSkillIdPatch({ path: { skill_id: id }, body: body })
  ) as Promise<AgentSkill>;
}

/**
 * Re-clone an agent skill's repository at its current remote HEAD.
 *
 * How a skill picks up upstream changes, and how a failed registration clone is
 * retried. The clone runs in the background: the returned skill is already
 * marked `pending`, and the caller polls until it settles on `ready` or
 * `failed`.
 */
export async function pullAgentSkill(id: string): Promise<AgentSkill> {
  return unwrap(
    sdk.pullAgentSkillApiV1AgentSkillsSkillIdPullPost({ path: { skill_id: id } })
  ) as Promise<AgentSkill>;
}

/** Delete an agent skill by ID. */
export async function deleteAgentSkill(id: string): Promise<void> {
  await unwrap(sdk.deleteAgentSkillApiV1AgentSkillsSkillIdDelete({ path: { skill_id: id } }));
}

/** List registered MCP servers with optional pagination, sort, and filters. */
export async function listMcpServers(query: ListQuery = {}): Promise<McpServer[]> {
  return unwrap(sdk.listMcpServersApiV1McpServersGet({ query: listQuery(query) })) as Promise<
    McpServer[]
  >;
}

/** Fetch a single registered MCP server by ID. */
export async function getMcpServer(id: string, options?: CallOptions): Promise<McpServer> {
  return unwrap(
    sdk.getMcpServerApiV1McpServersServerIdGet({ path: { server_id: id } }),
    options
  ) as Promise<McpServer>;
}

/** Register a new remote MCP server. */
export async function createMcpServer(body: McpServerCreate): Promise<McpServer> {
  return unwrap(sdk.createMcpServerApiV1McpServersPost({ body: body })) as Promise<McpServer>;
}

/** Apply a partial update to a registered MCP server. ``headers`` replaces the full set. */
export async function updateMcpServer(id: string, body: McpServerUpdate): Promise<McpServer> {
  return unwrap(
    sdk.updateMcpServerApiV1McpServersServerIdPatch({ path: { server_id: id }, body: body })
  ) as Promise<McpServer>;
}

/** Delete a registered MCP server. Fails while WorkflowTask tool bindings still reference it. */
export async function deleteMcpServer(id: string): Promise<void> {
  await unwrap(sdk.deleteMcpServerApiV1McpServersServerIdDelete({ path: { server_id: id } }));
}

/** List the tool mocks registered in the tenant (createdAt DESC by default). */
export async function listMcpToolMocks(query: ListQuery = {}): Promise<McpToolMock[]> {
  return unwrap(sdk.listMcpToolMocksApiV1McpToolMocksGet({ query: listQuery(query) })) as Promise<
    McpToolMock[]
  >;
}

/** Fetch a single tool mock by ID. */
export async function getMcpToolMock(id: string, options?: CallOptions): Promise<McpToolMock> {
  return unwrap(
    sdk.getMcpToolMockApiV1McpToolMocksMockIdGet({ path: { mock_id: id } }),
    options
  ) as Promise<McpToolMock>;
}

/** Register a new tool mock. */
export async function createMcpToolMock(body: McpToolMockCreate): Promise<McpToolMock> {
  return unwrap(sdk.createMcpToolMockApiV1McpToolMocksPost({ body: body })) as Promise<McpToolMock>;
}

/** Apply a partial update to a tool mock. `responses` replaces the full list. */
export async function updateMcpToolMock(id: string, body: McpToolMockUpdate): Promise<McpToolMock> {
  return unwrap(
    sdk.updateMcpToolMockApiV1McpToolMocksMockIdPatch({ path: { mock_id: id }, body: body })
  ) as Promise<McpToolMock>;
}

/**
 * Delete a tool mock. Runs already started keep their own snapshot of it, so
 * deleting one never changes how an existing run behaves.
 */
export async function deleteMcpToolMock(id: string): Promise<void> {
  await unwrap(sdk.deleteMcpToolMockApiV1McpToolMocksMockIdDelete({ path: { mock_id: id } }));
}

/**
 * Replace a tool mock's tag set wholesale, returning the updated mock.
 *
 * Tags are a sub-resource of the record, so the create and detail forms write
 * them with this call rather than through the mock's own create/update body.
 */
export async function setMcpToolMockTags(id: string, tagIds: string[]): Promise<McpToolMock> {
  return unwrap(
    sdk.setMcpToolMockTagsApiV1McpToolMocksMockIdTagsPut({
      path: { mock_id: id },
      body: { tagIds },
    })
  ) as Promise<McpToolMock>;
}

/**
 * List the MCP tool-call decisions recorded for one workflow execution.
 *
 * Only calls that reached the MCP gateway appear here — allowed ones that went
 * upstream and denied ones a policy vetoed. A call answered by a tool mock never
 * reaches the gateway, so it shows in the chat transcript instead.
 */
export async function listWorkflowExecutionToolInvocations(
  executionId: string,
  query: ListQuery = {}
): Promise<McpToolInvocation[]> {
  return unwrap(
    sdk.listWorkflowExecutionToolInvocationsApiV1WorkflowExecutionsExecutionIdToolInvocationsGet({
      path: { execution_id: executionId },
      query: listQuery(query),
    })
  ) as Promise<McpToolInvocation[]>;
}

/**
 * List every MCP tool-call decision recorded in the tenant (createdAt DESC by default).
 *
 * The audit-screen counterpart of {@link listWorkflowExecutionToolInvocations},
 * which narrows to one run. Admin-only, since it spans every run in the tenant.
 */
export async function listMcpToolInvocations(query: ListQuery = {}): Promise<McpToolInvocation[]> {
  return unwrap(
    sdk.listMcpToolInvocationsApiV1McpToolInvocationsGet({ query: listQuery(query) })
  ) as Promise<McpToolInvocation[]>;
}

/** Fetch a single recorded MCP tool-call decision by ID. */
export async function getMcpToolInvocation(
  id: string,
  options?: CallOptions
): Promise<McpToolInvocation> {
  return unwrap(
    sdk.getMcpToolInvocationApiV1McpToolInvocationsInvocationIdGet({ path: { invocation_id: id } }),
    options
  ) as Promise<McpToolInvocation>;
}

/**
 * List recorded impersonation sessions (startedAt DESC by default).
 *
 * Rows are scoped by the impersonated user's tenant, so an admin sees the
 * sessions that touched their own tenant's accounts — including ones a
 * platform-scoped super admin opened.
 */
export async function listImpersonationEvents(
  query: ListQuery = {}
): Promise<ImpersonationEvent[]> {
  return unwrap(
    sdk.listImpersonationEventsApiV1ImpersonationEventsGet({ query: listQuery(query) })
  ) as Promise<ImpersonationEvent[]>;
}

/** Fetch a single recorded impersonation session by ID. */
export async function getImpersonationEvent(
  id: string,
  options?: CallOptions
): Promise<ImpersonationEvent> {
  return unwrap(
    sdk.getImpersonationEventApiV1ImpersonationEventsEventIdGet({ path: { event_id: id } }),
    options
  ) as Promise<ImpersonationEvent>;
}

/**
 * List the certificates authorizing tasks' MCP tool calls (createdAt DESC by default).
 *
 * Every proxied tool call is backed by one of these, so the list spans both
 * grant kinds: the ones approvers granted and the ones a run's initiator granted
 * itself. Each row's `allowedTools` is parsed back out of the signed
 * certificate, so it can never disagree with what was actually authorized. Key
 * material is never part of the response.
 */
export async function listMcpToolCertificates(
  query: ListQuery = {}
): Promise<McpToolCertificate[]> {
  return unwrap(
    sdk.listMcpToolCertificatesApiV1McpToolCertificatesGet({ query: listQuery(query) })
  ) as Promise<McpToolCertificate[]>;
}

/**
 * Fetch a single tool certificate by its own ID.
 *
 * Distinct from {@link listApprovalCertificates}, which reaches approval-backed
 * records through the approval they were issued under and cannot see the ones a
 * run's initiator granted itself.
 */
export async function getMcpToolCertificateById(
  id: string,
  options?: CallOptions
): Promise<McpToolCertificate> {
  return unwrap(
    sdk.getMcpToolCertificateByIdApiV1McpToolCertificatesCertificateIdGet({
      path: { certificate_id: id },
    }),
    options
  ) as Promise<McpToolCertificate>;
}

/** List the outgoing notification-email queue (createdAt DESC by default). */
export async function listOutboundEmails(query: ListQuery = {}): Promise<OutboundEmail[]> {
  return unwrap(
    sdk.listOutboundEmailsApiV1OutboundEmailsGet({ query: listQuery(query) })
  ) as Promise<OutboundEmail[]>;
}

/** Fetch a single queued or delivered notification email by ID. */
export async function getOutboundEmail(id: string, options?: CallOptions): Promise<OutboundEmail> {
  return unwrap(
    sdk.getOutboundEmailApiV1OutboundEmailsEmailIdGet({ path: { email_id: id } }),
    options
  ) as Promise<OutboundEmail>;
}

/** Fetch the tools advertised by a registered MCP server (live query to the server). */
export async function listMcpServerTools(id: string): Promise<McpToolInfo[]> {
  return unwrap(
    sdk.listMcpServerToolsApiV1McpServersServerIdToolsGet({ path: { server_id: id } })
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
  return unwrap(
    sdk.searchMcpRegistryApiV1McpRegistryGet({ query: params })
  ) as Promise<McpRegistrySearchResult>;
}

/** List secrets with optional pagination, sort, and filters. Values are never returned. */
export async function listSecrets(query: ListQuery = {}): Promise<Secret[]> {
  return unwrap(sdk.listSecretsApiV1SecretsGet({ query: listQuery(query) })) as Promise<Secret[]>;
}

/** Fetch a single secret by ID. The stored value is never returned. */
export async function getSecret(id: string, options?: CallOptions): Promise<Secret> {
  return unwrap(
    sdk.getSecretApiV1SecretsSecretIdGet({ path: { secret_id: id } }),
    options
  ) as Promise<Secret>;
}

/**
 * List the entry keys of one secret. No value is ever returned.
 *
 * Unlike the `keys` field on a secret read — which only ever reports a `local`
 * secret's entries — this covers both kinds: a `vault` secret's keys are read
 * live from its KV v2 path.
 */
export async function listSecretKeys(id: string): Promise<string[]> {
  return unwrap(
    sdk.listSecretKeysApiV1SecretsSecretIdKeysGet({ path: { secret_id: id } })
  ) as Promise<string[]>;
}

/** Register a new secret: a `local` encrypted value or a `vault` KV v2 reference. */
export async function createSecret(body: SecretCreate): Promise<Secret> {
  return unwrap(sdk.createSecretApiV1SecretsPost({ body: body })) as Promise<Secret>;
}

/** Apply a partial update to a secret. Omitting `entries` keeps the stored map unchanged. */
export async function updateSecret(id: string, body: SecretUpdate): Promise<Secret> {
  return unwrap(
    sdk.updateSecretApiV1SecretsSecretIdPatch({ path: { secret_id: id }, body: body })
  ) as Promise<Secret>;
}

/** Delete a secret by ID. References to it fail lazily at their next resolution. */
export async function deleteSecret(id: string): Promise<void> {
  await unwrap(sdk.deleteSecretApiV1SecretsSecretIdDelete({ path: { secret_id: id } }));
}

/** List tags with optional pagination, sort, and filters. */
export async function listTags(query: ListQuery = {}): Promise<Tag[]> {
  return unwrap(sdk.listTagsApiV1TagsGet({ query: listQuery(query) })) as Promise<Tag[]>;
}

/** Fetch a single tag by ID. */
export async function getTag(id: string, options?: CallOptions): Promise<Tag> {
  return unwrap(sdk.getTagApiV1TagsTagIdGet({ path: { tag_id: id } }), options) as Promise<Tag>;
}

/** Register a new tag. Requires the `admin` or `developer` role. */
export async function createTag(body: TagCreate): Promise<Tag> {
  return unwrap(sdk.createTagApiV1TagsPost({ body: body })) as Promise<Tag>;
}

/**
 * Apply a partial update to a tag.
 *
 * Renaming is safe at any time: records reference a tag by id, so every record
 * carrying it picks up the new name.
 */
export async function updateTag(id: string, body: TagUpdate): Promise<Tag> {
  return unwrap(
    sdk.updateTagApiV1TagsTagIdPatch({ path: { tag_id: id }, body: body })
  ) as Promise<Tag>;
}

/** Delete a tag, detaching it from every record that carried it. */
export async function deleteTag(id: string): Promise<void> {
  await unwrap(sdk.deleteTagApiV1TagsTagIdDelete({ path: { tag_id: id } }));
}

/**
 * Replace a secret's tags wholesale. An empty array detaches every tag.
 *
 * Tags are a sub-resource rather than a field of the secret payload, so
 * creating a tagged record is a create followed by this call.
 */
export async function setSecretTags(id: string, tagIds: string[]): Promise<Secret> {
  return unwrap(
    sdk.setSecretTagsApiV1SecretsSecretIdTagsPut({ path: { secret_id: id }, body: { tagIds } })
  ) as Promise<Secret>;
}

/** Replace a workflow's tags wholesale. An empty array detaches every tag. */
export async function setWorkflowTags(id: string, tagIds: string[]): Promise<Workflow> {
  return unwrap(
    sdk.setWorkflowTagsApiV1WorkflowsWorkflowIdTagsPut({
      path: { workflow_id: id },
      body: { tagIds },
    })
  ) as Promise<Workflow>;
}

/** Replace an MCP server's tags wholesale. An empty array detaches every tag. */
export async function setMcpServerTags(id: string, tagIds: string[]): Promise<McpServer> {
  return unwrap(
    sdk.setMcpServerTagsApiV1McpServersServerIdTagsPut({
      path: { server_id: id },
      body: { tagIds },
    })
  ) as Promise<McpServer>;
}

/** Replace an agent skill's tags wholesale. An empty array detaches every tag. */
export async function setAgentSkillTags(id: string, tagIds: string[]): Promise<AgentSkill> {
  return unwrap(
    sdk.setAgentSkillTagsApiV1AgentSkillsSkillIdTagsPut({
      path: { skill_id: id },
      body: { tagIds },
    })
  ) as Promise<AgentSkill>;
}

/** List tenants with optional pagination, sort, and filters. */
export async function listTenants(query: ListQuery = {}): Promise<Tenant[]> {
  return unwrap(sdk.listTenantsApiV1TenantsGet({ query: listQuery(query) })) as Promise<Tenant[]>;
}

/** Fetch a single tenant by ID. */
export async function getTenant(id: string, options?: CallOptions): Promise<Tenant> {
  return unwrap(
    sdk.getTenantApiV1TenantsTenantIdGet({ path: { tenant_id: id } }),
    options
  ) as Promise<Tenant>;
}

/** Create a new tenant. */
export async function createTenant(body: TenantCreate): Promise<Tenant> {
  return unwrap(sdk.createTenantApiV1TenantsPost({ body: body })) as Promise<Tenant>;
}

/** Apply a partial update to a tenant. */
export async function updateTenant(id: string, body: TenantUpdate): Promise<Tenant> {
  return unwrap(
    sdk.updateTenantApiV1TenantsTenantIdPatch({ path: { tenant_id: id }, body: body })
  ) as Promise<Tenant>;
}

/** Delete a tenant by ID. Fails while any user remains assigned to it. */
export async function deleteTenant(id: string): Promise<void> {
  await unwrap(sdk.deleteTenantApiV1TenantsTenantIdDelete({ path: { tenant_id: id } }));
}

/**
 * Fetch the platform-wide system settings. `super_admin` only.
 *
 * The SMTP password is never part of the response; `smtpPasswordSet` reports
 * only whether one is stored.
 */
export async function getSystemSettings(options?: CallOptions): Promise<SystemSettings> {
  return unwrap(sdk.getSystemSettingsApiV1SystemSettingsGet(), options) as Promise<SystemSettings>;
}

/**
 * Apply a partial update to the system settings. `super_admin` only.
 *
 * Omitting `smtpPassword` — or sending it as an empty string — keeps the stored
 * password, so a blank field in the form is non-destructive.
 */
export async function updateSystemSettings(body: SystemSettingsUpdate): Promise<SystemSettings> {
  return unwrap(
    sdk.updateSystemSettingsApiV1SystemSettingsPatch({ body: body })
  ) as Promise<SystemSettings>;
}

/**
 * Send a test message with the stored SMTP settings to the caller's own address.
 *
 * The recipient is fixed server-side, so this cannot be used to relay mail
 * anywhere else.
 */
export async function sendSmtpTestEmail(): Promise<void> {
  await unwrap(sdk.sendSmtpTestEmailApiV1SystemSettingsSmtpTestPost());
}

/** List users with optional pagination, sort, and filters. */
export async function listUsers(query: ListQuery = {}): Promise<User[]> {
  return unwrap(sdk.listUsersApiV1UsersGet({ query: listQuery(query) })) as Promise<User[]>;
}

/** Fetch a single user by ID. */
export async function getUser(id: string, options?: CallOptions): Promise<User> {
  return unwrap(
    sdk.getUserApiV1UsersUserIdGet({ path: { user_id: id } }),
    options
  ) as Promise<User>;
}

/** Create a new user. */
export async function createUser(body: UserCreate): Promise<User> {
  return unwrap(sdk.createUserApiV1UsersPost({ body: body })) as Promise<User>;
}

/** Apply a partial update to a user. A blank password leaves it unchanged. */
export async function updateUser(id: string, body: UserUpdate): Promise<User> {
  return unwrap(
    sdk.updateUserApiV1UsersUserIdPatch({ path: { user_id: id }, body: body })
  ) as Promise<User>;
}

/** Delete a user by ID. */
export async function deleteUser(id: string): Promise<void> {
  await unwrap(sdk.deleteUserApiV1UsersUserIdDelete({ path: { user_id: id } }));
}

/** List user groups in the acting tenant, with optional pagination, sort, and filters. */
export async function listUserGroups(query: ListQuery = {}): Promise<UserGroup[]> {
  return unwrap(sdk.listUserGroupsApiV1UserGroupsGet({ query: listQuery(query) })) as Promise<
    UserGroup[]
  >;
}

/**
 * Fetch the acting tenant's user groups a given user belongs to.
 *
 * The read counterpart of {@link setUserGroups}. Membership is not carried on
 * the user record, so this is how a user-side screen learns which groups to
 * show without paging through every group in the tenant.
 */
export async function getUserGroupsForUser(userId: string): Promise<UserGroup[]> {
  return unwrap(
    sdk.listGroupsForUserApiV1UsersUserIdGroupsGet({ path: { user_id: userId } })
  ) as Promise<UserGroup[]>;
}

/** Fetch a single user group by ID, including its member IDs. */
export async function getUserGroup(id: string, options?: CallOptions): Promise<UserGroup> {
  return unwrap(
    sdk.getUserGroupApiV1UserGroupsGroupIdGet({ path: { group_id: id } }),
    options
  ) as Promise<UserGroup>;
}

/** Create a new user group in the acting tenant. */
export async function createUserGroup(body: UserGroupCreate): Promise<UserGroup> {
  return unwrap(sdk.createUserGroupApiV1UserGroupsPost({ body: body })) as Promise<UserGroup>;
}

/**
 * Apply a partial update to a user group.
 *
 * Omitting `memberIds` leaves membership untouched; supplying a list replaces
 * it wholesale.
 */
export async function updateUserGroup(id: string, body: UserGroupUpdate): Promise<UserGroup> {
  return unwrap(
    sdk.updateUserGroupApiV1UserGroupsGroupIdPatch({ path: { group_id: id }, body: body })
  ) as Promise<UserGroup>;
}

/** Delete a user group. Its members keep their accounts but lose its roles. */
export async function deleteUserGroup(id: string): Promise<void> {
  await unwrap(sdk.deleteUserGroupApiV1UserGroupsGroupIdDelete({ path: { group_id: id } }));
}

/**
 * Replace a user group's tag set wholesale, returning the updated group.
 *
 * Tags are a sub-resource of the group, so the create and detail forms write
 * them with this call rather than through the group's own create/update body.
 */
export async function setUserGroupTags(id: string, tagIds: string[]): Promise<UserGroup> {
  return unwrap(
    sdk.setUserGroupTagsApiV1UserGroupsGroupIdTagsPut({ path: { group_id: id }, body: { tagIds } })
  ) as Promise<UserGroup>;
}

/**
 * Replace the set of user groups a user belongs to, returning the updated user.
 *
 * The counterpart of editing a group's `memberIds`, so membership can be
 * managed from the user page as well as the group page. The returned user's
 * `groupRoles` already reflects the new membership.
 */
export async function setUserGroups(userId: string, groupIds: string[]): Promise<User> {
  return unwrap(
    sdk.setUserGroupsApiV1UsersUserIdGroupsPut({ path: { user_id: userId }, body: { groupIds } })
  ) as Promise<User>;
}

/** Join a user's first and last name into a single display string. */
export function formatUserName(user: Pick<User, "firstName" | "lastName">): string {
  return `${user.firstName} ${user.lastName}`.trim();
}

/**
 * Resolve a user's primary display name: the full name ("First Last") when
 * present, falling back to the username and finally the email.
 */
export function userDisplayName(
  user: Pick<User, "firstName" | "lastName" | "username" | "email">
): string {
  return formatUserName(user) || user.username || user.email;
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
 * The file is sent as multipart form data.
 */
export async function uploadUserAvatar(id: string, file: File): Promise<User> {
  return unwrap(
    sdk.uploadUserAvatarApiV1UsersUserIdAvatarPut({
      path: { user_id: id },
      body: { file },
    })
  ) as Promise<User>;
}

/** Remove a user's custom avatar, reverting them to the generated default. */
export async function deleteUserAvatar(id: string): Promise<User> {
  return unwrap(
    sdk.deleteUserAvatarApiV1UsersUserIdAvatarDelete({ path: { user_id: id } })
  ) as Promise<User>;
}

/**
 * Resolve a set of user IDs to their display names, in a single request.
 *
 * De-duplicates the IDs and resolves them all through
 * `POST /api/v1/users/resolve-names`, so a screen showing many user
 * references (an audit footer, a table of initiators) costs one round trip
 * rather than one per ID. Soft-deleted users still resolve, so names keep
 * rendering for the records they own.
 *
 * The server omits IDs the caller may not see, so those are simply missing
 * from the returned map and callers fall back to the raw ID. Users the caller
 * cannot see individually but whose *kind* of account is not a secret come
 * back under a fixed placeholder instead ("System User", "Super Admin").
 */
export async function getUserNames(ids: Iterable<string>): Promise<Map<string, string>> {
  const unique = [...new Set([...ids].filter(Boolean))];
  if (unique.length === 0) return new Map();
  const resolved = await unwrap(
    sdk.resolveUserNamesApiV1UsersResolveNamesPost({ body: { ids: unique } })
  );
  return new Map((resolved ?? []).map((entry) => [entry.id, entry.displayName]));
}

/**
 * Resolve a set of user IDs to their full {@link User} records.
 *
 * Each unique ID is fetched individually via {@link getUser} (which resolves
 * soft-deleted users too), so avatars and names still render for users that
 * have been soft-deleted. IDs that cannot be fetched are omitted, letting
 * callers fall back to a placeholder.
 */
export async function getUsersByIds(ids: Iterable<string>): Promise<Map<string, User>> {
  const unique = [...new Set([...ids].filter(Boolean))];
  const entries = await Promise.all(
    unique.map(async (id): Promise<[string, User] | null> => {
      try {
        return [id, await getUser(id)];
      } catch {
        return null;
      }
    })
  );
  return new Map(entries.filter((e): e is [string, User] => e !== null));
}

/** List workflows with optional pagination, sort, and filters. */
export async function listWorkflows(query: ListQuery = {}): Promise<Workflow[]> {
  return unwrap(sdk.listWorkflowsApiV1WorkflowsGet({ query: listQuery(query) })) as Promise<
    Workflow[]
  >;
}

/** Fetch a single workflow by ID. */
export async function getWorkflow(id: string, options?: CallOptions): Promise<Workflow> {
  return unwrap(
    sdk.getWorkflowApiV1WorkflowsWorkflowIdGet({ path: { workflow_id: id } }),
    options
  ) as Promise<Workflow>;
}

/**
 * Generate a draft workflow from an agent skill ("Generate workflow").
 *
 * Registers the workflow immediately (`status: "generating"`) and breaks the
 * prompt into its task templates in a background design run; callers poll
 * the workflow until it settles on `draft` (or `failed`).
 */
export async function generateWorkflow(
  skillId: string,
  body: GenerateWorkflowRequest
): Promise<Workflow> {
  const workflow = (await unwrap(
    sdk.generateWorkflowApiV1AgentSkillsSkillIdWorkflowsPost({
      path: { skill_id: skillId },
      body: body,
    })
  )) as Workflow;
  console.info("workflow generation started", { workflowId: workflow.id, skillId });
  return workflow;
}

/**
 * Publish a workflow, making it executable. Freezes the current design into the
 * workflow's published snapshot on the backend.
 */
export async function publishWorkflow(id: string): Promise<Workflow> {
  return unwrap(
    sdk.publishWorkflowApiV1WorkflowsWorkflowIdPublishPost({ path: { workflow_id: id } })
  ) as Promise<Workflow>;
}

/**
 * Summarize a workflow's design conversation into its AI-generated
 * description, overwriting the previous summary. A published workflow becomes
 * `modified`.
 */
export async function generateWorkflowDescription(id: string): Promise<Workflow> {
  return unwrap(
    sdk.generateWorkflowDescriptionApiV1WorkflowsWorkflowIdGenerateDescriptionPost({
      path: { workflow_id: id },
    })
  ) as Promise<Workflow>;
}

/**
 * Drop a modified workflow's unpublished edits, restoring the task templates,
 * name, and description captured the last time it was published.
 */
export async function discardWorkflowChanges(id: string): Promise<Workflow> {
  return unwrap(
    sdk.discardWorkflowChangesApiV1WorkflowsWorkflowIdDiscardChangesPost({
      path: { workflow_id: id },
    })
  ) as Promise<Workflow>;
}

/**
 * Deactivate a workflow, returning it to draft. Task templates, description,
 * and the published snapshot are left untouched.
 */
export async function deactivateWorkflow(id: string): Promise<Workflow> {
  return unwrap(
    sdk.deactivateWorkflowApiV1WorkflowsWorkflowIdDeactivatePost({ path: { workflow_id: id } })
  ) as Promise<Workflow>;
}

/** Apply a partial update to a workflow. */
export async function updateWorkflow(id: string, body: WorkflowUpdate): Promise<Workflow> {
  return unwrap(
    sdk.updateWorkflowApiV1WorkflowsWorkflowIdPatch({ path: { workflow_id: id }, body: body })
  ) as Promise<Workflow>;
}

/** Delete a workflow by ID. */
export async function deleteWorkflow(id: string): Promise<void> {
  await unwrap(sdk.deleteWorkflowApiV1WorkflowsWorkflowIdDelete({ path: { workflow_id: id } }));
}

/**
 * Execute a workflow, creating a WorkflowExecution that links the ADK session to
 * the workflow.
 *
 * @param id - Identifier of the workflow to run.
 * @param options - `designSource` picks which design a `modified` workflow
 *   runs: `"published"` (the default) runs the last published version as a real
 *   request, `"live"` runs the unpublished edits as a draft run. `"live"` needs
 *   the `developer` role and a `modified` workflow; the server answers 403
 *   `FORBIDDEN` or 409 `WORKFLOW_NOT_RUNNABLE` otherwise. `toolMockIds` names
 *   the tool mocks the run should apply, stubbing those tools instead of
 *   calling them — accepted only for a draft run, meaning a `draft` workflow or
 *   a `"live"` one; the server answers 409 `WORKFLOW_NOT_RUNNABLE` otherwise.
 */
export async function executeWorkflow(
  id: string,
  options: { toolMockIds?: string[]; designSource?: WorkflowDesignSource } = {}
): Promise<WorkflowExecution> {
  const body: ExecuteWorkflowRequest = {
    toolMockIds: options.toolMockIds ?? [],
    designSource: options.designSource ?? "published",
  };
  const session = (await unwrap(
    sdk.executeWorkflowApiV1WorkflowsWorkflowIdExecutePost({
      path: { workflow_id: id },
      body: body,
    })
  )) as WorkflowExecution;
  console.info("workflow executed", { workflowExecutionId: session.id, workflowId: id });
  return session;
}

/**
 * List the task templates belonging to a workflow (createdAt ASC by default)
 * with optional pagination, sort, and filters.
 */
export async function listWorkflowTaskTemplates(
  workflowId: string,
  query: ListQuery = {}
): Promise<WorkflowTaskTemplate[]> {
  return unwrap(
    sdk.listWorkflowTaskTemplatesApiV1WorkflowsWorkflowIdTaskTemplatesGet({
      path: { workflow_id: workflowId },
      query: listQuery(query),
    })
  ) as Promise<WorkflowTaskTemplate[]>;
}

/** Fetch a single WorkflowTaskTemplate by ID. */
export async function getWorkflowTaskTemplate(
  templateId: string,
  options?: CallOptions
): Promise<WorkflowTaskTemplate> {
  return unwrap(
    sdk.getWorkflowTaskTemplateApiV1WorkflowTaskTemplatesTemplateIdGet({
      path: { template_id: templateId },
    }),
    options
  ) as Promise<WorkflowTaskTemplate>;
}

/** Create a new task template under the workflow given in ``body.workflowId``. */
export async function createWorkflowTaskTemplate(
  body: WorkflowTaskTemplateCreate
): Promise<WorkflowTaskTemplate> {
  return unwrap(
    sdk.createWorkflowTaskTemplateApiV1WorkflowTaskTemplatesPost({ body: body })
  ) as Promise<WorkflowTaskTemplate>;
}

/** Apply a partial update to a task template. ``workflowId`` is not updatable. */
export async function updateWorkflowTaskTemplate(
  templateId: string,
  body: WorkflowTaskTemplateUpdate
): Promise<WorkflowTaskTemplate> {
  return unwrap(
    sdk.updateWorkflowTaskTemplateApiV1WorkflowTaskTemplatesTemplateIdPatch({
      path: { template_id: templateId },
      body: body,
    })
  ) as Promise<WorkflowTaskTemplate>;
}

/** Delete a task template by ID. */
export async function deleteWorkflowTaskTemplate(templateId: string): Promise<void> {
  await unwrap(
    sdk.deleteWorkflowTaskTemplateApiV1WorkflowTaskTemplatesTemplateIdDelete({
      path: { template_id: templateId },
    })
  );
}

/** One `/messages` record: an AG-UI message plus the attribution the backend folds in. */
interface SessionMessageRecord {
  id?: string;
  role?: string;
  toolCallId?: string;
  senderUserId?: string | null;
  workflowTaskId?: string | null;
}

/** A session chat's history and the two attribution maps derived from the same response. */
export interface SessionHistory {
  /** The chat history, oldest first. */
  messages: Message[];
  /** Sender attribution, keyed as {@link sendersFrom} describes. */
  senders: Map<string, string>;
  /** Per-message WorkflowTask association, keyed as {@link tasksFrom} describes. */
  tasks: Map<string, string>;
}

/**
 * Reduce raw `/messages` records to a message-id → sender-user-id map.
 *
 * Keyed by whichever id identifies the message to the rest of the UI: the
 * message id (the ADK event id) for human (`user`) messages, and the
 * `toolCallId` for tool-result messages (for example an A2UI user-action
 * acknowledgement) — the backend keys those by `toolCallId` since a tool
 * message's own `id` is regenerated on every fetch and cannot be used to
 * correlate it back to its sender. Unattributed records are omitted, so callers
 * fall back to the session's owner.
 */
function sendersFrom(records: SessionMessageRecord[]): Map<string, string> {
  const senders = new Map<string, string>();
  for (const record of records) {
    if (!record.senderUserId) continue;
    const key = record.role === "tool" ? record.toolCallId : record.id;
    if (key) senders.set(key, record.senderUserId);
  }
  return senders;
}

/**
 * Reduce raw `/messages` records to a message-id → WorkflowTask-id map.
 *
 * Keyed by the message id (the ADK event id) alone: the backend records the
 * association against every event, so there is no tool-message special case
 * here. Messages produced outside any task (the initial design exchange) are
 * omitted, and a design session's records carry no task at all, leaving the map
 * empty there.
 */
function tasksFrom(records: SessionMessageRecord[]): Map<string, string> {
  const tasks = new Map<string, string>();
  for (const record of records) {
    if (record.id && record.workflowTaskId) tasks.set(record.id, record.workflowTaskId);
  }
  return tasks;
}

/**
 * Fetch a session chat's `/messages` response once and derive every view of it.
 *
 * The history, its sender attribution, and its task association are all folded
 * into the same records by the backend, so they are parsed together rather than
 * re-fetched one view at a time — one request per poll instead of three, and a
 * single consistent snapshot behind all three.
 */
async function fetchSessionHistory(
  call: Promise<SdkResult<unknown>>,
  options?: CallOptions
): Promise<SessionHistory> {
  const records = (await unwrap(call, options)) as SessionMessageRecord[];
  return {
    messages: records as unknown as Message[],
    senders: sendersFrom(records),
    tasks: tasksFrom(records),
  };
}

/**
 * Fetch the chat history of a workflow's design session, with its attribution.
 *
 * A design session has no record of its own, so it is addressed by its
 * workflow's id. Returns an empty history while the background generation run
 * has not started yet. The chat is shared by every developer in the tenant, so
 * its messages carry the same `senderUserId` a workflow session's do; those
 * from the unattended background generation run have none, so callers fall back
 * to the workflow's `createdBy`. The returned `tasks` map is always empty — a
 * design session edits task *templates* and has no status-ful tasks.
 */
export async function getDesignSessionHistory(
  workflowId: string,
  options?: CallOptions
): Promise<SessionHistory> {
  return fetchSessionHistory(
    sdk.getDesignSessionMessagesApiV1WorkflowsWorkflowIdMessagesGet({
      path: { workflow_id: workflowId },
    }),
    options
  );
}

/** Fetch a WorkflowExecution record by ID. */
export async function getWorkflowExecution(
  id: string,
  options?: CallOptions
): Promise<WorkflowExecution> {
  return unwrap(
    sdk.getWorkflowExecutionApiV1WorkflowExecutionsExecutionIdGet({ path: { execution_id: id } }),
    options
  ) as Promise<WorkflowExecution>;
}

/**
 * Fetch the chat history of a WorkflowExecution's workflow session, with its
 * sender attribution and per-message task association.
 *
 * Unlike {@link getSessionMessages}, the history is keyed by the execution's
 * initiator on the backend, so any viewer (for example a designated approver)
 * sees the same conversation instead of a separate, empty session.
 *
 * Agent messages and legacy history written before attribution existed are
 * absent from `senders`, so callers fall back to the execution's initiator.
 * `tasks` names, for each message, the WorkflowTask that was in progress when it
 * was produced; messages produced outside any task are absent.
 */
export async function getWorkflowSessionHistory(
  executionId: string,
  options?: CallOptions
): Promise<SessionHistory> {
  return fetchSessionHistory(
    sdk.getWorkflowSessionMessagesApiV1WorkflowExecutionsExecutionIdMessagesGet({
      path: { execution_id: executionId },
    }),
    options
  );
}

/**
 * Attach a file to a workflow session and return the stored file's metadata.
 *
 * Sent as multipart form data with the `Content-Type` cleared so the browser
 * sets it with the correct multipart boundary — the same shape as
 * {@link uploadUserAvatar}, since the response is still the JSON envelope.
 *
 * The returned `name` is the name the file was actually stored under: a name
 * already taken in the session is stored as a numbered variant rather than
 * replacing what is there, so callers should display this rather than the name
 * they uploaded.
 */
export async function uploadSessionFile(
  workflowExecutionId: string,
  file: File
): Promise<SessionFile> {
  return unwrap(
    sdk.uploadSessionFileApiV1WorkflowExecutionsExecutionIdFilesPost({
      path: { execution_id: workflowExecutionId },
      body: { file },
    })
  ) as Promise<SessionFile>;
}

/**
 * Build the URL that downloads one of a workflow session's files.
 *
 * A plain URL rather than a fetch: the endpoint is cookie-authenticated and
 * serves the file as an attachment, so an `<a href>` downloads it with no
 * JavaScript involved — the same approach {@link avatarUrl} takes for images.
 */
export function sessionFileDownloadUrl(workflowExecutionId: string, fileId: string): string {
  const execution = encodeURIComponent(workflowExecutionId);
  return `${API_BASE}/api/v1/workflow-executions/${execution}/files/${encodeURIComponent(fileId)}/content`;
}

/** List WorkflowExecution records (newest first) with optional pagination, sort, and filters. */
export async function listWorkflowExecutions(query: ListQuery = {}): Promise<WorkflowExecution[]> {
  return unwrap(
    sdk.listWorkflowExecutionsApiV1WorkflowExecutionsGet({ query: listQuery(query) })
  ) as Promise<WorkflowExecution[]>;
}

/** Delete a WorkflowExecution by ID, along with its tasks and workflow session. */
export async function deleteWorkflowExecution(id: string): Promise<void> {
  await unwrap(
    sdk.deleteWorkflowExecutionApiV1WorkflowExecutionsExecutionIdDelete({
      path: { execution_id: id },
    })
  );
}

/**
 * List the WorkflowTasks belonging to the given WorkflowExecution (createdAt ASC by
 * default) with optional pagination, sort, and filters.
 */
export async function listWorkflowTasks(
  workflowExecutionId: string,
  query: ListQuery = {}
): Promise<WorkflowTask[]> {
  return unwrap(
    sdk.listWorkflowExecutionTasksApiV1WorkflowExecutionsExecutionIdWorkflowTasksGet({
      path: { execution_id: workflowExecutionId },
      query: listQuery(query),
    })
  ) as Promise<WorkflowTask[]>;
}

/** Fetch a single WorkflowTask by ID. */
export async function getWorkflowTask(
  taskId: string,
  options?: CallOptions
): Promise<WorkflowTask> {
  return unwrap(
    sdk.getWorkflowTaskApiV1WorkflowTasksTaskIdGet({ path: { task_id: taskId } }),
    options
  ) as Promise<WorkflowTask>;
}

/**
 * Apply a partial update to a WorkflowTask.
 *
 * Only `status` / `errorKind` / `errorMessage` are updatable — a run's task
 * list is fixed at execute time, so a task's title, description, dependencies
 * and tool bindings cannot be changed, and tasks cannot be created or deleted
 * through the API.
 */
export async function updateWorkflowTask(
  taskId: string,
  body: WorkflowTaskUpdate
): Promise<WorkflowTask> {
  return unwrap(
    sdk.updateWorkflowTaskApiV1WorkflowTasksTaskIdPatch({ path: { task_id: taskId }, body: body })
  ) as Promise<WorkflowTask>;
}

/**
 * Filter directive selecting only unread notifications.
 *
 * Used by the toolbar bell, which polls for unread items alone.
 */
export const UNREAD_ONLY_FILTER: FilterSpec = { field: "read", op: "eq", value: "false" };

/** List the current user's notifications (newest first) with optional pagination, sort, and filters. */
export async function listNotifications(query: ListQuery = {}): Promise<Notification[]> {
  return unwrap(sdk.listNotificationsApiV1NotificationsGet({ query: listQuery(query) })) as Promise<
    Notification[]
  >;
}

/**
 * Apply a partial update to a single notification and return the updated record.
 *
 * `read` is the only mutable field, so this is how a notification is marked read
 * (`{ read: true }`) or returned to the unread state.
 */
export async function updateNotification(
  id: string,
  data: NotificationUpdate
): Promise<Notification> {
  return unwrap(
    sdk.updateNotificationApiV1NotificationsNotificationIdPatch({
      path: { notification_id: id },
      body: data,
    })
  ) as Promise<Notification>;
}

/** Mark all of the current user's unread notifications as read. */
export async function markAllNotificationsRead(): Promise<void> {
  await unwrap(sdk.markAllNotificationsReadApiV1NotificationsReadAllPost());
}

/** Permanently delete a single notification. */
export async function deleteNotification(id: string): Promise<void> {
  await unwrap(
    sdk.deleteNotificationApiV1NotificationsNotificationIdDelete({ path: { notification_id: id } })
  );
}

/** List approval requests (newest first) with optional pagination, sort, and filters. */
export async function listApprovals(query: ListQuery = {}): Promise<Approval[]> {
  return unwrap(sdk.listApprovalsApiV1ApprovalsGet({ query: listQuery(query) })) as Promise<
    Approval[]
  >;
}

/** Fetch a single approval request by ID. */
export async function getApproval(id: string, options?: CallOptions): Promise<ApprovalDetail> {
  return unwrap(
    sdk.getApprovalApiV1ApprovalsApprovalIdGet({ path: { approval_id: id } }),
    options
  ) as Promise<ApprovalDetail>;
}

/**
 * Fetch the certificates issued under an approval, one per task it covers.
 *
 * Reports what the approval actually authorized -- for each covered task, which
 * MCP tools, until when, and whether the grant has since been revoked. An
 * approval covers the task it names plus every task after it up to the next
 * approval, and each is granted its certificate only when it starts, so an
 * empty list is an ordinary state rather than an error.
 */
export async function listApprovalCertificates(
  id: string,
  options?: CallOptions
): Promise<McpToolCertificateRead[]> {
  return unwrap(
    sdk.listApprovalCertificatesApiV1ApprovalsApprovalIdCertificatesGet({
      path: { approval_id: id },
    }),
    options
  ) as Promise<McpToolCertificateRead[]>;
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
  return unwrap(
    sdk.resolveApprovalApiV1ApprovalsApprovalIdPatch({
      path: { approval_id: id },
      body: { status, response },
    })
  ) as Promise<Approval>;
}

/**
 * HttpAgent variant that sends the auth session cookie, the CSRF token, the
 * selected tenant header, and the impersonation header with each streaming
 * request. The agent endpoints are POSTs, so they need both the cookie
 * (`credentials: "include"`) and the double-submit `X-CSRF-Token` header; a
 * super_admin also needs `X-Tenant-Id` to reach these tenant-scoped endpoints
 * at all, and an impersonating admin needs `X-Impersonate-User-Id` for the
 * agent to act as the impersonated user -- unlike the generated SDK calls
 * above, these bypass `client`'s request interceptor entirely, so the headers
 * must be attached here too.
 */
class CredentialedHttpAgent extends HttpAgent {
  /** Augment the base fetch config with credentials, CSRF, tenant, and impersonation headers. */
  protected requestInit(input: Parameters<HttpAgent["requestInit"]>[0]): RequestInit {
    const init = super.requestInit(input);
    const csrf = readCookie(CSRF_COOKIE_NAME);
    const tenantId = store.getState().auth.selectedTenantId;
    const impersonatedUserId = store.getState().auth.impersonatedUserId;
    return {
      ...init,
      credentials: "include",
      headers: {
        ...(init.headers as Record<string, string> | undefined),
        ...(csrf ? { [CSRF_HEADER_NAME]: csrf } : {}),
        ...(tenantId ? { [TENANT_HEADER_NAME]: tenantId } : {}),
        ...(impersonatedUserId ? { [IMPERSONATE_HEADER_NAME]: impersonatedUserId } : {}),
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
      defaultCatalogId: A2UI_CATALOG_ID,
    })
  );
  return agent;
}

/**
 * Create an HttpAgent scoped to one execution's workflow session endpoint,
 * pre-configured with the A2UI middleware so the agent can render interactive
 * surfaces.
 */
export function createWorkflowSessionAgent(
  workflowExecutionId: string,
  sessionId: string
): HttpAgent {
  const agent = new CredentialedHttpAgent({
    url: `${API_BASE}/api/v1/workflow-executions/${encodeURIComponent(workflowExecutionId)}/agent`,
    threadId: sessionId,
  });
  agent.use(
    new A2UIMiddleware({
      injectA2UITool: true,
      schema: basicCatalogJson as unknown as A2UIInlineCatalogSchema,
      defaultCatalogId: A2UI_CATALOG_ID,
    })
  );
  return agent;
}

/**
 * Create an HttpAgent scoped to a workflow's design session endpoint, pre-configured
 * with the A2UI middleware so the design agent can render interactive surfaces
 * while the user refines the workflow's task templates.
 */
export function createDesignSessionAgent(workflowId: string, sessionId: string): HttpAgent {
  const agent = new CredentialedHttpAgent({
    url: `${API_BASE}/api/v1/workflows/${encodeURIComponent(workflowId)}/agent`,
    threadId: sessionId,
  });
  agent.use(
    new A2UIMiddleware({
      injectA2UITool: true,
      schema: basicCatalogJson as unknown as A2UIInlineCatalogSchema,
      defaultCatalogId: A2UI_CATALOG_ID,
    })
  );
  return agent;
}
