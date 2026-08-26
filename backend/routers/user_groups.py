"""CRUD endpoints for UserGroup resources.

A user group bundles users within a tenant and grants every member its set of
roles. Members appear on the payload and read models as ``memberIds``; supplying
that field on a write replaces the group's membership wholesale.

Writes require the ``admin`` role, matching ``/users``; reads are open to any
authenticated caller, like every other resource router.

The membership of a *single* user is edited from the other side through
``PUT /users/{user_id}/groups`` (see :mod:`routers.user`), so an admin can
manage it from whichever page they are already on.
"""

from fastapi import APIRouter, Depends

from dependencies import (
    ApiMetaDep,
    CurrentUserIdDep,
    FilterDep,
    PaginationDep,
    SortDep,
    UserGroupReadServiceDep,
    UserGroupServiceDep,
    require_roles,
)
from models.response import ApiResponse
from models.user import Role
from models.user_group import UserGroupCreate, UserGroupRead, UserGroupUpdate

router = APIRouter(prefix="/user-groups", tags=["user-groups"])

#: Route dependency gating user-group writes behind the ``admin`` role.
_requires_admin = [Depends(require_roles(Role.admin))]


@router.post(
    "",
    response_model=ApiResponse[UserGroupRead],
    status_code=201,
    dependencies=_requires_admin,
)
async def create_user_group(
    body: UserGroupCreate,
    service: UserGroupServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[UserGroupRead]:
    """Create a user group in the acting tenant and place its members in it.

    Rejects ``super_admin`` among the roles with HTTP 422 — a group can never
    grant it. Rejects a member who is not a usable user of the acting tenant
    with HTTP 422 ``FOREIGN_KEY_VIOLATION``; a user of another tenant reads as
    a missing reference, so membership never confirms they exist elsewhere.
    """
    group = await service.create(body, user_id=user_id)
    return ApiResponse(meta=meta, data=group)


@router.get("", response_model=ApiResponse[list[UserGroupRead]])
async def list_user_groups(
    service: UserGroupReadServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[UserGroupRead]]:
    """Return a page of the acting tenant's user groups with their members.

    ``memberIds`` is not a column, so it can be read but never filtered or
    sorted on — naming it in ``q`` or ``s`` is rejected as an unknown field.
    """
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
    )
    return ApiResponse(meta=meta, data=items)


@router.get("/{group_id}", response_model=ApiResponse[UserGroupRead])
async def get_user_group(
    group_id: str,
    service: UserGroupReadServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[UserGroupRead]:
    """Return a single user group with its members.

    Raises a 404 (not a 403) for a group belonging to another tenant, so its
    existence is never confirmed to the caller.
    """
    group = await service.get(group_id)
    return ApiResponse(meta=meta, data=group)


@router.patch(
    "/{group_id}",
    response_model=ApiResponse[UserGroupRead],
    dependencies=_requires_admin,
)
async def update_user_group(
    group_id: str,
    body: UserGroupUpdate,
    service: UserGroupServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[UserGroupRead]:
    """Apply a partial update to a user group.

    Omitting ``memberIds`` leaves membership untouched; supplying a list
    replaces it wholesale, and an empty list empties the group. Changing
    ``roles`` takes effect for every member on their next request — nothing is
    cached.
    """
    group = await service.update(group_id, body, user_id=user_id)
    return ApiResponse(meta=meta, data=group)


@router.delete(
    "/{group_id}",
    response_model=ApiResponse[None],
    dependencies=_requires_admin,
)
async def delete_user_group(
    group_id: str,
    service: UserGroupServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    """Delete a user group.

    Its membership rows are removed with it, so former members lose the roles
    the group granted them. The users themselves are untouched.
    """
    await service.delete(group_id)
    return ApiResponse(meta=meta, data=None)
