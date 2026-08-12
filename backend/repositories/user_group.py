"""UserGroup repository: Protocol interface and SQLModel-backed implementation.

Groups are tenant-scoped, so every query filters on the repository's
``tenant_id`` and single-row fetches go through ``_get_scoped`` rather than
``session.get`` — a cross-tenant id therefore reads as "not found" instead of
"forbidden", matching the convention in
``.claude/rules/backend-patterns.md``.

Membership lives in :class:`~models.user_group.UserGroupMember` and is replaced
wholesale, the same shape as the tool bindings in
:mod:`repositories.workflow_task_template`. Members are validated against the
group's own tenant, which is what keeps a platform-scoped ``super_admin`` out
of every group and therefore keeps ``super_admin`` un-grantable through group
inheritance.
"""

from collections.abc import Sequence
from typing import Protocol

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.user import SYSTEM_USER_ID
from models.user_group import (
    UserGroup,
    UserGroupCreate,
    UserGroupMember,
    UserGroupRead,
    UserGroupUpdate,
)
from repositories._integrity import is_foreign_key_error
from repositories.exceptions import (
    ForeignKeyViolationError,
    NotFoundError,
    UniqueViolationError,
)
from repositories.query import FilterSpec, SortSpec, apply_filters, apply_sort
from repositories.user import UserRepository

#: Aliases for the builtin generics used in return annotations below. Both
#: classes define a ``list`` method, which shadows the builtin for every
#: annotation that follows it in the class body — the same workaround
#: :mod:`repositories.workflow_task_template` uses.
_StrList = list[str]
_GroupList = list[UserGroupRead]


class UserGroupRepository(Protocol):
    """Interface for UserGroup persistence operations."""

    async def get(self, group_id: str) -> UserGroupRead | None: ...

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> _GroupList: ...

    async def create(self, data: UserGroupCreate, *, user_id: str) -> UserGroupRead: ...

    async def update(
        self, group_id: str, data: UserGroupUpdate, *, user_id: str
    ) -> UserGroupRead: ...

    async def delete(self, group_id: str) -> None: ...

    async def exists(self, group_id: str) -> bool: ...

    async def group_ids_for_user(self, user_id: str) -> _StrList: ...

    async def list_for_user(self, user_id: str) -> _GroupList: ...

    async def set_groups_for_user(
        self, user_id: str, group_ids: Sequence[str]
    ) -> None: ...


