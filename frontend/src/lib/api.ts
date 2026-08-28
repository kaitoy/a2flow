import { type A2UIInlineCatalogSchema, A2UIMiddleware } from "@ag-ui/a2ui-middleware";
import { HttpAgent } from "@ag-ui/client";
import type { Message } from "@ag-ui/core";
import axios, { type AxiosRequestConfig, type AxiosResponse } from "axios";
import type { z } from "zod";
import type {
  AgentSkillCreate,
  AgentSkillRead as AgentSkillModel,
  AgentSkillUpdate,
  ApiError,
  ApiMeta,
  ApprovalCertificateRead,
  Approval as ApprovalModel,
  ApprovalStatus,
  ApprovalUpdate,
  AvatarConfig,
  ExecuteWorkflowRequest,
  GenerateWorkflowRequest,
  LoginRequest,
  McpCommand,
  McpRegistryEnvVar,
  McpRegistryHeader,
  McpRegistrySearchResult,
  McpRegistryServerEntry,
  McpServerCreate,
  McpServerRead as McpServerModel,
  McpServerUpdate,
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
  SecretCreate,
  SecretRead as SecretModel,
  SecretType,
  SecretUpdate,
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
  WorkflowExecution as WorkflowExecutionModel,
  WorkflowExecutionStatus,
  WorkflowRead as WorkflowModel,
  WorkflowStatus,
  WorkflowTaskCreate,
  WorkflowTaskRead as WorkflowTaskModel,
  WorkflowTaskStatus,
  WorkflowTaskTemplateCreate,
  WorkflowTaskTemplateRead as WorkflowTaskTemplateModel,
  WorkflowTaskTemplateUpdate,
  WorkflowTaskUpdate,
  WorkflowUpdate,
} from "@/generated/api/types.gen";
import {
  zCreateAgentSkillApiV1AgentSkillsPostResponse,
  zCreateMcpServerApiV1McpServersPostResponse,
  zCreateMcpToolMockApiV1McpToolMocksPostResponse,
  zCreateSecretApiV1SecretsPostResponse,
  zCreateTagApiV1TagsPostResponse,
  zCreateTenantApiV1TenantsPostResponse,
  zCreateUserApiV1UsersPostResponse,
  zCreateUserGroupApiV1UserGroupsPostResponse,
  zCreateWorkflowTaskApiV1WorkflowTasksPostResponse,
  zCreateWorkflowTaskTemplateApiV1WorkflowTaskTemplatesPostResponse,
  zDeactivateWorkflowApiV1WorkflowsWorkflowIdDeactivatePostResponse,
  zDeleteAgentSkillApiV1AgentSkillsSkillIdDeleteResponse,
  zDeleteMcpServerApiV1McpServersServerIdDeleteResponse,
  zDeleteMcpToolMockApiV1McpToolMocksMockIdDeleteResponse,
  zDeleteNotificationApiV1NotificationsNotificationIdDeleteResponse,
  zDeleteSecretApiV1SecretsSecretIdDeleteResponse,
  zDeleteSessionApiV1SessionsSessionIdDeleteResponse,
  zDeleteTagApiV1TagsTagIdDeleteResponse,
  zDeleteTenantApiV1TenantsTenantIdDeleteResponse,
  zDeleteUserApiV1UsersUserIdDeleteResponse,
  zDeleteUserAvatarApiV1UsersUserIdAvatarDeleteResponse,
  zDeleteUserGroupApiV1UserGroupsGroupIdDeleteResponse,
  zDeleteWorkflowApiV1WorkflowsWorkflowIdDeleteResponse,
  zDeleteWorkflowExecutionApiV1WorkflowExecutionsExecutionIdDeleteResponse,
  zDeleteWorkflowTaskApiV1WorkflowTasksTaskIdDeleteResponse,
  zDeleteWorkflowTaskTemplateApiV1WorkflowTaskTemplatesTemplateIdDeleteResponse,
  zDiscardWorkflowChangesApiV1WorkflowsWorkflowIdDiscardChangesPostResponse,
  zExecuteWorkflowApiV1WorkflowsWorkflowIdExecutePostResponse,
  zGenerateWorkflowApiV1AgentSkillsSkillIdWorkflowsPostResponse,
  zGenerateWorkflowDescriptionApiV1WorkflowsWorkflowIdGenerateDescriptionPostResponse,
  zGetAgentSkillApiV1AgentSkillsSkillIdGetResponse,
  zGetApprovalApiV1ApprovalsApprovalIdGetResponse,
  zGetApprovalCertificateApiV1ApprovalsApprovalIdCertificateGetResponse,
  zGetDesignSessionMessagesApiV1WorkflowsWorkflowIdMessagesGetResponse,
  zGetMcpServerApiV1McpServersServerIdGetResponse,
  zGetMcpToolMockApiV1McpToolMocksMockIdGetResponse,
  zGetSecretApiV1SecretsSecretIdGetResponse,
  zGetSessionApiV1SessionsSessionIdGetResponse,
  zGetSessionMessagesApiV1SessionsSessionIdMessagesGetResponse,
  zGetSystemSettingsApiV1SystemSettingsGetResponse,
  zGetTagApiV1TagsTagIdGetResponse,
  zGetTenantApiV1TenantsTenantIdGetResponse,
  zGetUserApiV1UsersUserIdGetResponse,
  zGetUserGroupApiV1UserGroupsGroupIdGetResponse,
  zGetWorkflowApiV1WorkflowsWorkflowIdGetResponse,
  zGetWorkflowExecutionApiV1WorkflowExecutionsExecutionIdGetResponse,
  zGetWorkflowSessionMessagesApiV1WorkflowExecutionsExecutionIdMessagesGetResponse,
  zGetWorkflowTaskApiV1WorkflowTasksTaskIdGetResponse,
  zGetWorkflowTaskTemplateApiV1WorkflowTaskTemplatesTemplateIdGetResponse,
  zListAgentSkillsApiV1AgentSkillsGetResponse,
  zListApprovalsApiV1ApprovalsGetResponse,
  zListGroupsForUserApiV1UsersUserIdGroupsGetResponse,
  zListMcpServersApiV1McpServersGetResponse,
  zListMcpServerToolsApiV1McpServersServerIdToolsGetResponse,
  zListMcpToolMocksApiV1McpToolMocksGetResponse,
  zListNotificationsApiV1NotificationsGetResponse,
  zListSecretKeysApiV1SecretsSecretIdKeysGetResponse,
  zListSecretsApiV1SecretsGetResponse,
  zListSessionsApiV1SessionsGetResponse,
  zListTagsApiV1TagsGetResponse,
  zListTenantsApiV1TenantsGetResponse,
  zListUserGroupsApiV1UserGroupsGetResponse,
  zListUsersApiV1UsersGetResponse,
  zListWorkflowExecutionsApiV1WorkflowExecutionsGetResponse,
  zListWorkflowExecutionTasksApiV1WorkflowExecutionsExecutionIdWorkflowTasksGetResponse,
  zListWorkflowExecutionToolInvocationsApiV1WorkflowExecutionsExecutionIdToolInvocationsGetResponse,
  zListWorkflowsApiV1WorkflowsGetResponse,
  zListWorkflowTaskTemplatesApiV1WorkflowsWorkflowIdTaskTemplatesGetResponse,
  zLoginApiV1AuthLoginPostResponse,
  zLogoutApiV1AuthLogoutPostResponse,
  zMarkAllNotificationsReadApiV1NotificationsReadAllPostResponse,
  zMeApiV1AuthMeGetResponse,
  zPublishWorkflowApiV1WorkflowsWorkflowIdPublishPostResponse,
  zPullAgentSkillApiV1AgentSkillsSkillIdPullPostResponse,
  zResolveApprovalApiV1ApprovalsApprovalIdPatchResponse,
  zResolveUserNamesApiV1UsersResolveNamesPostResponse,
  zSearchMcpRegistryApiV1McpRegistryGetResponse,
  zSendSmtpTestEmailApiV1SystemSettingsSmtpTestPostResponse,
  zSetAgentSkillTagsApiV1AgentSkillsSkillIdTagsPutResponse,
  zSetMcpServerTagsApiV1McpServersServerIdTagsPutResponse,
  zSetSecretTagsApiV1SecretsSecretIdTagsPutResponse,
  zSetUserGroupsApiV1UsersUserIdGroupsPutResponse,
  zSetWorkflowTagsApiV1WorkflowsWorkflowIdTagsPutResponse,
  zStartImpersonationApiV1AuthImpersonatePostResponse,
  zStopImpersonationApiV1AuthImpersonateDeleteResponse,
  zUpdateAgentSkillApiV1AgentSkillsSkillIdPatchResponse,
  zUpdateMcpServerApiV1McpServersServerIdPatchResponse,
  zUpdateMcpToolMockApiV1McpToolMocksMockIdPatchResponse,
  zUpdateNotificationApiV1NotificationsNotificationIdPatchResponse,
  zUpdateSecretApiV1SecretsSecretIdPatchResponse,
  zUpdateSystemSettingsApiV1SystemSettingsPatchResponse,
  zUpdateTagApiV1TagsTagIdPatchResponse,
  zUpdateTenantApiV1TenantsTenantIdPatchResponse,
  zUpdateUserApiV1UsersUserIdPatchResponse,
  zUpdateUserGroupApiV1UserGroupsGroupIdPatchResponse,
  zUpdateWorkflowApiV1WorkflowsWorkflowIdPatchResponse,
  zUpdateWorkflowTaskApiV1WorkflowTasksTaskIdPatchResponse,
  zUpdateWorkflowTaskTemplateApiV1WorkflowTaskTemplatesTemplateIdPatchResponse,
  zUploadUserAvatarApiV1UsersUserIdAvatarPutResponse,
} from "@/generated/api/zod.gen";
import { store } from "@/store";
import { showToast } from "@/store/toastSlice";
import basicCatalogJson from "../generated/basic_catalog.json";
import { A2UI_CATALOG_ID } from "./a2uiCatalogId";
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

