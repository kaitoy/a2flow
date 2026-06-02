"""Domain exceptions raised by repository implementations."""


class RepositoryError(Exception):
    """Base class for all repository errors."""


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
