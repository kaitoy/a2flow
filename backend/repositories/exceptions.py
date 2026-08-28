"""Domain exceptions raised by repository implementations."""


class RepositoryError(Exception):
    """Base class for all repository errors."""


class UnauthorizedError(Exception):
    """Raised when a request lacks a valid authenticated session.

    Mapped to HTTP 401 with the ``UNAUTHENTICATED`` error code. The message is
    intentionally generic to avoid leaking whether a username exists.
    """

    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message)


class CsrfError(Exception):
    """Raised when a state-changing request fails CSRF validation.

    Mapped to HTTP 403 with the ``CSRF_FAILED`` error code.
    """

    def __init__(self, message: str = "CSRF validation failed") -> None:
        super().__init__(message)


class ForbiddenError(Exception):
    """Raised when an authenticated user is not allowed to perform an action.

    Mapped to HTTP 403 with the ``FORBIDDEN`` error code. Unlike
    :class:`UnauthorizedError` (no valid session), the caller is authenticated but
    lacks permission for the specific resource — for example resolving an approval
    they are not the designated approver of.
    """

    def __init__(self, message: str = "Operation not permitted") -> None:
        super().__init__(message)


class NotFoundError(RepositoryError):
    """Raised when a requested entity does not exist in the database."""

    def __init__(self, entity: str, id_: str) -> None:
        self.entity = entity
        self.id = id_
        super().__init__(f"{entity} {id_!r} not found")


class ForeignKeyViolationError(RepositoryError):
    """Raised when a required related entity (foreign key) does not exist."""

    def __init__(self, entity: str, id_: str) -> None:
        self.entity = entity
        self.id = id_
        super().__init__(f"{entity} {id_!r} not found")


class ReferencedError(RepositoryError):
    """Raised when deleting an entity that is still referenced by other records."""


class UniqueViolationError(RepositoryError):
    """Raised when creating or updating a record would violate a unique constraint.

    Carries the ``entity`` name, the offending unique ``field``, and the duplicate
    ``value`` so the HTTP layer can surface them in the error envelope's
    ``details`` block when returning HTTP 409.
    """

    def __init__(self, entity: str, field: str, value: str) -> None:
        self.entity = entity
        self.field = field
        self.value = value
        super().__init__(f"{entity} with {field} {value!r} already exists")


class McpConnectionError(Exception):
    """Raised when a registered MCP server cannot be reached, launched, or errors out.

    Carries the ``server`` (name, URL, or command line — already known to the
    caller) and a ``reason`` string. The HTTP layer logs ``reason`` server-side
    but never returns it to the client, since it echoes the raw caught
    exception text.
    """

    def __init__(self, server: str, reason: str) -> None:
        self.server = server
        self.reason = reason
        super().__init__(f"MCP server {server!r} unreachable: {reason}")


class SkillCloneError(Exception):
    """Raised when an AgentSkill repository cannot be cloned or its directory resolved.

    Carries the ``skill_id`` and a ``reason`` string. The HTTP layer logs
    ``reason`` server-side but never returns it to the client, mirroring
    :class:`McpConnectionError`, since it can embed raw git/network failure
    text.
    """

    def __init__(self, skill_id: str, reason: str) -> None:
        self.skill_id = skill_id
        self.reason = reason
        super().__init__(f"failed to prepare skill {skill_id!r}: {reason}")


class SkillNotReadyError(RepositoryError):
    """Raised when an AgentSkill has no published revision to run against.

    A skill becomes usable only once its clone has published a revision
    directory and recorded the sha on ``AgentSkill.commit_sha``. Until then —
    while the registration clone is still running, or after it failed — running
    a workflow on it has nothing to load. Also raised when the revision a
    WorkflowExecution pinned is no longer on disk and the skill has no current
    revision to fall back on, which an admin fixes by pulling the skill again.

    Carries the ``skill_id`` so the HTTP layer can surface it in the error
    envelope's ``details`` block when returning HTTP 409.
    """

    def __init__(self, skill_id: str) -> None:
        self.skill_id = skill_id
        super().__init__(
            f"AgentSkill {skill_id!r} has no published revision; pull it first"
        )