declare module "axios" {
  interface AxiosRequestConfig {
    /**
     * When true, skip the global error toast for a FORBIDDEN (403) failure on
     * this specific request -- the caller renders its own access-denied state
     * instead. Any other failure, including a different 403, still toasts
     * normally. See {@link isForbiddenError}.
     */
    suppressForbiddenToast?: boolean;
  }
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
  const tenantId = store.getState().auth.selectedTenantId;
  if (tenantId) config.headers.set(TENANT_HEADER_NAME, tenantId);
  const impersonatedUserId = store.getState().auth.impersonatedUserId;
  if (impersonatedUserId) config.headers.set(IMPERSONATE_HEADER_NAME, impersonatedUserId);
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // Redirect to the login page when a request is rejected for lack of a valid
    // session — except the login request itself, which surfaces 401 inline.
    const url: string = error?.config?.url ?? "";
    const isSessionExpiry =
      typeof window !== "undefined" &&
      error?.response?.status === 401 &&
      !url.endsWith("/auth/login") &&
      window.location.pathname !== "/login";
    if (isSessionExpiry) {
      // A toast would just flash and vanish mid-navigation, so skip it here.
      window.location.assign("/login");
    } else if (error?.config?.suppressForbiddenToast && isForbiddenError(error)) {
      // Caller renders its own access-denied state; skip the generic toast.
    } else {
      reportApiError(error);
    }
    return Promise.reject(error);
  }
);

/**
 * In-flight GET requests keyed by URL + query params, so two callers racing
 * for the exact same data collapse into one network request instead of the
 * backend seeing it twice. The main case this guards against is a list
 * page's mount effect firing twice with identical params -- e.g. under React
 * StrictMode's dev-only mount/cleanup/remount cycle -- but it also covers two
 * independent components (e.g. the tenant switcher and the tenants admin
 * page) requesting the same resource at once. Entries are removed as soon as
 * the request settles, so this shares only concurrent requests -- it is not
 * a cache and never serves stale data to a later call.
 */
const inFlightGets = new Map<string, Promise<AxiosResponse>>();

function dedupeKey(url: string, config?: AxiosRequestConfig): string {
  return `${url}?${JSON.stringify(config?.params ?? {})}`;
}

const rawGet = apiClient.get.bind(apiClient) as (
  url: string,
  config?: AxiosRequestConfig
) => Promise<AxiosResponse>;

apiClient.get = ((url: string, config?: AxiosRequestConfig) => {
  const key = dedupeKey(url, config);
  const existing = inFlightGets.get(key);
  if (existing) return existing;
  const request = rawGet(url, config).finally(() => inFlightGets.delete(key));
  inFlightGets.set(key, request);
  return request;
}) as typeof apiClient.get;

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
 * Extract a user-facing message from a failed API call. Handles both shapes a
 * call can fail with: an {@link ApiClientError} (a 2xx response whose envelope
 * carries an error, thrown by {@link fetchEnvelope}) and a raw Axios error (an
 * HTTP-level failure, e.g. a non-2xx status), which the response interceptor
 * below reports but re-throws unconverted.
 */
