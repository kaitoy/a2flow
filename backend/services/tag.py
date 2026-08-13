"""Use case service for Tag resources.

A thin wrapper over :class:`TagRepository`: tags carry no business rules of
their own beyond the tenant scoping and uniqueness the repository already
enforces. It exists so routers depend on a service like every other resource,
and so ``get`` raises instead of returning ``None``.

Attaching tags to records is *not* here — that belongs to each taggable
resource's own service (``SecretService.set_tags`` and friends), so the record's
existence and the caller's right to write it are checked by the layer that owns
those rules.
"""

from collections.abc import Sequence

from models.tag import Tag, TagCreate, TagUpdate
from repositories import TagRepository
from repositories.exceptions import NotFoundError
from repositories.query import FilterSpec, SortSpec


class TagService:
    """Application service orchestrating Tag operations."""

    def __init__(self, repo: TagRepository) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing Tag persistence.
        """
        self._repo = repo

    async def get(self, tag_id: str) -> Tag:
        """Return the Tag with the given ID.

        Args:
            tag_id: Identifier of the tag to fetch.

        Returns:
            The matching Tag.

        Raises:
            NotFoundError: If no tag exists with the given ID.
        """
        tag = await self._repo.get(tag_id)
        if tag is None:
            raise NotFoundError("Tag", tag_id)
        return tag

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[Tag]:
        """Return a page of Tag records.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.

        Returns:
            The requested page of tags.
        """
        return await self._repo.list(
            limit=limit, offset=offset, sort=sort, filters=filters
        )

    async def create(self, data: TagCreate, *, user_id: str) -> Tag:
        """Create a new Tag.

        Args:
            data: Creation payload.
            user_id: ID of the acting user recorded on the audit fields.

        Returns:
            The created Tag.

        Raises:
            UniqueViolationError: If the tenant already has a tag by that name.
        """
        return await self._repo.create(data, user_id=user_id)

    async def update(self, tag_id: str, data: TagUpdate, *, user_id: str) -> Tag:
        """Apply a partial update to a Tag.

        Renaming is safe at any time: records reference the tag by id, so every
        record carrying it follows the new name.

        Args:
            tag_id: Identifier of the tag to update.
            data: Partial update payload.
            user_id: ID of the acting user recorded on ``updated_by``.

        Returns:
            The updated Tag.

        Raises:
            NotFoundError: If no tag exists with the given ID.
            UniqueViolationError: If the new name is already taken.
        """
        return await self._repo.update(tag_id, data, user_id=user_id)

    async def delete(self, tag_id: str) -> None:
        """Delete a Tag, detaching it from every record that carried it.

        Args:
            tag_id: Identifier of the tag to delete.

        Raises:
            NotFoundError: If no tag exists with the given ID.
        """
        await self._repo.delete(tag_id)
