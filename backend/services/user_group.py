"""Use case service for UserGroup resources.

Wraps the :class:`UserGroupRepository` with the business rule the routers need:
raising :class:`NotFoundError` when a group is missing. Authorization is split
the usual way — the ``admin`` role gate lives in the router, while the tenant
boundary is already enforced by the repository, which is constructed for one
tenant and treats a cross-tenant id as absent.

There is deliberately no "recompute inherited roles" step anywhere here.
Effective roles are resolved on read by
:class:`repositories.effective_roles.SqlEffectiveRoleRepository`, so a
membership change takes effect on the very next request with nothing to
invalidate.
"""

from collections.abc import Sequence

from models.user_group import UserGroupCreate, UserGroupRead, UserGroupUpdate
from repositories import UserGroupRepository
from repositories.exceptions import NotFoundError
from repositories.query import FilterSpec, SortSpec

_GroupList = list[UserGroupRead]
_StrList = list[str]


class UserGroupService:
    """Application service orchestrating UserGroup operations."""

    def __init__(self, repo: UserGroupRepository) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing UserGroup persistence, already scoped to
                the acting tenant.
        """
        self._repo = repo

    async def get(self, group_id: str) -> UserGroupRead:
        """Return the UserGroup with the given ID.

        Args:
            group_id: Identifier of the group to fetch.

        Returns:
            The matching group with its membership attached.

        Raises:
            NotFoundError: If no group exists with the given ID in the acting
                tenant.
        """
        group = await self._repo.get(group_id)
        if group is None:
            raise NotFoundError("UserGroup", group_id)
        return group

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> _GroupList:
        """Return a page of UserGroup records in the acting tenant.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.

        Returns:
            The requested page of groups, each with its membership attached.
        """
        return await self._repo.list(
            limit=limit, offset=offset, sort=sort, filters=filters
        )

    async def create(self, data: UserGroupCreate, *, user_id: str) -> UserGroupRead:
        """Create a new UserGroup.

        Args:
            data: Fields for the new group, including its initial members.
            user_id: Identifier of the acting user, recorded as the creator.

        Returns:
            The created group.

        Raises:
            ForeignKeyViolationError: If a member id is not a usable user of
                the acting tenant.
        """
        return await self._repo.create(data, user_id=user_id)

    async def update(
        self, group_id: str, data: UserGroupUpdate, *, user_id: str
    ) -> UserGroupRead:
        """Apply a partial update to a UserGroup.

        Args:
            group_id: Identifier of the group to update.
            data: Fields to update; ``member_ids`` replaces membership
                wholesale when supplied.
            user_id: Identifier of the acting user, recorded as the updater.

        Returns:
            The updated group.

        Raises:
            NotFoundError: If no group exists with the given ID in the acting
                tenant.
            ForeignKeyViolationError: If a member id is not a usable user of
                the acting tenant.
        """
        return await self._repo.update(group_id, data, user_id=user_id)

    async def delete(self, group_id: str) -> None:
        """Delete a UserGroup, dropping its membership rows with it.

        Args:
            group_id: Identifier of the group to delete.

        Raises:
            NotFoundError: If no group exists with the given ID in the acting
                tenant.
        """
        await self._repo.delete(group_id)

    async def group_ids_for_user(self, user_id: str) -> _StrList:
        """Return the ids of the acting tenant's groups a user belongs to.

        Args:
            user_id: Identifier of the user whose memberships to list.

        Returns:
            The sorted group ids.
        """
        return await self._repo.group_ids_for_user(user_id)

    async def groups_for_user(self, user_id: str) -> _GroupList:
        """Return the acting tenant's groups a user belongs to.

        Args:
            user_id: Identifier of the user whose memberships to list.

        Returns:
            The groups, ordered by name, each with its membership attached.
        """
        return await self._repo.list_for_user(user_id)

    async def set_groups_for_user(self, user_id: str, group_ids: Sequence[str]) -> None:
        """Replace the set of groups a user belongs to.

        Args:
            user_id: Identifier of the user whose membership to set.
            group_ids: Ids of the groups the user should end up in.

        Raises:
            ForeignKeyViolationError: If the user is not a usable member of the
                acting tenant, or a group id is not a group of that tenant.
        """
        await self._repo.set_groups_for_user(user_id, group_ids)