export function getApiErrorMessage(error: unknown): string {
  if (error instanceof ApiClientError) {
    return error.message;
  }
  if (axios.isAxiosError(error)) {
    const envelopeError = (error.response?.data as { error?: ApiError } | null | undefined)?.error;
    if (envelopeError?.message) {
      return envelopeError.message;
    }
    if (!error.response) {
      return "Unable to reach the server. Please check your connection and try again.";
    }
    if (error.message) {
      return error.message;
    }
  } else if (error instanceof Error) {
    return error.message;
  }
  return "Something went wrong. Please try again.";
}

/**
 * Show a failed API call's message as a red toast. Called from the response
 * interceptor (HTTP-level failures) and from {@link fetchEnvelope} (2xx
 * responses whose envelope still carries an error).
 */
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
 * which this deliberately does not match. Handles both shapes a call can
 * fail with, same as {@link getApiErrorMessage}: a raw Axios error
 * (HTTP-level 403) and an {@link ApiClientError} (a 2xx envelope that still
 * carries the error, thrown by {@link fetchEnvelope}).
 */
export function isForbiddenError(error: unknown): boolean {
  if (error instanceof ApiClientError) {
    return error.code === FORBIDDEN_CODE;
  }
  if (axios.isAxiosError(error) && error.response?.status === 403) {
    const envelopeCode = (error.response.data as { error?: ApiError } | null | undefined)?.error
      ?.code;
    return envelopeCode === undefined || envelopeCode === FORBIDDEN_CODE;
  }
  return false;
}

/**
 * True when `error` is the backend's `ApprovalAlreadyResolvedError` (HTTP 409,
 * envelope `error.code === "APPROVAL_ALREADY_RESOLVED"`) -- someone else
 * decided this approval first. Only reachable for a group-addressed approval,
 * where several eligible members can hold the controls at the same time, so
 * the UI reports "already decided" rather than a generic failure.
 */
export function isApprovalAlreadyResolvedError(error: unknown): boolean {
  if (error instanceof ApiClientError) {
    return error.code === APPROVAL_ALREADY_RESOLVED_CODE;
  }
  if (axios.isAxiosError(error) && error.response?.status === 409) {
    const envelopeCode = (error.response.data as { error?: ApiError } | null | undefined)?.error
      ?.code;
    return envelopeCode === APPROVAL_ALREADY_RESOLVED_CODE;
  }
  return false;
}

/**
 * Axios request config for a page's initial-load GET that renders its own
 * {@link isForbiddenError}-driven access-denied state, so the generic error
 * toast should stay silent for a FORBIDDEN failure on that specific request.
 */
export const SUPPRESS_FORBIDDEN_TOAST: AxiosRequestConfig = { suppressForbiddenToast: true };

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
    const err = new ApiClientError(
      env.error.code,
      env.error.message,
      env.error.details,
      env.meta.requestId
    );
    if (!(res.config?.suppressForbiddenToast && isForbiddenError(err))) {
      reportApiError(err);
    }
    throw err;
  }
  return env.data;
}

type AuditedKeys = "id" | "createdAt" | "updatedAt" | "createdBy" | "updatedBy";
type WithAudit<T extends Partial<Record<AuditedKeys, unknown>>> = T &
  Required<Pick<T, AuditedKeys>>;

export type AgentSkill = WithAudit<AgentSkillModel>;
export type Approval = WithAudit<ApprovalModel>;
export type McpServer = WithAudit<McpServerModel>;
export type McpToolMock = WithAudit<McpToolMockModel>;
export type McpToolInvocation = WithAudit<McpToolInvocationModel>;
export type Notification = WithAudit<NotificationModel>;
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
export type {
  AgentSkillCreate,
  AgentSkillUpdate,
  ApprovalCertificateRead,
  ApprovalStatus,
  ApprovalUpdate,
  AvatarConfig,
  GenerateWorkflowRequest,
  LoginRequest,
  McpCommand,
  McpRegistryEnvVar,
  McpRegistryHeader,
  McpRegistrySearchResult,
  McpRegistryServerEntry,
  McpServerCreate,
  McpServerUpdate,
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
  WorkflowExecutionStatus,
  WorkflowStatus,
  WorkflowTaskCreate,
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
  tagIds = [],
}: ListQuery = {}): Pick<AxiosRequestConfig, "params" | "paramsSerializer"> {
  const params: Record<string, unknown> = { limit, offset };
  if (sort) params.s = `${sort.descending ? "-" : ""}${sort.field}`;
  if (filters.length > 0) params.q = filters.map((f) => `${f.field}:${f.op}:${f.value}`);
  if (tagIds.length > 0) params.tag = tagIds;
  return { params, paramsSerializer: { indexes: null } };
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
  return fetchEnvelope(
    apiClient.post("/api/v1/auth/login", {
      username,
      password,
      tenantName: tenantName || undefined,
    }),
    zLoginApiV1AuthLoginPostResponse
  ) as Promise<User>;
}

/** Revoke the current session and clear the auth cookies. */
export async function logout(): Promise<void> {
  await fetchEnvelope(apiClient.post("/api/v1/auth/logout"), zLogoutApiV1AuthLogoutPostResponse);
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
  return fetchEnvelope(apiClient.get("/api/v1/auth/me"), zMeApiV1AuthMeGetResponse) as Promise<Me>;
}

/**
 * Start impersonating another user. The backend enforces eligibility (role,
 * tenant, and target-role restrictions); a rejection surfaces as a thrown
 * `ApiClientError` with the usual `FORBIDDEN`/`NOT_FOUND` codes.
 */
export async function startImpersonation(targetUserId: string): Promise<Me> {
  return fetchEnvelope(
    apiClient.post("/api/v1/auth/impersonate", { targetUserId }),
    zStartImpersonationApiV1AuthImpersonatePostResponse
  ) as Promise<Me>;
}