class WorkflowNotRunnableError(RepositoryError):
    """Raised when a Workflow cannot be executed or published in its current state.

    Executing requires a ``published`` or ``modified`` workflow — or, for a
    caller holding the ``developer`` or ``super_admin`` role, a ``draft``
    workflow — and publishing requires at least one task template plus a design
    that is not already published. A workflow still ``generating``, left in
    ``failed``, holding no task templates, already ``published`` with no changes to
    promote, or a ``draft`` run attempted by a plain ``requester`` has nothing
    runnable.

    Carries the ``workflow_id`` and a human-readable ``reason`` so the HTTP
    layer can surface them in the error envelope's ``details`` block when
    returning HTTP 409.
    """

    def __init__(self, workflow_id: str, reason: str) -> None:
        self.workflow_id = workflow_id
        self.reason = reason
        super().__init__(f"Workflow {workflow_id!r} is not runnable: {reason}")


class ApprovalAlreadyResolvedError(RepositoryError):
    """Raised when a decision is submitted for an approval that already has one.

    A decision is final. This never mattered much while an approval was
    addressed to a single user -- only they could submit one, and the UI
    disables the controls once a decision lands -- but a group-addressed
    approval is genuinely raced: two members can open the same chat and both
    click Approve. Silently letting the second write win would overwrite the
    first decision and leave ``decided_by`` naming whoever clicked last, which
    is not who resolved the request.

    Only a *status* change is blocked. Editing the ``response`` comment of an
    already-decided approval stays allowed, which
    :class:`~models.approval.Approval` explicitly contemplates.

    Carries the ``approval_id`` and the ``status`` already recorded so the HTTP
    layer can surface both in the error envelope's ``details`` block when
    returning HTTP 409.
    """

    def __init__(self, approval_id: str, status: str) -> None:
        self.approval_id = approval_id
        self.status = status
        super().__init__(f"Approval {approval_id!r} was already resolved as {status!r}")


class WorkflowNotModifiedError(RepositoryError):
    """Raised when a Workflow has no unpublished changes to discard.

    ``POST /workflows/{id}/discard-changes`` only makes sense for a workflow in
    the ``modified`` state — one that was published and then edited, so a
    published snapshot exists to restore. Any other status (including a
    ``published`` workflow that is already in sync) has nothing to discard.

    Carries the ``workflow_id`` so the HTTP layer can surface it in the error
    envelope's ``details`` block when returning HTTP 409.
    """

    def __init__(self, workflow_id: str) -> None:
        self.workflow_id = workflow_id
        super().__init__(f"Workflow {workflow_id!r} has no unpublished changes")


class WorkflowNotDeactivatableError(RepositoryError):
    """Raised when a Workflow is not published/modified, so there is nothing to deactivate.

    ``POST /workflows/{id}/deactivate`` only makes sense for a workflow that is
    currently ``published`` or ``modified`` — returning it to ``draft`` revokes
    the ``requester`` role's execute access until it is published again. Any
    other status (``draft``, ``generating``, ``failed``) has nothing to
    deactivate.

    Carries the ``workflow_id`` so the HTTP layer can surface it in the error
    envelope's ``details`` block when returning HTTP 409.
    """

    def __init__(self, workflow_id: str) -> None:
        self.workflow_id = workflow_id
        super().__init__(f"Workflow {workflow_id!r} is not published")


