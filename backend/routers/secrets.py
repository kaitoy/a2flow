"""CRUD endpoints for Secret resources.

Secret values are write-only: create and update accept a plaintext ``value``
(encrypted by the service before persistence), but every response uses
:class:`SecretRead`, which has no ``value`` field at all — neither the
plaintext nor the stored ciphertext is ever serialized to clients.
"""

from fastapi import APIRouter

from dependencies import (
    ApiMetaDep,
    CurrentUserIdDep,
    FilterDep,
    PaginationDep,
    SecretServiceDep,
    SortDep,
)
from models.response import ApiResponse
from models.secret import SecretCreate, SecretRead, SecretUpdate

router = APIRouter(prefix="/secrets", tags=["secrets"])


@router.post("", response_model=ApiResponse[SecretRead], status_code=201)
async def create_secret(
    body: SecretCreate,
    service: SecretServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[SecretRead]:
    secret = await service.create(body, user_id=user_id)
    return ApiResponse(meta=meta, data=SecretRead.model_validate(secret))


@router.get("", response_model=ApiResponse[list[SecretRead]])
async def list_secrets(
    service: SecretServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[SecretRead]]:
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
    )
    return ApiResponse(meta=meta, data=[SecretRead.model_validate(s) for s in items])


@router.get("/{secret_id}", response_model=ApiResponse[SecretRead])
async def get_secret(
    secret_id: str,
    service: SecretServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[SecretRead]:
    secret = await service.get(secret_id)
    return ApiResponse(meta=meta, data=SecretRead.model_validate(secret))


@router.patch("/{secret_id}", response_model=ApiResponse[SecretRead])
async def update_secret(
    secret_id: str,
    body: SecretUpdate,
    service: SecretServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[SecretRead]:
    secret = await service.update(secret_id, body, user_id=user_id)
    return ApiResponse(meta=meta, data=SecretRead.model_validate(secret))


@router.delete("/{secret_id}", response_model=ApiResponse[None])
async def delete_secret(
    secret_id: str,
    service: SecretServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    await service.delete(secret_id)
    return ApiResponse(meta=meta, data=None)