/** Stop impersonating, if currently active; a no-op (never throws for this reason) otherwise. */
export async function stopImpersonation(): Promise<Me> {
  return fetchEnvelope(
    apiClient.delete("/api/v1/auth/impersonate"),
    zStopImpersonationApiV1AuthImpersonateDeleteResponse
  ) as Promise<Me>;
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
export async function getAgentSkill(id: string, config?: AxiosRequestConfig): Promise<AgentSkill> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/agent-skills/${encodeURIComponent(id)}`, config),
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

/**
 * Re-clone an agent skill's repository at its current remote HEAD.
 *
 * How a skill picks up upstream changes, and how a failed registration clone is
 * retried. The clone runs in the background: the returned skill is already
 * marked `pending`, and the caller polls until it settles on `ready` or
 * `failed`.
 */
export async function pullAgentSkill(id: string): Promise<AgentSkill> {
  return fetchEnvelope(
    apiClient.post(`/api/v1/agent-skills/${encodeURIComponent(id)}/pull`),
    zPullAgentSkillApiV1AgentSkillsSkillIdPullPostResponse
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
export async function getMcpServer(id: string, config?: AxiosRequestConfig): Promise<McpServer> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/mcp-servers/${encodeURIComponent(id)}`, config),
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

/** List the tool mocks registered in the tenant (createdAt DESC by default). */
export async function listMcpToolMocks(query: ListQuery = {}): Promise<McpToolMock[]> {
  return fetchEnvelope(
    apiClient.get("/api/v1/mcp-tool-mocks", listConfig(query)),
    zListMcpToolMocksApiV1McpToolMocksGetResponse
  ) as Promise<McpToolMock[]>;
}

/** Fetch a single tool mock by ID. */
export async function getMcpToolMock(
  id: string,
  config?: AxiosRequestConfig
): Promise<McpToolMock> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/mcp-tool-mocks/${encodeURIComponent(id)}`, config),
    zGetMcpToolMockApiV1McpToolMocksMockIdGetResponse
  ) as Promise<McpToolMock>;
}

/** Register a new tool mock. */
export async function createMcpToolMock(body: McpToolMockCreate): Promise<McpToolMock> {
  return fetchEnvelope(
    apiClient.post("/api/v1/mcp-tool-mocks", body),
    zCreateMcpToolMockApiV1McpToolMocksPostResponse
  ) as Promise<McpToolMock>;
}

/** Apply a partial update to a tool mock. `responses` replaces the full list. */
export async function updateMcpToolMock(id: string, body: McpToolMockUpdate): Promise<McpToolMock> {
  return fetchEnvelope(
    apiClient.patch(`/api/v1/mcp-tool-mocks/${encodeURIComponent(id)}`, body),
    zUpdateMcpToolMockApiV1McpToolMocksMockIdPatchResponse
  ) as Promise<McpToolMock>;
}

/**
 * Delete a tool mock. Runs already started keep their own snapshot of it, so
 * deleting one never changes how an existing run behaves.
 */
export async function deleteMcpToolMock(id: string): Promise<void> {
  await fetchEnvelope(
    apiClient.delete(`/api/v1/mcp-tool-mocks/${encodeURIComponent(id)}`),
    zDeleteMcpToolMockApiV1McpToolMocksMockIdDeleteResponse
  );
}

/**
 * List the MCP tool-call decisions recorded for one workflow execution.
 *
 * Only calls that reached the MCP proxy appear here — allowed ones that went
 * upstream and denied ones a policy vetoed. A call answered by a tool mock never
 * reaches the proxy, so it shows in the chat transcript instead.
 */
export async function listWorkflowExecutionToolInvocations(
  executionId: string,
  query: ListQuery = {}
): Promise<McpToolInvocation[]> {
  return fetchEnvelope(
    apiClient.get(
      `/api/v1/workflow-executions/${encodeURIComponent(executionId)}/tool-invocations`,
      listConfig(query)
    ),
    zListWorkflowExecutionToolInvocationsApiV1WorkflowExecutionsExecutionIdToolInvocationsGetResponse
  ) as Promise<McpToolInvocation[]>;
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

/** List secrets with optional pagination, sort, and filters. Values are never returned. */
export async function listSecrets(query: ListQuery = {}): Promise<Secret[]> {
  return fetchEnvelope(
    apiClient.get("/api/v1/secrets", listConfig(query)),
    zListSecretsApiV1SecretsGetResponse
  ) as Promise<Secret[]>;
}

/** Fetch a single secret by ID. The stored value is never returned. */
export async function getSecret(id: string, config?: AxiosRequestConfig): Promise<Secret> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/secrets/${encodeURIComponent(id)}`, config),
    zGetSecretApiV1SecretsSecretIdGetResponse
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
  return fetchEnvelope(
    apiClient.get(`/api/v1/secrets/${encodeURIComponent(id)}/keys`),
    zListSecretKeysApiV1SecretsSecretIdKeysGetResponse
  ) as Promise<string[]>;
}

/** Register a new secret: a `local` encrypted value or a `vault` KV v2 reference. */
export async function createSecret(body: SecretCreate): Promise<Secret> {
  return fetchEnvelope(
    apiClient.post("/api/v1/secrets", body),
    zCreateSecretApiV1SecretsPostResponse
  ) as Promise<Secret>;
}

/** Apply a partial update to a secret. Omitting `entries` keeps the stored map unchanged. */
export async function updateSecret(id: string, body: SecretUpdate): Promise<Secret> {
  return fetchEnvelope(
    apiClient.patch(`/api/v1/secrets/${encodeURIComponent(id)}`, body),
    zUpdateSecretApiV1SecretsSecretIdPatchResponse
  ) as Promise<Secret>;
}

/** Delete a secret by ID. References to it fail lazily at their next resolution. */
export async function deleteSecret(id: string): Promise<void> {
  await fetchEnvelope(
    apiClient.delete(`/api/v1/secrets/${encodeURIComponent(id)}`),
    zDeleteSecretApiV1SecretsSecretIdDeleteResponse
  );
}

/** List tags with optional pagination, sort, and filters. */
export async function listTags(query: ListQuery = {}): Promise<Tag[]> {
  return fetchEnvelope(
    apiClient.get("/api/v1/tags", listConfig(query)),
    zListTagsApiV1TagsGetResponse
  ) as Promise<Tag[]>;
}