class WorkflowDescriptionNotGeneratableError(RepositoryError):
    """Raised when a Workflow's description cannot be generated in its current state.

    ``POST /workflows/{id}/generate-description`` summarizes the workflow's
    design conversation, so it needs that conversation to exist and to be
    settled: a workflow still ``generating`` has a design run in flight, and
    one without a design session (or with an empty one) has nothing to
    summarize.

    Carries the ``workflow_id`` and a human-readable ``reason`` so the HTTP
    layer can surface them in the error envelope's ``details`` block when
    returning HTTP 409.
    """

    def __init__(self, workflow_id: str, reason: str) -> None:
        self.workflow_id = workflow_id
        self.reason = reason
        super().__init__(
            f"Workflow {workflow_id!r} has no description to generate: {reason}"
        )


class SummarizationFailedError(RepositoryError):
    """Raised when the LLM call summarizing a design conversation fails.

    Unlike the background generation job — which records the failure on the
    workflow row and moves on — the on-demand
    ``POST /workflows/{id}/generate-description`` has nothing else to deliver,
    so the failure surfaces as HTTP 502.

    Carries the ``workflow_id`` and a ``reason``. The HTTP layer logs ``reason``
    server-side but never returns it to the client, since it echoes the raw
    caught exception text.
    """

    def __init__(self, workflow_id: str, reason: str) -> None:
        self.workflow_id = workflow_id
        self.reason = reason
        super().__init__(
            f"Failed to summarize the design conversation of workflow "
            f"{workflow_id!r}: {reason}"
        )


class RegistryUnavailableError(Exception):
    """Raised when the official MCP registry cannot be reached or errors out.

    Carries a ``reason`` string. The HTTP layer logs ``reason`` server-side
    but never returns it to the client, since it echoes the raw caught
    exception text.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"MCP registry unavailable: {reason}")


class DependencyCycleError(RepositoryError):
    """Raised when adding WorkflowTask dependency edges would create a cycle.

    Carries the ``task_id`` whose new dependencies introduce the cycle and the
    offending ``depends_on_id`` (the edge endpoint that closes the loop), so the
    HTTP layer can surface them in the error envelope's ``details`` block when
    returning HTTP 409.
    """

    def __init__(self, task_id: str, depends_on_id: str) -> None:
        self.task_id = task_id
        self.depends_on_id = depends_on_id
        super().__init__(
            f"Dependency from task {task_id!r} on {depends_on_id!r} "
            "would create a cycle"
        )


class AvatarValidationError(RepositoryError):
    """Raised when an uploaded avatar image has an unsupported type or exceeds the size limit.

    Carries a human-readable ``reason`` so the HTTP layer can surface it in the
    error envelope's ``details`` block when returning HTTP 422.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class McpServerValidationError(RepositoryError):
    """Raised when an MCPServer create/update would leave an invalid transport shape.

    ``MCPServerCreate`` enforces the shape at the request boundary, but a PATCH
    body alone cannot: the rule applies to the merged result of the stored
    record and the partial update, which only the service can compute. Carries
    a human-readable ``reason`` surfaced in the error envelope's ``details``
    block when returning HTTP 422.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class McpToolMockValidationError(RepositoryError):
    """Raised when an MCPToolMock create/update would leave an invalid target.

    ``McpToolMockCreate`` enforces the rule at the request boundary, but a PATCH
    body alone cannot: whether the merged mock targets a registered server or a
    built-in tool depends on the stored record, which only the service can see.
    Carries a human-readable ``reason`` surfaced in the error envelope's
    ``details`` block when returning HTTP 422.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class SecretValidationError(RepositoryError):
    """Raised when a Secret create/update would leave an invalid per-type shape.

    ``SecretCreate`` enforces the shape at the request boundary, but a PATCH
    body alone cannot: the rule applies to the merged result of the stored
    record and the partial update, which only the service can compute. Carries
    a human-readable ``reason`` surfaced in the error envelope's ``details``
    block when returning HTTP 422.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class SystemSettingsValidationError(RepositoryError):
    """Raised when a system-settings update would leave an unusable SMTP configuration.

    Enabling email delivery needs a relay host and a sender address, and a relay
    that requires a username needs a password to go with it. The rule applies to
    the merged result of the stored record and the partial update (mirrors
    :class:`SecretValidationError`), which only the service can compute. Carries
    a human-readable ``reason`` surfaced in the error envelope's ``details``
    block when returning HTTP 422.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class EmailSendError(Exception):
    """Raised when a message could not be handed to the configured SMTP relay.

    Carries a ``reason`` string. The HTTP layer logs ``reason`` server-side but
    never returns it to the client, mirroring :class:`McpConnectionError`: the
    text echoes the raw ``smtplib`` failure, which can quote relay banners and
    the configured credentials' username back at the caller.

    ``permanent`` says whether retrying could ever help. Only
    :mod:`infrastructure.email_sender` sets it, because only there is the
    ``smtplib`` exception type still in hand; the email queue worker reads it to
    decide between scheduling another attempt and writing the message off. The
    HTTP layer ignores it — a caller who asked for a test send gets the same 502
    either way.
    """

    def __init__(self, reason: str, *, permanent: bool = False) -> None:
        self.reason = reason
        self.permanent = permanent
        super().__init__(f"failed to send email: {reason}")


