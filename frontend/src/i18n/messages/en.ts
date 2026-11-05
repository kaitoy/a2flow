/**
 * @module i18n/messages/en — The English catalog, which defines the set of keys
 * every other language must provide. Its text is what the GUI shows by default.
 */

/** A translated message; plural messages are selected by `Intl.PluralRules` from `count`. */
export type Message = string | (Partial<Record<Intl.LDMLPluralRule, string>> & { other: string });

/** English messages by key. */
export const en = {
  "app.description": "AI chat powered by Google ADK",
  "errors.APPROVAL_ALREADY_RESOLVED": "This approval has already been decided.",
  "errors.CONFLICT_REFERENCED": "This is still in use by other items and cannot be deleted.",
  "errors.CONFLICT_UNIQUE": "An item with the same value already exists.",
  "errors.CSRF_FAILED": "Your session could not be verified. Reload the page and try again.",
  "errors.DEPENDENCY_CYCLE": "The task dependencies form a cycle.",
  "errors.ELICITATION_ALREADY_ANSWERED": "This question has already been answered or has expired.",
  "errors.EMAIL_SEND_FAILED": "The email could not be sent.",
  "errors.FORBIDDEN": "You do not have permission to do this.",
  "errors.FOREIGN_KEY_VIOLATION": "An item this refers to could not be found.",
  "errors.HTTP": "Request failed with status {status}.",
  "errors.INTERNAL_ERROR": "An unexpected server error occurred.",
  "errors.INVALID_AGENT_SKILL": "The skill settings are not valid.",
  "errors.INVALID_AVATAR": "The avatar image cannot be used.",
  "errors.INVALID_KNOWLEDGE_SOURCE": "The knowledge source cannot be registered.",
  "errors.INVALID_MCP_SERVER": "The MCP server settings are not valid.",
  "errors.INVALID_MCP_TOOL_MOCK": "The tool mock settings are not valid.",
  "errors.INVALID_QUERY": "The filter or sort could not be applied.",
  "errors.INVALID_SECRET": "The secret settings are not valid.",
  "errors.INVALID_SESSION_FILE": "The file cannot be attached to this session.",
  "errors.INVALID_SESSION_INPUT": "This input cannot be sent to the session.",
  "errors.INVALID_SYSTEM_SETTINGS": "The system settings are not valid.",
  "errors.INVALID_TENANT": "The tenant settings are not valid.",
  "errors.INVALID_USER": "The user settings are not valid.",
  "errors.MCP_UNREACHABLE": "The MCP server could not be reached.",
  "errors.NETWORK_ERROR": "Unable to reach the server. Please check your connection and try again.",
  "errors.NOT_FOUND": "The item could not be found.",
  "errors.OUTBOUND_EMAIL_NOT_DELETABLE": "An email still being sent cannot be deleted.",
  "errors.REGISTRY_UNREACHABLE": "The MCP registry could not be reached.",
  "errors.SECRET_RESOLUTION_FAILED": "A secret reference could not be resolved.",
  "errors.SESSION_AWAITING_APPROVAL": "This session is waiting for an approval.",
  "errors.SESSION_RUN_IN_PROGRESS": "A run is already in progress in this session.",
  "errors.SKILL_CLONE_FAILED": "The skill repository could not be cloned.",
  "errors.SKILL_NOT_READY": "The skill has no published revision yet.",
  "errors.SUMMARIZATION_FAILED": "The summary could not be generated.",
  "errors.TOO_MANY_LOGIN_ATTEMPTS": "Too many failed sign-in attempts. Wait a while and try again.",
  "errors.UNAUTHENTICATED": "Invalid username or password.",
  "errors.VALIDATION_ERROR": "The request is not valid. Check what you entered.",
  "errors.WORKFLOW_NOT_DEACTIVATABLE":
    "The workflow is not published, so there is nothing to deactivate.",
  "errors.WORKFLOW_NOT_MODIFIED": "The workflow has no unpublished changes to discard.",
  "errors.WORKFLOW_NOT_RUNNABLE": "The workflow cannot do this in its current state.",
  "errors.WORKFLOW_PROMPT_NOT_GENERATABLE":
    "The prompt cannot be generated for this workflow right now.",
  "errors.generic": "Something went wrong. Please try again.",
  "profile.language.browser": "Follow browser language",
  "profile.language.impersonating": "Your language is not changed while acting as another user.",
  "profile.language.label": "Language",
  "profile.preferences": "Preferences",
  "time.daysAgo": "{count}d ago",
  "time.hoursAgo": "{count}h ago",
  "time.justNow": "just now",
  "time.minutesAgo": "{count}m ago",
  "users.names.superAdmin": "Super Admin",
  "users.names.system": "System User",
} satisfies Record<string, Message>;

/** A key of the catalog. */
export type MessageKey = keyof typeof en;

/** A complete catalog: every key, and only those. */
export type Messages = Record<MessageKey, Message>;
