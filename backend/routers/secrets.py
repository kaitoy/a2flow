"""CRUD endpoints for Secret resources.

Secret values are write-only: create and update accept plaintext ``entries``
(encrypted by the service before persistence), but every response uses
:class:`SecretRead`, which replaces them with a bare ``keys`` list — neither the
plaintext nor the stored ciphertext is ever serialized to clients.

``GET /{secret_id}/keys`` exists alongside that field because ``SecretRead.keys``
can only report a ``local`` secret's entries; a ``vault`` secret's keys live at
its KV v2 path and need a live read, which would be far too expensive to do for
every row of a list response. Pickers that must offer both kinds use this route.

Writes are open to ``admin`` **or** ``developer``: secrets are one of the four
resources a tag can label (see ``routers/tags.py``), and a developer wiring an
MCP server's ``${secret:...}`` reference or an agent skill's auth password needs
to be able to register the credential in the first place, not just point at one
an admin happened to create first.
"""

from fastapi import APIRouter, Depends

from dependencies import (
    ApiMetaDep,
    CurrentUserIdDep,
    FilterDep,
    PaginationDep,
    SecretServiceDep,
    SortDep,
    TagFilterDep,
    require_roles,
)
from models.response import ApiResponse
from models.secret import SecretCreate, SecretRead, SecretUpdate
from models.tag import TagIdsUpdate
from models.user import Role

router = APIRouter(prefix="/secrets", tags=["secrets"])

#: Route dependency gating secret writes behind the ``admin`` or ``developer`` role.
_requires_write = [Depends(require_roles(Role.admin, Role.developer))]


@router.post(
    "",
    response_model=ApiResponse[SecretRead],
    status_code=201,
    dependencies=_requires_write,
)
async def create_secret(
    body: SecretCreate,
    service: SecretServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[SecretRead]:
    secret = await service.create(body, user_id=user_id)
    return ApiResponse(meta=meta, data=await service.to_read(secret))


@router.get("", response_model=ApiResponse[list[SecretRead]])
async def list_secrets(
    service: SecretServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    tags: TagFilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[SecretRead]]:
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
        tag_ids=tags.tag_ids,
    )
    return ApiResponse(meta=meta, data=await service.to_read_many(items))


@router.get("/{secret_id}", response_model=ApiResponse[SecretRead])
async def get_secret(
    secret_id: str,
    service: SecretServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[SecretRead]:
    secret = await service.get(secret_id)
    return ApiResponse(meta=meta, data=await service.to_read(secret))


@router.get("/{secret_id}/keys", response_model=ApiResponse[list[str]])
async def list_secret_keys(
    secret_id: str,
    service: SecretServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[str]]:
    keys = await service.list_keys(secret_id)
    return ApiResponse(meta=meta, data=keys)


@router.patch(
    "/{secret_id}",
    response_model=ApiResponse[SecretRead],
    dependencies=_requires_write,
)
async def update_secret(
    secret_id: str,
    body: SecretUpdate,
    service: SecretServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[SecretRead]:
    secret = await service.update(secret_id, body, user_id=user_id)
    return ApiResponse(meta=meta, data=await service.to_read(secret))


@router.put(
    "/{secret_id}/tags",
    response_model=ApiResponse[SecretRead],
    dependencies=_requires_write,
)
async def set_secret_tags(
    secret_id: str,
    body: TagIdsUpdate,
    service: SecretServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[SecretRead]:
    secret = await service.set_tags(secret_id, body.tag_ids)
    return ApiResponse(meta=meta, data=await service.to_read(secret))


@router.delete(
    "/{secret_id}",
    response_model=ApiResponse[None],
    dependencies=_requires_write,
)
async def delete_secret(
    secret_id: str,
    service: SecretServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    await service.delete(secret_id)
    return ApiResponse(meta=meta, data=None)