class SqlUserGroupRepository:
    """SQLModel-backed implementation of UserGroupRepository.

    Takes the user repository as a collaborator so membership can be validated
    against real, same-tenant users before insertion — the cross-entity foreign
    key pattern used by :class:`repositories.workflow.SqlWorkflowRepository`.
    """

    def __init__(
        self, session: AsyncSession, users: UserRepository, *, tenant_id: str
    ) -> None:
        self._db = session
        self._users = users
        self._tenant_id = tenant_id

    # -- group lookups -------------------------------------------------------

    async def _get_scoped(self, group_id: str) -> UserGroup | None:
        """Return the group when it belongs to this repository's tenant, else ``None``."""
        stmt = select(UserGroup).where(
            UserGroup.id == group_id, UserGroup.tenant_id == self._tenant_id
        )
        return (await self._db.exec(stmt)).first()

    async def get(self, group_id: str) -> UserGroupRead | None:
        group = await self._get_scoped(group_id)
        if group is None:
            return None
        return UserGroupRead.from_group(
            group, member_ids=await self._members_for(group_id)
        )

    async def exists(self, group_id: str) -> bool:
        return await self._get_scoped(group_id) is not None

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> _GroupList:
        stmt = select(UserGroup).where(UserGroup.tenant_id == self._tenant_id)
        stmt = apply_filters(stmt, UserGroup, filters, readable=UserGroupRead)
        stmt = apply_sort(
            stmt,
            UserGroup,
            sort,
            default=[col(UserGroup.created_at).desc()],
            readable=UserGroupRead,
        )
        groups = list((await self._db.exec(stmt.limit(limit).offset(offset))).all())
        members = await self._members_for_many([g.id for g in groups])
        return [
            UserGroupRead.from_group(g, member_ids=members.get(g.id, []))
            for g in groups
        ]

    # -- writes --------------------------------------------------------------

    async def create(self, data: UserGroupCreate, *, user_id: str) -> UserGroupRead:
        """Create a group and place its initial members in it.

        Args:
            data: The validated creation payload.
            user_id: Id of the user performing the write, recorded as
                ``created_by`` / ``updated_by``.

        Returns:
            The stored group with its membership attached.

        Raises:
            ForeignKeyViolationError: If any member id is not a usable user of
                this tenant.
        """
        member_ids = list(data.member_ids or [])
        await self._validate_members(member_ids)
        group = UserGroup.model_validate(
            {
                **data.model_dump(exclude={"member_ids"}),
                "tenant_id": self._tenant_id,
                "created_by": user_id,
                "updated_by": user_id,
            }
        )
        self._db.add(group)
        for member_id in member_ids:
            self._db.add(UserGroupMember(group_id=group.id, user_id=member_id))
        await self._commit(user_id=user_id, name=data.name)
        await self._db.refresh(group)
        return UserGroupRead.from_group(group, member_ids=sorted(member_ids))

    async def update(
        self, group_id: str, data: UserGroupUpdate, *, user_id: str
    ) -> UserGroupRead:
        """Apply a partial update, replacing membership wholesale when supplied.

        Args:
            group_id: Identifier of the group to update.
            data: Fields to change; a ``member_ids`` of ``None`` leaves
                membership untouched.
            user_id: Id of the user performing the write.

        Returns:
            The updated group with its membership attached.

        Raises:
            NotFoundError: If no group with that id exists in this tenant.
            ForeignKeyViolationError: If any member id is not a usable user of
                this tenant.
        """
        group = await self._get_scoped(group_id)
        if group is None:
            raise NotFoundError("UserGroup", group_id)
        group.sqlmodel_update(
            data.model_dump(exclude_unset=True, exclude={"member_ids"})
        )
        group.updated_by = user_id
        self._db.add(group)
        if data.member_ids is not None:
            await self._validate_members(data.member_ids)
            await self._replace_members(group_id, data.member_ids)
        await self._commit(user_id=user_id, name=data.name or group.name)
        await self._db.refresh(group)
        return UserGroupRead.from_group(
            group, member_ids=await self._members_for(group_id)
        )

    async def delete(self, group_id: str) -> None:
        """Delete a group; its membership rows cascade away with it.

        Args:
            group_id: Identifier of the group to delete.

        Raises:
            NotFoundError: If no group with that id exists in this tenant.
        """
        group = await self._get_scoped(group_id)
        if group is None:
            raise NotFoundError("UserGroup", group_id)
        await self._db.delete(group)
        await self._db.commit()

    async def _commit(self, *, user_id: str, name: str) -> None:
        """Commit, translating the two constraint failures a group write can hit.

        An acting user who does not exist fails the ``created_by`` /
        ``updated_by`` foreign key; a name already taken in this tenant fails
        ``uq_user_groups_tenant_id_name``. Everything else propagates.

        Args:
            user_id: The acting user id recorded on the row.
            name: The group name the write was attempting to store, echoed back
                in the conflict error.

        Raises:
            ForeignKeyViolationError: If the acting user does not exist.
            UniqueViolationError: If the name is already used in this tenant.
        """
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            if is_foreign_key_error(e):
                raise ForeignKeyViolationError("User", user_id) from e
            raise UniqueViolationError("UserGroup", "name", name) from e

    # -- membership from the user side ---------------------------------------

    async def group_ids_for_user(self, user_id: str) -> _StrList:
        """Return the ids of this tenant's groups that ``user_id`` belongs to.

        Args:
            user_id: Identifier of the user whose memberships to list.

        Returns:
            The sorted group ids, restricted to this repository's tenant.
        """
        stmt = (
            select(UserGroupMember.group_id)
            .join(UserGroup, onclause=col(UserGroup.id) == UserGroupMember.group_id)
            .where(
                col(UserGroupMember.user_id) == user_id,
                col(UserGroup.tenant_id) == self._tenant_id,
            )
        )
        return sorted((await self._db.exec(stmt)).all())

    async def list_for_user(self, user_id: str) -> _GroupList:
        """Return this tenant's groups that ``user_id`` belongs to.

        The membership counterpart of :meth:`list`, used by the user detail
        page so it never has to page through every group looking for one
        member.

        Args:
            user_id: Identifier of the user whose memberships to list.

        Returns:
            The groups, ordered by name, each with its membership attached.
        """
        stmt = (
            select(UserGroup)
            .join(
                UserGroupMember,
                onclause=col(UserGroup.id) == UserGroupMember.group_id,
            )
            .where(
                col(UserGroupMember.user_id) == user_id,
                col(UserGroup.tenant_id) == self._tenant_id,
            )
            .order_by(col(UserGroup.name))
        )
        groups = list((await self._db.exec(stmt)).all())
        members = await self._members_for_many([g.id for g in groups])
        return [
            UserGroupRead.from_group(g, member_ids=members.get(g.id, []))
            for g in groups
        ]

    async def set_groups_for_user(self, user_id: str, group_ids: Sequence[str]) -> None:
        """Replace the set of this tenant's groups ``user_id`` belongs to.

        A user can only ever be a member of their own tenant's groups (see
        :meth:`_validate_members`), so replacing this tenant's set replaces
        their memberships entirely.

        Args:
            user_id: Identifier of the user whose membership to set.
            group_ids: Ids of the groups the user should end up in.

        Raises:
            ForeignKeyViolationError: If the user is not a usable member of
                this tenant, or any group id is not a group of this tenant.
        """
        await self._validate_members([user_id])
        for group_id in group_ids:
            if await self._get_scoped(group_id) is None:
                raise ForeignKeyViolationError("UserGroup", group_id)
        existing = await self._db.exec(
            select(UserGroupMember)
            .join(UserGroup, onclause=col(UserGroup.id) == UserGroupMember.group_id)
            .where(
                col(UserGroupMember.user_id) == user_id,
                col(UserGroup.tenant_id) == self._tenant_id,
            )
        )
        for row in existing.all():
            await self._db.delete(row)
        await self._db.flush()
        for group_id in group_ids:
            self._db.add(UserGroupMember(group_id=group_id, user_id=user_id))
        await self._db.commit()

    # -- membership helpers --------------------------------------------------

    async def _members_for(self, group_id: str) -> _StrList:
        """Return the sorted member ids of one group."""
        stmt = select(UserGroupMember.user_id).where(
            col(UserGroupMember.group_id) == group_id
        )
        return sorted((await self._db.exec(stmt)).all())

    async def _members_for_many(self, group_ids: Sequence[str]) -> dict[str, _StrList]:
        """Return a mapping of group id to its sorted member ids, in one query."""
        out: dict[str, _StrList] = {gid: [] for gid in group_ids}
        if not group_ids:
            return out
        stmt = select(UserGroupMember).where(
            col(UserGroupMember.group_id).in_(group_ids)
        )
        for row in (await self._db.exec(stmt)).all():
            out.setdefault(row.group_id, []).append(row.user_id)
        return {gid: sorted(members) for gid, members in out.items()}

    async def _replace_members(self, group_id: str, member_ids: Sequence[str]) -> None:
        """Delete every membership row of ``group_id`` and insert ``member_ids`` afresh."""
        existing = await self._db.exec(
            select(UserGroupMember).where(col(UserGroupMember.group_id) == group_id)
        )
        for row in existing.all():
            await self._db.delete(row)
        # Flush the deletes before the inserts: re-adding a member that is
        # already present would otherwise collide on the composite primary key
        # when SQLAlchemy orders the INSERT ahead of the DELETE.
        await self._db.flush()
        for member_id in member_ids:
            self._db.add(UserGroupMember(group_id=group_id, user_id=member_id))

    async def _validate_members(self, member_ids: Sequence[str]) -> None:
        """Reject member ids that are not usable users of this group's tenant.

        A user qualifies only when they exist, are not soft-deleted, are not
        the seeded system user, and belong to this repository's tenant. The
        tenant check is what keeps platform-scoped users — every ``super_admin``
        and the system user — out of groups, and therefore keeps ``super_admin``
        un-grantable through group inheritance.

        A user of another tenant is reported as a missing foreign key rather
        than a forbidden one, so membership never confirms that an id exists
        somewhere else.

        Args:
            member_ids: The proposed member ids (deduplicated by the payload
                model).

        Raises:
            ForeignKeyViolationError: For the first id that does not qualify.
        """
        if not member_ids:
            return
        usable = {
            user.id
            for user in await self._users.get_many(list(member_ids))
            if user.deleted_at is None
            and user.id != SYSTEM_USER_ID
            and user.tenant_id == self._tenant_id
        }
        for member_id in member_ids:
            if member_id not in usable:
                raise ForeignKeyViolationError("User", member_id)