/** Fetch a single tag by ID. */
export async function getTag(id: string, config?: AxiosRequestConfig): Promise<Tag> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/tags/${encodeURIComponent(id)}`, config),
    zGetTagApiV1TagsTagIdGetResponse
  ) as Promise<Tag>;
}

/** Register a new tag. Requires the `admin` or `developer` role. */
export async function createTag(body: TagCreate): Promise<Tag> {
  return fetchEnvelope(
    apiClient.post("/api/v1/tags", body),
    zCreateTagApiV1TagsPostResponse
  ) as Promise<Tag>;
}

/**
 * Apply a partial update to a tag.
 *
 * Renaming is safe at any time: records reference a tag by id, so every record
 * carrying it picks up the new name.
 */
export async function updateTag(id: string, body: TagUpdate): Promise<Tag> {
  return fetchEnvelope(
    apiClient.patch(`/api/v1/tags/${encodeURIComponent(id)}`, body),
    zUpdateTagApiV1TagsTagIdPatchResponse
  ) as Promise<Tag>;
}

/** Delete a tag, detaching it from every record that carried it. */
export async function deleteTag(id: string): Promise<void> {
  await fetchEnvelope(
    apiClient.delete(`/api/v1/tags/${encodeURIComponent(id)}`),
    zDeleteTagApiV1TagsTagIdDeleteResponse
  );
}

/**
 * Replace a secret's tags wholesale. An empty array detaches every tag.
 *
 * Tags are a sub-resource rather than a field of the secret payload, so
 * creating a tagged record is a create followed by this call.
 */
export async function setSecretTags(id: string, tagIds: string[]): Promise<Secret> {
  return fetchEnvelope(
    apiClient.put(`/api/v1/secrets/${encodeURIComponent(id)}/tags`, { tagIds }),
    zSetSecretTagsApiV1SecretsSecretIdTagsPutResponse
  ) as Promise<Secret>;
}

/** Replace a workflow's tags wholesale. An empty array detaches every tag. */
export async function setWorkflowTags(id: string, tagIds: string[]): Promise<Workflow> {
  return fetchEnvelope(
    apiClient.put(`/api/v1/workflows/${encodeURIComponent(id)}/tags`, { tagIds }),
    zSetWorkflowTagsApiV1WorkflowsWorkflowIdTagsPutResponse
  ) as Promise<Workflow>;
}

/** Replace an MCP server's tags wholesale. An empty array detaches every tag. */
export async function setMcpServerTags(id: string, tagIds: string[]): Promise<McpServer> {
  return fetchEnvelope(
    apiClient.put(`/api/v1/mcp-servers/${encodeURIComponent(id)}/tags`, { tagIds }),
    zSetMcpServerTagsApiV1McpServersServerIdTagsPutResponse
  ) as Promise<McpServer>;
}

/** Replace an agent skill's tags wholesale. An empty array detaches every tag. */
export async function setAgentSkillTags(id: string, tagIds: string[]): Promise<AgentSkill> {
  return fetchEnvelope(
    apiClient.put(`/api/v1/agent-skills/${encodeURIComponent(id)}/tags`, { tagIds }),
    zSetAgentSkillTagsApiV1AgentSkillsSkillIdTagsPutResponse
  ) as Promise<AgentSkill>;
}

/** List tenants with optional pagination, sort, and filters. */
export async function listTenants(query: ListQuery = {}): Promise<Tenant[]> {
  return fetchEnvelope(
    apiClient.get("/api/v1/tenants", listConfig(query)),
    zListTenantsApiV1TenantsGetResponse
  ) as Promise<Tenant[]>;
}

/** Fetch a single tenant by ID. */
export async function getTenant(id: string, config?: AxiosRequestConfig): Promise<Tenant> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/tenants/${encodeURIComponent(id)}`, config),
    zGetTenantApiV1TenantsTenantIdGetResponse
  ) as Promise<Tenant>;
}

/** Create a new tenant. */
export async function createTenant(body: TenantCreate): Promise<Tenant> {
  return fetchEnvelope(
    apiClient.post("/api/v1/tenants", body),
    zCreateTenantApiV1TenantsPostResponse
  ) as Promise<Tenant>;
}

/** Apply a partial update to a tenant. */
export async function updateTenant(id: string, body: TenantUpdate): Promise<Tenant> {
  return fetchEnvelope(
    apiClient.patch(`/api/v1/tenants/${encodeURIComponent(id)}`, body),
    zUpdateTenantApiV1TenantsTenantIdPatchResponse
  ) as Promise<Tenant>;
}

/** Delete a tenant by ID. Fails while any user remains assigned to it. */
export async function deleteTenant(id: string): Promise<void> {
  await fetchEnvelope(
    apiClient.delete(`/api/v1/tenants/${encodeURIComponent(id)}`),
    zDeleteTenantApiV1TenantsTenantIdDeleteResponse
  );
}

/**
 * Fetch the platform-wide system settings. `super_admin` only.
 *
 * The SMTP password is never part of the response; `smtpPasswordSet` reports
 * only whether one is stored.
 */
export async function getSystemSettings(config?: AxiosRequestConfig): Promise<SystemSettings> {
  return fetchEnvelope(
    apiClient.get("/api/v1/system-settings", config),
    zGetSystemSettingsApiV1SystemSettingsGetResponse
  ) as Promise<SystemSettings>;
}

/**
 * Apply a partial update to the system settings. `super_admin` only.
 *
 * Omitting `smtpPassword` — or sending it as an empty string — keeps the stored
 * password, so a blank field in the form is non-destructive.
 */
export async function updateSystemSettings(body: SystemSettingsUpdate): Promise<SystemSettings> {
  return fetchEnvelope(
    apiClient.patch("/api/v1/system-settings", body),
    zUpdateSystemSettingsApiV1SystemSettingsPatchResponse
  ) as Promise<SystemSettings>;
}

/**
 * Send a test message with the stored SMTP settings to the caller's own address.
 *
 * The recipient is fixed server-side, so this cannot be used to relay mail
 * anywhere else.
 */
export async function sendSmtpTestEmail(): Promise<void> {
  await fetchEnvelope(
    apiClient.post("/api/v1/system-settings/smtp/test"),
    zSendSmtpTestEmailApiV1SystemSettingsSmtpTestPostResponse
  );
}

/** List users with optional pagination, sort, and filters. */
export async function listUsers(query: ListQuery = {}): Promise<User[]> {
  return fetchEnvelope(
    apiClient.get("/api/v1/users", listConfig(query)),
    zListUsersApiV1UsersGetResponse
  ) as Promise<User[]>;
}

