"""Use case service for Tag resources.

A thin wrapper over :class:`TagRepository`: tags carry a single business rule
of their own beyond the tenant scoping and uniqueness the repository already
enforces -- only an ``admin`` (or ``super_admin``) may create, edit, or delete
a tag that is, or would become, an access-control gate (``access_control`` on
:mod:`models.tag`) -- every field of such a tag, not just the flag itself --
even though tag writes as a whole are open to ``developer`` too. A developer
who could edit or delete one would be able to hide a record behind a tag their
groups do not carry, or remove the gate outright. It otherwise exists so
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
    def _assert_may_write_access_control_tag(caller_roles: Collection[str]) -> None:
        """Reject a caller who may not create, edit, or delete an access-control tag.

        Args:
            caller_roles: The caller's effective roles, including any inherited
                from their user groups (``EffectiveRolesDep``).

        Raises:
            ForbiddenError: If the caller is neither ``admin`` nor ``super_admin``.
        """
        if not has_any_role(caller_roles, Role.admin):
            raise ForbiddenError(
                "Only an admin may create, edit, or delete an access-control tag"
            )

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
            self._assert_may_write_access_control_tag(caller_roles)
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
        record carrying it follows the new name. But a tag that already is, or
        that this update would make, an access-control gate needs the admin
        role for the update as a whole -- every field, not just
        ``access_control`` -- since a developer able to edit one could hide a
        record behind a tag their groups do not carry.

        Args:
            tag_id: Identifier of the tag to update.
            data: Partial update payload.
            user_id: ID of the acting user recorded on ``updated_by``.
            caller_roles: The caller's effective roles, checked only when the
                tag is or would become an access-control gate.

        Returns:
            The updated Tag.

        Raises:
            NotFoundError: If no tag exists with the given ID.
            ForbiddenError: If the tag is or would become an access-control
                gate and the caller is not an admin.
            UniqueViolationError: If the new name is already taken.
        """
        current = await self.get(tag_id)
        if current.access_control or data.access_control:
            self._assert_may_write_access_control_tag(caller_roles)
        return await self._repo.update(tag_id, data, user_id=user_id)

    async def delete(self, tag_id: str, *, caller_roles: Collection[str]) -> None:
        """Delete a Tag, detaching it from every record that carried it.

        Args:
            tag_id: Identifier of the tag to delete.
            caller_roles: The caller's effective roles, checked only when the
                tag is an access-control gate.

        Raises:
            NotFoundError: If no tag exists with the given ID.
            ForbiddenError: If the tag is an access-control gate and the
                caller is not an admin.
        """
        current = await self.get(tag_id)
        if current.access_control:
            self._assert_may_write_access_control_tag(caller_roles)
        await self._repo.delete(tag_id)
