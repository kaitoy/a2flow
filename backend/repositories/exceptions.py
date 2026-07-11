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
    """Raised when a registered remote MCP server cannot be reached or errors out.

    Carries the ``server`` (name or URL, already known to the caller) and a
    ``reason`` string. The HTTP layer logs ``reason`` server-side but never
    returns it to the client, since it echoes the raw caught exception text.
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


class SecretResolutionError(Exception):
    """Raised when a ``${secret:NAME}`` reference cannot be resolved to a value.

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


class QueryValidationError(RepositoryError):
    """Raised when a sort or filter query parameter is malformed or references an unknown field.

    Carries a human-readable ``reason`` so the HTTP layer can surface it in the
    error envelope's ``details`` block when returning HTTP 400.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)
