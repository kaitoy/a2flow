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

    Carries the ``server`` (name or URL) and a human-readable ``reason`` so the
    HTTP layer can surface them in the error envelope's ``details`` block when
    returning HTTP 502.
    """

    def __init__(self, server: str, reason: str) -> None:
        self.server = server
        self.reason = reason
        super().__init__(f"MCP server {server!r} unreachable: {reason}")


class RegistryUnavailableError(Exception):
    """Raised when the official MCP registry cannot be reached or errors out.

    Carries a human-readable ``reason`` so the HTTP layer can surface it in the
    error envelope's ``details`` block when returning HTTP 502.
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


class QueryValidationError(RepositoryError):
    """Raised when a sort or filter query parameter is malformed or references an unknown field.

    Carries a human-readable ``reason`` so the HTTP layer can surface it in the
    error envelope's ``details`` block when returning HTTP 400.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)