/** Fetch a single user by ID. */
export async function getUser(id: string, config?: AxiosRequestConfig): Promise<User> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/users/${encodeURIComponent(id)}`, config),
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

/** List user groups in the acting tenant, with optional pagination, sort, and filters. */
export async function listUserGroups(query: ListQuery = {}): Promise<UserGroup[]> {
  return fetchEnvelope(
    apiClient.get("/api/v1/user-groups", listConfig(query)),
    zListUserGroupsApiV1UserGroupsGetResponse
  ) as Promise<UserGroup[]>;
}

/**
 * Fetch the acting tenant's user groups a given user belongs to.
 *
 * The read counterpart of {@link setUserGroups}. Membership is not carried on
 * the user record, so this is how a user-side screen learns which groups to
 * show without paging through every group in the tenant.
 */
export async function getUserGroupsForUser(userId: string): Promise<UserGroup[]> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/users/${encodeURIComponent(userId)}/groups`),
    zListGroupsForUserApiV1UsersUserIdGroupsGetResponse
  ) as Promise<UserGroup[]>;
}

/** Fetch a single user group by ID, including its member IDs. */
export async function getUserGroup(id: string, config?: AxiosRequestConfig): Promise<UserGroup> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/user-groups/${encodeURIComponent(id)}`, config),
    zGetUserGroupApiV1UserGroupsGroupIdGetResponse
  ) as Promise<UserGroup>;
}

/** Create a new user group in the acting tenant. */
export async function createUserGroup(body: UserGroupCreate): Promise<UserGroup> {
  return fetchEnvelope(
    apiClient.post("/api/v1/user-groups", body),
    zCreateUserGroupApiV1UserGroupsPostResponse
  ) as Promise<UserGroup>;
}

/**
 * Apply a partial update to a user group.
 *
 * Omitting `memberIds` leaves membership untouched; supplying a list replaces
 * it wholesale.
 */
export async function updateUserGroup(id: string, body: UserGroupUpdate): Promise<UserGroup> {
  return fetchEnvelope(
    apiClient.patch(`/api/v1/user-groups/${encodeURIComponent(id)}`, body),
    zUpdateUserGroupApiV1UserGroupsGroupIdPatchResponse
  ) as Promise<UserGroup>;
}

/** Delete a user group. Its members keep their accounts but lose its roles. */
export async function deleteUserGroup(id: string): Promise<void> {
  await fetchEnvelope(
    apiClient.delete(`/api/v1/user-groups/${encodeURIComponent(id)}`),
    zDeleteUserGroupApiV1UserGroupsGroupIdDeleteResponse
  );
}

/**
 * Replace the set of user groups a user belongs to, returning the updated user.
 *
 * The counterpart of editing a group's `memberIds`, so membership can be
 * managed from the user page as well as the group page. The returned user's
 * `groupRoles` already reflects the new membership.
 */
export async function setUserGroups(userId: string, groupIds: string[]): Promise<User> {
  return fetchEnvelope(
    apiClient.put(`/api/v1/users/${encodeURIComponent(userId)}/groups`, { groupIds }),
    zSetUserGroupsApiV1UsersUserIdGroupsPutResponse
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
  const resolved = await fetchEnvelope(
    apiClient.post("/api/v1/users/resolve-names", { ids: unique }),
    zResolveUserNamesApiV1UsersResolveNamesPostResponse
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
  return fetchEnvelope(
    apiClient.get("/api/v1/workflows", listConfig(query)),
    zListWorkflowsApiV1WorkflowsGetResponse
  ) as Promise<Workflow[]>;
}

/** Fetch a single workflow by ID. */
export async function getWorkflow(id: string, config?: AxiosRequestConfig): Promise<Workflow> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/workflows/${encodeURIComponent(id)}`, config),
    zGetWorkflowApiV1WorkflowsWorkflowIdGetResponse
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
  const workflow = (await fetchEnvelope(
    apiClient.post(`/api/v1/agent-skills/${encodeURIComponent(skillId)}/workflows`, body),
    zGenerateWorkflowApiV1AgentSkillsSkillIdWorkflowsPostResponse
  )) as Workflow;
  logger.info({ workflowId: workflow.id, skillId }, "workflow generation started");
  return workflow;
}

/**
 * Publish a workflow, making it executable. Freezes the current design into the
 * workflow's published snapshot on the backend.
 */
export async function publishWorkflow(id: string): Promise<Workflow> {
  return fetchEnvelope(
    apiClient.post(`/api/v1/workflows/${encodeURIComponent(id)}/publish`),
    zPublishWorkflowApiV1WorkflowsWorkflowIdPublishPostResponse
  ) as Promise<Workflow>;
}

/**
 * Summarize a workflow's design conversation into its AI-generated
 * description, overwriting the previous summary. A published workflow becomes
 * `modified`.
 */
export async function generateWorkflowDescription(id: string): Promise<Workflow> {
  return fetchEnvelope(
    apiClient.post(`/api/v1/workflows/${encodeURIComponent(id)}/generate-description`),
    zGenerateWorkflowDescriptionApiV1WorkflowsWorkflowIdGenerateDescriptionPostResponse
  ) as Promise<Workflow>;
}

/**
 * Drop a modified workflow's unpublished edits, restoring the task templates,
 * name, and description captured the last time it was published.
 */
export async function discardWorkflowChanges(id: string): Promise<Workflow> {
  return fetchEnvelope(
    apiClient.post(`/api/v1/workflows/${encodeURIComponent(id)}/discard-changes`),
    zDiscardWorkflowChangesApiV1WorkflowsWorkflowIdDiscardChangesPostResponse
  ) as Promise<Workflow>;
}

/**
 * Deactivate a workflow, returning it to draft. Task templates, description,
 * and the published snapshot are left untouched.
 */
