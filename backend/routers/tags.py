"""CRUD endpoints for Tag resources.

Tags are the label vocabulary shared by secrets, workflows, MCP servers, and
agent skills. Writes are open to ``admin`` **or** ``developer``: secrets are
administered by the former and the other three by the latter, so gating on
either one alone would leave half the taggable resources with no way to mint a
label for themselves.

Attaching a tag to a record is not here — that is a sub-resource of the record
itself (``PUT /{resource}/{id}/tags``), gated by that resource's own write role.

Deleting a tag detaches it from every record that carried it (the join tables
cascade) rather than being blocked by them, so retiring a label never requires
hunting down its users first.
"""

from fastapi import APIRouter, Depends

from dependencies import (
    ApiMetaDep,
    CurrentUserIdDep,
    FilterDep,
    PaginationDep,
    SortDep,
    TagServiceDep,
    require_roles,
)
from models.response import ApiResponse
from models.tag import Tag, TagCreate, TagUpdate
from models.user import Role

router = APIRouter(prefix="/tags", tags=["tags"])

#: Route dependency gating tag writes behind the ``admin`` or ``developer`` role.
_requires_write = [Depends(require_roles(Role.admin, Role.developer))]


@router.post(
    "",
    response_model=ApiResponse[Tag],
    status_code=201,
    dependencies=_requires_write,
)
async def create_tag(
    body: TagCreate,
    service: TagServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[Tag]:
    tag = await service.create(body, user_id=user_id)
    return ApiResponse(meta=meta, data=tag)


@router.get("", response_model=ApiResponse[list[Tag]])
async def list_tags(
    service: TagServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[Tag]]:
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
    )
    return ApiResponse(meta=meta, data=items)


@router.get("/{tag_id}", response_model=ApiResponse[Tag])
async def get_tag(
    tag_id: str,
    service: TagServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[Tag]:
    tag = await service.get(tag_id)
    return ApiResponse(meta=meta, data=tag)


@router.patch(
    "/{tag_id}",
    response_model=ApiResponse[Tag],
    dependencies=_requires_write,
)
async def update_tag(
    tag_id: str,
    body: TagUpdate,
    service: TagServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[Tag]:
    tag = await service.update(tag_id, body, user_id=user_id)
    return ApiResponse(meta=meta, data=tag)


@router.delete(
    "/{tag_id}",
    response_model=ApiResponse[None],
    dependencies=_requires_write,
)
async def delete_tag(
    tag_id: str,
    service: TagServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    await service.delete(tag_id)
    return ApiResponse(meta=meta, data=None)
