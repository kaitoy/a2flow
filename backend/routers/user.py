"""CRUD endpoints for User resources.

All responses use :class:`UserRead`, which omits the password hash, so the
stored credential is never serialized to clients.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Response, UploadFile

from dependencies import (
    ApiMetaDep,
    CurrentTenantIdDep,
    CurrentUserDep,
    EffectiveRolesDep,
    FilterDep,
    PaginationDep,
    SortDep,
    UserAvatarServiceDep,
    UserGroupServiceDep,
    UserServiceDep,
    require_roles,
)
from models.response import ApiResponse
from models.user import (
    ResolvedUserName,
    Role,
    User,
    UserCreate,
    UserNameResolveRequest,
    UserRead,
    UserUpdate,
)
from models.user_group import UserGroupMembershipUpdate, UserGroupRead
from services import UserService

router = APIRouter(prefix="/users", tags=["users"])

#: Route dependency gating user creation and deletion behind the ``admin`` role.
#: ``PATCH`` is not listed here — it allows a limited self-service path and is
#: authorized in :class:`~services.user.UserService` instead.
_requires_admin = [Depends(require_roles(Role.admin))]


async def _to_read(service: UserService, user: User) -> UserRead:
    """Project one user into its read view, resolving its inherited roles.

    Args:
        service: The user service, used to resolve group-inherited roles.
        user: The user to project.

    Returns:
        The read view, carrying both direct and group-inherited roles.
    """
    group_roles = await service.group_roles_for([user])
    return UserRead.from_user(user, group_roles=group_roles[user.id])


async def _to_read_many(service: UserService, users: list[User]) -> list[UserRead]:
    """Project a page of users into read views with one membership query.

    Args:
        service: The user service, used to resolve group-inherited roles.
        users: The users to project.

    Returns:
        The read views, in the order given.
    """
    group_roles = await service.group_roles_for(users)
    return [UserRead.from_user(u, group_roles=group_roles[u.id]) for u in users]


@router.post(
    "",
    response_model=ApiResponse[UserRead],
    status_code=201,
    dependencies=_requires_admin,
)
async def create_user(
    body: UserCreate,
    service: UserServiceDep,
    acting_user: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[UserRead]:
    """Create a new user and return it without the password hash.

    Requires the ``admin`` role; creating a ``super_admin`` or assigning a
    ``tenantId`` additionally requires the acting user to be a super admin.
    """
    user = await service.create(body, acting_user=acting_user)
    return ApiResponse(meta=meta, data=await _to_read(service, user))


@router.get("", response_model=ApiResponse[list[UserRead]])
async def list_users(
    service: UserServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    acting_user: CurrentUserDep,
    acting_tenant_id: CurrentTenantIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[UserRead]]:
    """Return a page of users without their password hashes.

    A non-super-admin caller only ever sees users in their own tenant. A
    super admin sees users in the tenant they're currently acting as (see
    :data:`CurrentTenantIdDep`, resolved from the app bar's tenant switcher),
    plus every super_admin user platform-wide regardless of tenant.
    """
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
        acting_user=acting_user,
        acting_tenant_id=acting_tenant_id,
    )
    return ApiResponse(meta=meta, data=await _to_read_many(service, items))


@router.post("/resolve-names", response_model=ApiResponse[list[ResolvedUserName]])
async def resolve_user_names(
    body: UserNameResolveRequest,
    service: UserServiceDep,
    acting_user: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[ResolvedUserName]]:
    """Resolve a batch of user ids to the display names the caller may see.

    Lets a client render many user references (audit footers, initiator and
    approver columns) with one request instead of one ``GET /users/{id}`` per
    id. Applies the same tenant boundary as that endpoint: a user outside the
    caller's tenant is not named, except that the seeded system user and any
    ``super_admin`` come back under a fixed placeholder. Ids that resolve to
    nothing the caller may see are omitted rather than erroring, so the client
    falls back to displaying the raw id for those.

    ``POST`` rather than ``GET`` because the id list runs to
    ``MAX_RESOLVE_NAME_IDS`` entries, which does not fit a URL; the request is
    a read and requires no role beyond a valid session.
    """
    names = await service.resolve_names(body.ids, acting_user=acting_user)
    return ApiResponse(meta=meta, data=names)


@router.get("/{user_id}", response_model=ApiResponse[UserRead])
async def get_user(
    user_id: str,
    service: UserServiceDep,
    acting_user: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[UserRead]:
    """Return a single user without the password hash.

    Raises a 404 (not a 403) if the user exists but belongs to a different
    tenant than the caller, unless the caller is a super admin.
    """
    user = await service.get(user_id, acting_user=acting_user)
    return ApiResponse(meta=meta, data=await _to_read(service, user))


@router.patch("/{user_id}", response_model=ApiResponse[UserRead])
async def update_user(
    user_id: str,
    body: UserUpdate,
    service: UserServiceDep,
    acting_user: CurrentUserDep,
    acting_roles: EffectiveRolesDep,
    meta: ApiMetaDep,
) -> ApiResponse[UserRead]:
    """Apply a partial update to a user and return it without the password hash.

    Admins may update any user; other callers may update only their own
    avatar customization (the self-service ``/profile`` page). The
    authorization rules live in :meth:`UserService.update`. ``admin`` counts
    whether it is granted directly or inherited from a user group.
    """
    user = await service.update(
        user_id, body, acting_user=acting_user, acting_roles=acting_roles
    )
    return ApiResponse(meta=meta, data=await _to_read(service, user))


@router.delete(
    "/{user_id}",
    response_model=ApiResponse[None],
    dependencies=_requires_admin,
)
async def delete_user(
    user_id: str,
    service: UserServiceDep,
    acting_user: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    """Delete a user by ID.

    Raises a 404 (not a 403) if the user exists but belongs to a different
    tenant than the caller, unless the caller is a super admin.
    """
    await service.delete(user_id, acting_user=acting_user)
    return ApiResponse(meta=meta, data=None)


@router.get("/{user_id}/groups", response_model=ApiResponse[list[UserGroupRead]])
async def list_groups_for_user(
    user_id: str,
    service: UserServiceDep,
    group_service: UserGroupServiceDep,
    acting_user: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[UserGroupRead]]:
    """Return the acting tenant's groups the given user belongs to.

    The read counterpart of ``PUT /users/{user_id}/groups``. Reads are open to
    any authenticated caller, as everywhere else, but the user is resolved
    through :class:`~services.user.UserService` first, so a target in another
    tenant reads as 404 rather than confirming that it exists.
    """
    user = await service.get(user_id, acting_user=acting_user)
    groups = await group_service.groups_for_user(user.id)
    return ApiResponse(meta=meta, data=groups)


@router.put(
    "/{user_id}/groups",
    response_model=ApiResponse[UserRead],
    dependencies=_requires_admin,
)
async def set_user_groups(
    user_id: str,
    body: UserGroupMembershipUpdate,
    service: UserServiceDep,
    group_service: UserGroupServiceDep,
    acting_user: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[UserRead]:
    """Replace the set of user groups a user belongs to.

    The counterpart of editing a group's ``memberIds`` from the group side, so
    membership can be managed from whichever page the admin is already on.
    ``PUT`` rather than ``PATCH`` because the supplied list replaces the user's
    membership wholesale.

    The target is fetched through :meth:`UserService.get` first, so a user in
    another tenant raises a 404 rather than a 403 and never confirms their
    existence. The returned user's ``groupRoles`` reflects the new membership
    immediately — nothing is cached, so the change is live on the next request.

    Requires the ``admin`` role. Raises HTTP 422 if a group id is not a group
    of the acting tenant, or if the target cannot be a member of one (a
    platform-scoped user such as a super admin).
    """
    user = await service.get(user_id, acting_user=acting_user)
    await group_service.set_groups_for_user(user.id, body.group_ids)
    # Re-read after the membership commit: it expires the instance fetched
    # above, and serializing an expired one outside the request's greenlet
    # context would fail.
    refreshed = await service.get(user_id, acting_user=acting_user)
    return ApiResponse(meta=meta, data=await _to_read(service, refreshed))


@router.put("/{user_id}/avatar", response_model=ApiResponse[UserRead])
async def upload_user_avatar(
    user_id: str,
    file: Annotated[UploadFile, File(description="Avatar image file")],
    avatar_service: UserAvatarServiceDep,
    service: UserServiceDep,
    acting_user: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[UserRead]:
    """Store or replace a user's custom avatar and return the updated user.

    Self-service only: the target must be the acting user themself (or the
    acting user must be a super admin). The image is validated (allowed type
    and size) by the service. The returned user's ``avatarUpdatedAt`` reflects
    the new image so the client can refresh its cached avatar.
    """
    data = await file.read()
    await avatar_service.set(
        user_id,
        data=data,
        content_type=file.content_type or "",
        acting_user=acting_user,
    )
    user = await service.get(user_id, acting_user=acting_user)
    return ApiResponse(meta=meta, data=await _to_read(service, user))


@router.get("/{user_id}/avatar")
async def get_user_avatar(
    user_id: str,
    avatar_service: UserAvatarServiceDep,
    service: UserServiceDep,
    acting_user: CurrentUserDep,
) -> Response:
    """Return the user's custom avatar image bytes, or 404 if none is stored.

    Returns a raw image response (not the JSON envelope) so it can be used
    directly as an ``<img>`` source. Raises a 404 if the owning user exists
    but belongs to a different tenant than the caller, unless the caller is a
    super admin.
    """
    await service.get(user_id, acting_user=acting_user)
    avatar = await avatar_service.get(user_id)
    return Response(
        content=avatar.data,
        media_type=avatar.content_type,
        headers={
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/{user_id}/avatar", response_model=ApiResponse[UserRead])
async def delete_user_avatar(
    user_id: str,
    avatar_service: UserAvatarServiceDep,
    service: UserServiceDep,
    acting_user: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[UserRead]:
    """Remove a user's custom avatar and return the updated user.

    Self-service only: the target must be the acting user themself (or the
    acting user must be a super admin). After removal the returned user's
    ``avatarUpdatedAt`` is ``None`` so the client falls back to the generated
    default avatar.
    """
    await avatar_service.remove(user_id, acting_user=acting_user)
    user = await service.get(user_id, acting_user=acting_user)
    return ApiResponse(meta=meta, data=await _to_read(service, user))
