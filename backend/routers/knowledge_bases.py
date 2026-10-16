"""Endpoints for knowledge bases: CRUD, their sources, their pages, and export.

Writes are gated behind ``developer``, matching agent skills and MCP servers:
what a workflow's agents know is part of how the workflow is built. Reads are
open to every authenticated user, subject to access-control tags.

Registering, re-ingesting, and deleting a source answer at once and leave the
work to a background job (``KnowledgeJobDep``); the source's ``status`` is
what the admin UI polls. ``DELETE .../sources/{id}`` therefore returns the
source marked ``removing`` rather than ``null``: it disappears once the job
has taken its knowledge out of the pages.
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Response, UploadFile

from dependencies.auth import CurrentUserIdDep
from dependencies.authz import require_roles
from dependencies.context import (
    ApiMetaDep,
    FilterDep,
    PaginationDep,
    SortDep,
    TagFilterDep,
)
from dependencies.service import KnowledgeBaseServiceDep, KnowledgeJobDep
from models.knowledge import (
    KnowledgeBaseCreate,
    KnowledgeBaseRead,
    KnowledgeBaseUpdate,
    KnowledgePageContent,
    KnowledgePageSummary,
    KnowledgeSourceRead,
    KnowledgeUrlSourceCreate,
)
from models.response import ApiResponse
from models.tag import TagIdsUpdate
from models.user import Role
from routers._download import content_disposition
from services.knowledge_ingest import KnowledgeJobAction

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])

#: Route dependency gating knowledge base writes behind the ``developer`` role.
_requires_developer = [Depends(require_roles(Role.developer))]


@router.post(
    "",
    response_model=ApiResponse[KnowledgeBaseRead],
    status_code=201,
    dependencies=_requires_developer,
)
async def create_knowledge_base(
    body: KnowledgeBaseCreate,
    service: KnowledgeBaseServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[KnowledgeBaseRead]:
    kb = await service.create(body, user_id=user_id)
    return ApiResponse(meta=meta, data=await service.to_read(kb))


@router.get("", response_model=ApiResponse[list[KnowledgeBaseRead]])
async def list_knowledge_bases(
    service: KnowledgeBaseServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    tags: TagFilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[KnowledgeBaseRead]]:
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
        tag_ids=tags.tag_ids,
    )
    return ApiResponse(meta=meta, data=await service.to_read_many(items))


@router.get("/{kb_id}", response_model=ApiResponse[KnowledgeBaseRead])
async def get_knowledge_base(
    kb_id: str, service: KnowledgeBaseServiceDep, meta: ApiMetaDep
) -> ApiResponse[KnowledgeBaseRead]:
    kb = await service.get(kb_id)
    return ApiResponse(meta=meta, data=await service.to_read(kb))


@router.patch(
    "/{kb_id}",
    response_model=ApiResponse[KnowledgeBaseRead],
    dependencies=_requires_developer,
)
async def update_knowledge_base(
    kb_id: str,
    body: KnowledgeBaseUpdate,
    service: KnowledgeBaseServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[KnowledgeBaseRead]:
    kb = await service.update(kb_id, body, user_id=user_id)
    return ApiResponse(meta=meta, data=await service.to_read(kb))


@router.delete(
    "/{kb_id}", response_model=ApiResponse[None], dependencies=_requires_developer
)
async def delete_knowledge_base(
    kb_id: str, service: KnowledgeBaseServiceDep, meta: ApiMetaDep
) -> ApiResponse[None]:
    await service.delete(kb_id)
    return ApiResponse(meta=meta, data=None)


@router.put(
    "/{kb_id}/tags",
    response_model=ApiResponse[KnowledgeBaseRead],
    dependencies=_requires_developer,
)
async def set_knowledge_base_tags(
    kb_id: str,
    body: TagIdsUpdate,
    service: KnowledgeBaseServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[KnowledgeBaseRead]:
    kb = await service.set_tags(kb_id, body.tag_ids)
    return ApiResponse(meta=meta, data=await service.to_read(kb))


@router.get("/{kb_id}/sources", response_model=ApiResponse[list[KnowledgeSourceRead]])
async def list_knowledge_sources(
    kb_id: str, service: KnowledgeBaseServiceDep, meta: ApiMetaDep
) -> ApiResponse[list[KnowledgeSourceRead]]:
    return ApiResponse(meta=meta, data=await service.list_sources(kb_id))


@router.post(
    "/{kb_id}/sources/url",
    response_model=ApiResponse[KnowledgeSourceRead],
    status_code=201,
    dependencies=_requires_developer,
)
async def add_knowledge_url_source(
    kb_id: str,
    body: KnowledgeUrlSourceCreate,
    service: KnowledgeBaseServiceDep,
    background: BackgroundTasks,
    job: KnowledgeJobDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[KnowledgeSourceRead]:
    """Register a web page as a source and start reading it into the wiki."""
    source = await service.add_url_source(kb_id, body.url, user_id=user_id)
    background.add_task(
        job, source.id, action=KnowledgeJobAction.ingest, user_id=user_id
    )
    return ApiResponse(meta=meta, data=source)


@router.post(
    "/{kb_id}/sources/file",
    response_model=ApiResponse[KnowledgeSourceRead],
    status_code=201,
    dependencies=_requires_developer,
)
async def add_knowledge_file_source(
    kb_id: str,
    file: Annotated[UploadFile, File(description="Document to read into the wiki")],
    service: KnowledgeBaseServiceDep,
    background: BackgroundTasks,
    job: KnowledgeJobDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[KnowledgeSourceRead]:
    """Upload a document as a source and start reading it into the wiki."""
    source = await service.add_file_source(
        kb_id,
        filename=file.filename,
        content_type=file.content_type,
        read=file.read,
        user_id=user_id,
    )
    background.add_task(
        job, source.id, action=KnowledgeJobAction.ingest, user_id=user_id
    )
    return ApiResponse(meta=meta, data=source)


@router.post(
    "/{kb_id}/sources/{source_id}/reingest",
    response_model=ApiResponse[KnowledgeSourceRead],
    dependencies=_requires_developer,
)
async def reingest_knowledge_source(
    kb_id: str,
    source_id: str,
    service: KnowledgeBaseServiceDep,
    background: BackgroundTasks,
    job: KnowledgeJobDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[KnowledgeSourceRead]:
    """Read a source again -- a URL's current page, or a failed upload once more."""
    source = await service.request_reingest(kb_id, source_id, user_id=user_id)
    background.add_task(
        job, source.id, action=KnowledgeJobAction.reingest, user_id=user_id
    )
    return ApiResponse(meta=meta, data=source)


