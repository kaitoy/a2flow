"""Use case service for Tag resources.

A thin wrapper over :class:`TagRepository`: tags carry a single business rule
of their own beyond the tenant scoping and uniqueness the repository already
enforces -- only an ``admin`` (or ``super_admin``) may set or clear the
``access_control`` flag (:mod:`models.tag`), even though tag writes as a whole
are open to ``developer`` too. A developer who could flip it would be able to
hide any record behind a tag their groups do not carry. It otherwise exists so
routers depend on a service like every other resource, and so ``get`` raises
instead of returning ``None``.

Attaching tags to records is *not* here — that belongs to each taggable
resource's own service (``SecretService.set_tags`` and friends), so the record's
existence and the caller's right to write it are checked by the layer that owns
those rules.
"""

from collections.abc import Collection, Sequence

from models.tag import Tag, TagCreate, TagUpdate
from models.user import Role, has_any_role
from repositories.exceptions import ForbiddenError, NotFoundError
from repositories.query import FilterSpec, SortSpec
from repositories.tag import TagRepository


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

    @staticmethod
    def _assert_may_set_access_control(caller_roles: Collection[str]) -> None:
        """Reject a caller who may not change a tag's ``access_control`` flag.

        Args:
            caller_roles: The caller's effective roles, including any inherited
                from their user groups (``EffectiveRolesDep``).

        Raises:
            ForbiddenError: If the caller is neither ``admin`` nor ``super_admin``.
        """
        if not has_any_role(caller_roles, Role.admin):
            raise ForbiddenError("Only an admin may change a tag's access-control flag")

    async def create(
        self, data: TagCreate, *, user_id: str, caller_roles: Collection[str]
    ) -> Tag:
        """Create a new Tag.

        Args:
            data: Creation payload.
            user_id: ID of the acting user recorded on the audit fields.
            caller_roles: The caller's effective roles, checked only when the
                payload turns the tag into an access-control gate.

        Returns:
            The created Tag.

        Raises:
            ForbiddenError: If ``access_control`` is set by a non-admin.
            UniqueViolationError: If the tenant already has a tag by that name.
        """
        if data.access_control:
            self._assert_may_set_access_control(caller_roles)
        return await self._repo.create(data, user_id=user_id)

    async def update(
        self,
        tag_id: str,
        data: TagUpdate,
        *,
        user_id: str,
        caller_roles: Collection[str],
    ) -> Tag:
        """Apply a partial update to a Tag.

        Renaming is safe at any time: records reference the tag by id, so every
        record carrying it follows the new name. Only a *change* to
        ``access_control`` needs the admin role: the edit form always sends
        the flag, so a developer echoing the stored value back must succeed.

        Args:
            tag_id: Identifier of the tag to update.
            data: Partial update payload.
            user_id: ID of the acting user recorded on ``updated_by``.
            caller_roles: The caller's effective roles, checked only when the
                payload would flip ``access_control``.

        Returns:
            The updated Tag.

        Raises:
            NotFoundError: If no tag exists with the given ID.
            ForbiddenError: If ``access_control`` would change and the caller
                is not an admin.
            UniqueViolationError: If the new name is already taken.
        """
        current = await self.get(tag_id)
        if (
            data.access_control is not None
            and data.access_control != current.access_control
        ):
            self._assert_may_set_access_control(caller_roles)
        return await self._repo.update(tag_id, data, user_id=user_id)

    async def delete(self, tag_id: str) -> None:
        """Delete a Tag, detaching it from every record that carried it.

        Args:
            tag_id: Identifier of the tag to delete.

        Raises:
            NotFoundError: If no tag exists with the given ID.
        """
        await self._repo.delete(tag_id)
