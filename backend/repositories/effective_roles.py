"""Resolution of the roles users inherit from the groups they belong to.

A user's **effective roles** are their direct grants (``users.roles``) unioned
with the roles of every :class:`~models.user_group.UserGroup` they are a member
of. Nothing is denormalized onto ``users``: this module resolves the inherited
half on demand, so removing a user from a group takes effect on the very next
request and no stale grant can survive a missed cache invalidation.

Queries here are **deliberately not tenant-scoped**, unlike the rest of
:mod:`repositories`. Two reasons:

* The caller may be platform-scoped. ``dependencies.auth.get_current_tenant_id``
  raises for a ``super_admin`` who has not selected a tenant via ``X-Tenant-Id``,
  yet every request still has to resolve its own effective roles — including the
  ones that never touch a tenant-scoped resource.
* The membership rows are already tenant-validated at write time by
  :class:`repositories.user_group.SqlUserGroupRepository`, which refuses to
  place a user in a group belonging to a different tenant. Filtering again here
  would be redundant and, worse, would silently drop grants a user genuinely
  holds if the acting tenant differed.

This makes it the second intentionally tenant-unscoped module alongside
:mod:`repositories.tenant_bootstrap` — see the "Tenant Scoping in the
Repository Layer" section of ``.claude/rules/backend-patterns.md``.
"""

from collections.abc import Collection, Sequence
from typing import Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.user_group import UserGroup, UserGroupMember

#: Maximum ids bound into a single ``IN (...)`` predicate. SQLite caps the
#: number of bound parameters per statement (999 by default on older builds), so
#: a large batch is split across several queries rather than failing outright.
_ID_CHUNK_SIZE = 500


def _chunked(ids: Sequence[str]) -> list[Sequence[str]]:
    """Split ``ids`` into chunks small enough for one ``IN (...)`` predicate.

    Args:
        ids: The identifiers to bind.

    Returns:
        A list of slices of ``ids``, each at most :data:`_ID_CHUNK_SIZE` long.
    """
    return [ids[i : i + _ID_CHUNK_SIZE] for i in range(0, len(ids), _ID_CHUNK_SIZE)]


class EffectiveRoleRepository(Protocol):
    """Interface for resolving group-inherited roles."""

    async def group_roles_for_user(self, user_id: str) -> frozenset[str]: ...

    async def group_roles_for_users(
        self, user_ids: Collection[str]
    ) -> dict[str, frozenset[str]]: ...

    async def effective_roles_for_user(
        self, user_id: str, direct_roles: Collection[str]
    ) -> frozenset[str]: ...

    async def group_ids_for_users(
        self, user_ids: Collection[str]
    ) -> dict[str, list[str]]: ...


class SqlEffectiveRoleRepository:
    """SQLModel-backed implementation of EffectiveRoleRepository.

    Intentionally takes no ``tenant_id``: see the module docstring for why the
    lookups here must span every tenant.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def group_roles_for_user(self, user_id: str) -> frozenset[str]:
        """Return the roles ``user_id`` inherits from their group memberships.

        Args:
            user_id: Identifier of the user to resolve.

        Returns:
            The union of the roles of every group the user belongs to, empty
            when they belong to none.
        """
        return (await self.group_roles_for_users([user_id])).get(user_id, frozenset())

    async def group_roles_for_users(
        self, user_ids: Collection[str]
    ) -> dict[str, frozenset[str]]:
        """Return the group-inherited roles of many users in one pass.

        Batched so a list endpoint resolves a whole page with a single query
        rather than one per row.

        Args:
            user_ids: Identifiers of the users to resolve. Duplicates are
                tolerated.

        Returns:
            A mapping of user id to inherited roles. Every requested id is
            present; users in no group map to an empty set.
        """
        unique_ids = list(dict.fromkeys(user_ids))
        out: dict[str, set[str]] = {uid: set() for uid in unique_ids}
        if not unique_ids:
            return {}
        for chunk in _chunked(unique_ids):
            stmt = (
                select(UserGroupMember.user_id, UserGroup.roles)
                .join(UserGroup, onclause=col(UserGroup.id) == UserGroupMember.group_id)
                .where(col(UserGroupMember.user_id).in_(chunk))
            )
            result = await self._db.exec(stmt)
            for member_user_id, roles in result.all():
                out[member_user_id].update(roles or [])
        return {uid: frozenset(roles) for uid, roles in out.items()}

    async def group_ids_for_users(
        self, user_ids: Collection[str]
    ) -> dict[str, list[str]]:
        """Return the ids of the groups each user belongs to, in one pass.

        The membership half of :meth:`group_roles_for_users`, batched the same
        way so a list endpoint resolves a whole page with one query per chunk.
        It backs :attr:`models.user.UserRead.group_ids`, which lets the client
        answer "may I act on this group-addressed approval?" from the session
        user it already holds, rather than issuing a request per approval it
        renders.

        Args:
            user_ids: Identifiers of the users to resolve. Duplicates are
                tolerated.

        Returns:
            A mapping of user id to group ids, sorted for a stable response.
            Every requested id is present; users in no group map to an empty
            list.
        """
        unique_ids = list(dict.fromkeys(user_ids))
        if not unique_ids:
            return {}
        out: dict[str, set[str]] = {uid: set() for uid in unique_ids}
        for chunk in _chunked(unique_ids):
            stmt = select(UserGroupMember.user_id, UserGroupMember.group_id).where(
                col(UserGroupMember.user_id).in_(chunk)
            )
            for member_user_id, group_id in (await self._db.exec(stmt)).all():
                out[member_user_id].add(group_id)
        return {uid: sorted(ids) for uid, ids in out.items()}

    async def effective_roles_for_user(
        self, user_id: str, direct_roles: Collection[str]
    ) -> frozenset[str]:
        """Return the union of a user's direct grants and their inherited roles.

        Args:
            user_id: Identifier of the user to resolve.
            direct_roles: The user's own ``roles`` column.

        Returns:
            The effective roles to authorize the user against.
        """
        return frozenset(direct_roles) | await self.group_roles_for_user(user_id)