class UserValidationError(RepositoryError):
    """Raised when a User create/update would combine super_admin with a tenant.

    A super admin is platform-scoped by definition and must never carry a
    tenant_id. On a PATCH the rule applies to the merged result of the stored
    record and the partial update (mirrors :class:`SecretValidationError`),
    which only the service can compute. Carries a human-readable ``reason``
    surfaced in the error envelope's ``details`` block when returning HTTP 422.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class SecretResolutionError(Exception):
    """Raised when a ``${secret:NAME/KEY}`` reference cannot be resolved to a value.

    Covers a missing secret name, a ciphertext that cannot be decrypted, a
    Vault read failure, and a ``vault``-type secret with no Vault connection
    configured. Carries the ``secret_name`` (already known to the caller) and a
    ``reason`` string; the HTTP layer logs ``reason`` server-side but never
    returns it to the client, mirroring :class:`McpConnectionError`.
    """

    def __init__(self, secret_name: str, reason: str) -> None:
        self.secret_name = secret_name
        self.reason = reason
        super().__init__(f"failed to resolve secret {secret_name!r}: {reason}")


class SessionRunInProgressError(RepositoryError):
    """Raised when an agent run is requested for a session already being run.

    Only one process may drive a given ADK session at a time (see
    ``infrastructure/locks.py``): a second concurrent run would reason over an
    in-memory session that the first run's appends have already left behind.
    Carries the ``thread_id`` so the HTTP layer can surface it in the error
    envelope's ``details`` block when returning HTTP 409.
    """

    def __init__(self, thread_id: str) -> None:
        self.thread_id = thread_id
        super().__init__(
            f"An agent run is already in progress for session {thread_id!r}"
        )


class OutboundEmailNotDeletableError(RepositoryError):
    """Raised when deleting an OutboundEmail row that is not in a terminal status.

    A ``pending``/``sending`` row may be actively claimed by the queue worker
    (see :mod:`repositories.outbound_email_queue`); only ``sent``/``failed``
    rows -- the terminal states -- may be deleted through the super_admin API.

    Carries the ``email_id`` and the ``status`` found so the HTTP layer can
    surface both in the error envelope's ``details`` block when returning
    HTTP 409.
    """

    def __init__(self, email_id: str, status: str) -> None:
        self.email_id = email_id
        self.status = status
        super().__init__(
            f"OutboundEmail {email_id!r} cannot be deleted while its status "
            f"is {status!r}; only 'sent' or 'failed' rows may be deleted"
        )


class QueryValidationError(RepositoryError):
    """Raised when a sort or filter query parameter is malformed or references an unknown field.

    Carries a human-readable ``reason`` so the HTTP layer can surface it in the
    error envelope's ``details`` block when returning HTTP 400.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)
