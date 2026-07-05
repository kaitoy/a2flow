"""CRUD endpoints for User resources.

All responses use :class:`UserRead`, which omits the password hash, so the
stored credential is never serialized to clients.
"""

from typing import Annotated

from fastapi import APIRouter, File, Response, UploadFile

from dependencies import (
    ApiMetaDep,
    CurrentUserIdDep,
    FilterDep,
    PaginationDep,
    SortDep,
    UserAvatarServiceDep,
    UserServiceDep,
)
from models.response import ApiResponse
from models.user import UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=ApiResponse[UserRead], status_code=201)
async def create_user(
    body: UserCreate,
    service: UserServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[UserRead]:
    """Create a new user and return it without the password hash."""
    user = await service.create(body, user_id=user_id)
    return ApiResponse(meta=meta, data=UserRead.model_validate(user))


@router.get("", response_model=ApiResponse[list[UserRead]])
async def list_users(
    service: UserServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[UserRead]]:
    """Return a page of users without their password hashes."""
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
    )
    return ApiResponse(meta=meta, data=[UserRead.model_validate(u) for u in items])


@router.get("/{user_id}", response_model=ApiResponse[UserRead])
async def get_user(
    user_id: str,
    service: UserServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[UserRead]:
    """Return a single user without the password hash."""
    user = await service.get(user_id)
    return ApiResponse(meta=meta, data=UserRead.model_validate(user))


@router.patch("/{user_id}", response_model=ApiResponse[UserRead])
async def update_user(
    user_id: str,
    body: UserUpdate,
    service: UserServiceDep,
    current_user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[UserRead]:
    """Apply a partial update to a user and return it without the password hash."""
    user = await service.update(user_id, body, user_id=current_user_id)
    return ApiResponse(meta=meta, data=UserRead.model_validate(user))


@router.delete("/{user_id}", response_model=ApiResponse[None])
async def delete_user(
    user_id: str,
    service: UserServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    """Delete a user by ID."""
    await service.delete(user_id)
    return ApiResponse(meta=meta, data=None)


@router.put("/{user_id}/avatar", response_model=ApiResponse[UserRead])
async def upload_user_avatar(
    user_id: str,
    file: Annotated[UploadFile, File(description="Avatar image file")],
    avatar_service: UserAvatarServiceDep,
    service: UserServiceDep,
    current_user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[UserRead]:
    """Store or replace a user's custom avatar and return the updated user.

    The image is validated (allowed type and size) by the service. The returned
    user's ``avatarUpdatedAt`` reflects the new image so the client can refresh
    its cached avatar.
    """
    data = await file.read()
    await avatar_service.set(
        user_id,
        data=data,
        content_type=file.content_type or "",
        acting_user_id=current_user_id,
    )
    user = await service.get(user_id)
    return ApiResponse(meta=meta, data=UserRead.model_validate(user))


@router.get("/{user_id}/avatar")
async def get_user_avatar(
    user_id: str,
    avatar_service: UserAvatarServiceDep,
) -> Response:
    """Return the user's custom avatar image bytes, or 404 if none is stored.

    Returns a raw image response (not the JSON envelope) so it can be used
    directly as an ``<img>`` source.
    """
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
    meta: ApiMetaDep,
) -> ApiResponse[UserRead]:
    """Remove a user's custom avatar and return the updated user.

    After removal the returned user's ``avatarUpdatedAt`` is ``None`` so the
    client falls back to the generated default avatar.
    """
    await avatar_service.remove(user_id)
    user = await service.get(user_id)
    return ApiResponse(meta=meta, data=UserRead.model_validate(user))
