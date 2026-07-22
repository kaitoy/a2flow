"""CRUD endpoints for User resources.

All responses use :class:`UserRead`, which omits the password hash, so the
stored credential is never serialized to clients.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Response, UploadFile

from dependencies import (
    ApiMetaDep,
    CurrentUserDep,
    FilterDep,
    PaginationDep,
    SortDep,
    UserAvatarServiceDep,
    UserServiceDep,
    require_roles,
)
from models.response import ApiResponse
from models.user import Role, UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])

#: Route dependency gating user creation and deletion behind the ``admin`` role.
#: ``PATCH`` is not listed here — it allows a limited self-service path and is
#: authorized in :class:`~services.user.UserService` instead.
_requires_admin = [Depends(require_roles(Role.admin))]


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
    return ApiResponse(meta=meta, data=UserRead.model_validate(user))


@router.get("", response_model=ApiResponse[list[UserRead]])
async def list_users(
    service: UserServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    acting_user: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[UserRead]]:
    """Return a page of users without their password hashes.

    A non-super-admin caller only ever sees users in their own tenant; a
    super admin sees every user.
    """
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
        acting_user=acting_user,
    )
    return ApiResponse(meta=meta, data=[UserRead.model_validate(u) for u in items])


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
    return ApiResponse(meta=meta, data=UserRead.model_validate(user))


@router.patch("/{user_id}", response_model=ApiResponse[UserRead])
async def update_user(
    user_id: str,
    body: UserUpdate,
    service: UserServiceDep,
    acting_user: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[UserRead]:
    """Apply a partial update to a user and return it without the password hash.

    Admins may update any user; other callers may update only their own
    avatar customization (the self-service ``/account`` page). The
    authorization rules live in :meth:`UserService.update`.
    """
    user = await service.update(user_id, body, acting_user=acting_user)
    return ApiResponse(meta=meta, data=UserRead.model_validate(user))


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
    return ApiResponse(meta=meta, data=UserRead.model_validate(user))


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
    return ApiResponse(meta=meta, data=UserRead.model_validate(user))