@router.delete(
    "/{kb_id}/sources/{source_id}",
    response_model=ApiResponse[KnowledgeSourceRead],
    dependencies=_requires_developer,
)
async def delete_knowledge_source(
    kb_id: str,
    source_id: str,
    service: KnowledgeBaseServiceDep,
    background: BackgroundTasks,
    job: KnowledgeJobDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[KnowledgeSourceRead]:
    """Take a source's knowledge out of the wiki, then delete the source."""
    source = await service.request_removal(kb_id, source_id, user_id=user_id)
    background.add_task(
        job, source.id, action=KnowledgeJobAction.remove, user_id=user_id
    )
    return ApiResponse(meta=meta, data=source)


@router.get("/{kb_id}/pages", response_model=ApiResponse[list[KnowledgePageSummary]])
async def list_knowledge_pages(
    kb_id: str, service: KnowledgeBaseServiceDep, meta: ApiMetaDep
) -> ApiResponse[list[KnowledgePageSummary]]:
    return ApiResponse(meta=meta, data=await service.list_pages(kb_id))


@router.get(
    "/{kb_id}/pages/{path:path}", response_model=ApiResponse[KnowledgePageContent]
)
async def get_knowledge_page(
    kb_id: str, path: str, service: KnowledgeBaseServiceDep, meta: ApiMetaDep
) -> ApiResponse[KnowledgePageContent]:
    """Return one page as its OKF document; ``path`` is the page path without its leading ``/``."""
    return ApiResponse(meta=meta, data=await service.get_page(kb_id, path))


@router.get("/{kb_id}/export")
async def export_knowledge_base(
    kb_id: str, service: KnowledgeBaseServiceDep
) -> Response:
    """Download the knowledge base as a zipped OKF bundle.

    Outside the ``ApiResponse`` envelope, like every file download.
    """
    kb, bundle = await service.export(kb_id)
    return Response(
        content=bundle,
        media_type="application/zip",
        headers={
            "Content-Disposition": content_disposition(f"{kb.name}.zip"),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