export async function deactivateWorkflow(id: string): Promise<Workflow> {
  return fetchEnvelope(
    apiClient.post(`/api/v1/workflows/${encodeURIComponent(id)}/deactivate`),
    zDeactivateWorkflowApiV1WorkflowsWorkflowIdDeactivatePostResponse
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

/**
 * Execute a workflow, creating a WorkflowExecution that links the ADK session to
 * the workflow.
 *
 * @param id - Identifier of the workflow to run.
 * @param options - `toolMockIds` names the tool mocks the run should apply,
 *   stubbing those tools instead of calling them. Accepted only while the
 *   workflow is still `draft`; the server answers 409 `WORKFLOW_NOT_RUNNABLE`
 *   otherwise.
 */
export async function executeWorkflow(
  id: string,
  options: { toolMockIds?: string[] } = {}
): Promise<WorkflowExecution> {
  const body: ExecuteWorkflowRequest = { toolMockIds: options.toolMockIds ?? [] };
  const session = (await fetchEnvelope(
    apiClient.post(`/api/v1/workflows/${encodeURIComponent(id)}/execute`, body),
    zExecuteWorkflowApiV1WorkflowsWorkflowIdExecutePostResponse
  )) as WorkflowExecution;
  logger.info({ workflowExecutionId: session.id, workflowId: id }, "workflow executed");
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
  return fetchEnvelope(
    apiClient.get(
      `/api/v1/workflows/${encodeURIComponent(workflowId)}/task-templates`,
      listConfig(query)
    ),
    zListWorkflowTaskTemplatesApiV1WorkflowsWorkflowIdTaskTemplatesGetResponse
  ) as Promise<WorkflowTaskTemplate[]>;
}

/** Fetch a single WorkflowTaskTemplate by ID. */
export async function getWorkflowTaskTemplate(
  templateId: string,
  config?: AxiosRequestConfig
): Promise<WorkflowTaskTemplate> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/workflow-task-templates/${encodeURIComponent(templateId)}`, config),
    zGetWorkflowTaskTemplateApiV1WorkflowTaskTemplatesTemplateIdGetResponse
  ) as Promise<WorkflowTaskTemplate>;
}

/** Create a new task template under the workflow given in ``body.workflowId``. */
export async function createWorkflowTaskTemplate(
  body: WorkflowTaskTemplateCreate
): Promise<WorkflowTaskTemplate> {
  return fetchEnvelope(
    apiClient.post("/api/v1/workflow-task-templates", body),
    zCreateWorkflowTaskTemplateApiV1WorkflowTaskTemplatesPostResponse
  ) as Promise<WorkflowTaskTemplate>;
}

/** Apply a partial update to a task template. ``workflowId`` is not updatable. */
export async function updateWorkflowTaskTemplate(
  templateId: string,
  body: WorkflowTaskTemplateUpdate
): Promise<WorkflowTaskTemplate> {
  return fetchEnvelope(
    apiClient.patch(`/api/v1/workflow-task-templates/${encodeURIComponent(templateId)}`, body),
    zUpdateWorkflowTaskTemplateApiV1WorkflowTaskTemplatesTemplateIdPatchResponse
  ) as Promise<WorkflowTaskTemplate>;
}

/** Delete a task template by ID. */
export async function deleteWorkflowTaskTemplate(templateId: string): Promise<void> {
  await fetchEnvelope(
    apiClient.delete(`/api/v1/workflow-task-templates/${encodeURIComponent(templateId)}`),
    zDeleteWorkflowTaskTemplateApiV1WorkflowTaskTemplatesTemplateIdDeleteResponse
  );
}

/** One `/messages` record, as far as the attribution helpers below care. */
interface MessageSenderRecord {
  id?: string;
  role?: string;
  toolCallId?: string;
  senderUserId?: string | null;
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
function sendersFrom(records: MessageSenderRecord[]): Map<string, string> {
  const senders = new Map<string, string>();
  for (const record of records) {
    if (!record.senderUserId) continue;
    const key = record.role === "tool" ? record.toolCallId : record.id;
    if (key) senders.set(key, record.senderUserId);
  }
  return senders;
}

/**
 * Fetch the chat history of a workflow's design session.
 *
 * A design session has no record of its own, so it is addressed by its
 * workflow's id. Returns an empty list while the background generation run has
 * not started yet. The records carry `senderUserId` (and `workflowTaskId`,
 * always `null` here — a design session has no status-ful tasks) so the payload
 * shape matches {@link getWorkflowSessionMessages} and the chat components can
 * be reused unchanged.
 */
export async function getDesignSessionMessages(
  workflowId: string,
  config?: AxiosRequestConfig
): Promise<Message[]> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/workflows/${encodeURIComponent(workflowId)}/messages`, config),
    zGetDesignSessionMessagesApiV1WorkflowsWorkflowIdMessagesGetResponse
  ) as Promise<Message[]>;
}

/**
 * Fetch the per-message sender attribution for a workflow's design session.
 *
 * The design chat is shared by every developer in the tenant, so its messages
 * carry the same attribution a workflow session's do. Hits the same `/messages`
 * endpoint as {@link getDesignSessionMessages}, reading the `senderUserId` each
 * record carries; see {@link sendersFrom} for how the map is keyed. Messages
 * from the unattended background generation run have no sender, so callers fall
 * back to the workflow's `createdBy`.
 */
export async function getDesignSessionMessageSenders(
  workflowId: string
): Promise<Map<string, string>> {
  const records = (await fetchEnvelope(
    apiClient.get(`/api/v1/workflows/${encodeURIComponent(workflowId)}/messages`),
    zGetDesignSessionMessagesApiV1WorkflowsWorkflowIdMessagesGetResponse
  )) as MessageSenderRecord[];
  return sendersFrom(records);
}

