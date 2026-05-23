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