/** Fetch a WorkflowExecution record by ID. */
export async function getWorkflowExecution(
  id: string,
  config?: AxiosRequestConfig
): Promise<WorkflowExecution> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/workflow-executions/${encodeURIComponent(id)}`, config),
    zGetWorkflowExecutionApiV1WorkflowExecutionsExecutionIdGetResponse
  ) as Promise<WorkflowExecution>;
}

/**
 * Fetch the chat history of a WorkflowExecution's workflow session.
 *
 * Unlike {@link getSessionMessages}, the history is keyed by the execution's
 * initiator on the backend, so any viewer (for example a designated approver)
 * sees the same conversation instead of a separate, empty session.
 */
export async function getWorkflowSessionMessages(
  executionId: string,
  config?: AxiosRequestConfig
): Promise<Message[]> {
  return fetchEnvelope(
    apiClient.get(
      `/api/v1/workflow-executions/${encodeURIComponent(executionId)}/messages`,
      config
    ),
    zGetWorkflowSessionMessagesApiV1WorkflowExecutionsExecutionIdMessagesGetResponse
  ) as Promise<Message[]>;
}

/**
 * Fetch the per-message sender attribution for a WorkflowExecution's chat.
 *
 * Hits the same `/messages` endpoint as {@link getWorkflowSessionMessages},
 * reading the `senderUserId` each record carries; see {@link sendersFrom} for
 * how the map is keyed. Agent messages and legacy history sent before
 * attribution existed are absent, so callers fall back to the execution's
 * initiator.
 */
export async function getWorkflowSessionMessageSenders(
  executionId: string
): Promise<Map<string, string>> {
  const records = (await fetchEnvelope(
    apiClient.get(`/api/v1/workflow-executions/${encodeURIComponent(executionId)}/messages`),
    zGetWorkflowSessionMessagesApiV1WorkflowExecutionsExecutionIdMessagesGetResponse
  )) as MessageSenderRecord[];
  return sendersFrom(records);
}

/**
 * Fetch the per-message WorkflowTask association for a WorkflowExecution's chat.
 *
 * Returns a map from message id (the ADK event id) to the id of the WorkflowTask
 * that was in progress when the message was produced. Messages produced outside
 * any task (for example the initial design exchange) are absent. Hits the same
 * `/messages` endpoint as {@link getWorkflowSessionMessages}, reading the
 * `workflowTaskId` each record carries alongside its `id`.
 */
export async function getWorkflowSessionMessageTasks(
  executionId: string
): Promise<Map<string, string>> {
  const records = (await fetchEnvelope(
    apiClient.get(`/api/v1/workflow-executions/${encodeURIComponent(executionId)}/messages`),
    zGetWorkflowSessionMessagesApiV1WorkflowExecutionsExecutionIdMessagesGetResponse
  )) as Array<{ id?: string; workflowTaskId?: string | null }>;
  const tasks = new Map<string, string>();
  for (const record of records) {
    if (record.id && record.workflowTaskId) {
      tasks.set(record.id, record.workflowTaskId);
    }
  }
  return tasks;
}

/** List WorkflowExecution records (newest first) with optional pagination, sort, and filters. */
export async function listWorkflowExecutions(query: ListQuery = {}): Promise<WorkflowExecution[]> {
  return fetchEnvelope(
    apiClient.get("/api/v1/workflow-executions", listConfig(query)),
    zListWorkflowExecutionsApiV1WorkflowExecutionsGetResponse
  ) as Promise<WorkflowExecution[]>;
}

/** Delete a WorkflowExecution by ID, along with its tasks and workflow session. */
export async function deleteWorkflowExecution(id: string): Promise<void> {
  await fetchEnvelope(
    apiClient.delete(`/api/v1/workflow-executions/${encodeURIComponent(id)}`),
    zDeleteWorkflowExecutionApiV1WorkflowExecutionsExecutionIdDeleteResponse
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
  return fetchEnvelope(
    apiClient.get(
      `/api/v1/workflow-executions/${encodeURIComponent(workflowExecutionId)}/workflow-tasks`,
      listConfig(query)
    ),
    zListWorkflowExecutionTasksApiV1WorkflowExecutionsExecutionIdWorkflowTasksGetResponse
  ) as Promise<WorkflowTask[]>;
}

/** Fetch a single WorkflowTask by ID. */
export async function getWorkflowTask(
  taskId: string,
  config?: AxiosRequestConfig
): Promise<WorkflowTask> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/workflow-tasks/${encodeURIComponent(taskId)}`, config),
    zGetWorkflowTaskApiV1WorkflowTasksTaskIdGetResponse
  ) as Promise<WorkflowTask>;
}

/** Create a new WorkflowTask under the workflow execution given in ``body.workflowExecutionId``. */
export async function createWorkflowTask(body: WorkflowTaskCreate): Promise<WorkflowTask> {
  return fetchEnvelope(
    apiClient.post("/api/v1/workflow-tasks", body),
    zCreateWorkflowTaskApiV1WorkflowTasksPostResponse
  ) as Promise<WorkflowTask>;
}

/** Apply a partial update to a WorkflowTask. ``workflowExecutionId`` is not updatable. */
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
 * Filter directive selecting only unread notifications.
 *
 * Used by the toolbar bell, which polls for unread items alone.
 */
export const UNREAD_ONLY_FILTER: FilterSpec = { field: "read", op: "eq", value: "false" };

/** List the current user's notifications (newest first) with optional pagination, sort, and filters. */
export async function listNotifications(query: ListQuery = {}): Promise<Notification[]> {
  return fetchEnvelope(
    apiClient.get("/api/v1/notifications", listConfig(query)),
    zListNotificationsApiV1NotificationsGetResponse
  ) as Promise<Notification[]>;
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
  return fetchEnvelope(
    apiClient.patch(`/api/v1/notifications/${encodeURIComponent(id)}`, data),
    zUpdateNotificationApiV1NotificationsNotificationIdPatchResponse
  ) as Promise<Notification>;
}

/** Mark all of the current user's unread notifications as read. */
export async function markAllNotificationsRead(): Promise<void> {
  await fetchEnvelope(
    apiClient.post("/api/v1/notifications/read-all"),
    zMarkAllNotificationsReadApiV1NotificationsReadAllPostResponse
  );
}

/** Permanently delete a single notification. */
export async function deleteNotification(id: string): Promise<void> {
  await fetchEnvelope(
    apiClient.delete(`/api/v1/notifications/${encodeURIComponent(id)}`),
    zDeleteNotificationApiV1NotificationsNotificationIdDeleteResponse
  );
}

/** List approval requests (newest first) with optional pagination, sort, and filters. */
export async function listApprovals(query: ListQuery = {}): Promise<Approval[]> {
  return fetchEnvelope(
    apiClient.get("/api/v1/approvals", listConfig(query)),
    zListApprovalsApiV1ApprovalsGetResponse
  ) as Promise<Approval[]>;
}

/** Fetch a single approval request by ID. */
export async function getApproval(id: string, config?: AxiosRequestConfig): Promise<Approval> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/approvals/${encodeURIComponent(id)}`, config),
    zGetApprovalApiV1ApprovalsApprovalIdGetResponse
  ) as Promise<Approval>;
}

/**
 * Fetch the certificate issued when an approval was granted.
 *
 * Reports what the approval actually authorized -- which MCP tools, until when,
 * and whether it has since been revoked. Rejects with a 404 when the approval
 * granted no tool authority: it was never approved, or it named no task.
 */
export async function getApprovalCertificate(
  id: string,
  config?: AxiosRequestConfig
): Promise<ApprovalCertificateRead> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/approvals/${encodeURIComponent(id)}/certificate`, config),
    zGetApprovalCertificateApiV1ApprovalsApprovalIdCertificateGetResponse
  ) as Promise<ApprovalCertificateRead>;
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
 * HttpAgent variant that sends the auth session cookie, the CSRF token, the
 * selected tenant header, and the impersonation header with each streaming
 * request. The agent endpoints are POSTs, so they need both the cookie
 * (`credentials: "include"`) and the double-submit `X-CSRF-Token` header; a
 * super_admin also needs `X-Tenant-Id` to reach these tenant-scoped endpoints
 * at all, and an impersonating admin needs `X-Impersonate-User-Id` for the
 * agent to act as the impersonated user -- unlike the axios-based calls
 * above, these bypass `apiClient`'s interceptor entirely, so the headers
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
