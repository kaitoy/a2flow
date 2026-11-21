"""Endpoints letting a tenant's ``admin`` load and clear the demo dataset.

Like :mod:`routers.admin_settings`, these act on the caller's tenant
(``CurrentTenantIdDep``: their own, or the one a ``super_admin`` selected with
``X-Tenant-Id``). The work is done by :mod:`infrastructure.demo_data`, which
writes the rows directly rather than through the services, the same way it is
called outside a request at startup; it has no service of its own to go
through.
"""

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from dependencies.auth import CurrentTenantIdDep, CurrentUserIdDep
from dependencies.authz import require_roles
from dependencies.context import ApiMetaDep
from dependencies.repository import DBSessionDep
from dependencies.service import SkillSyncJobDep
from infrastructure.demo_data import clear_demo_data, has_demo_data, load_demo_data
from models.response import ApiResponse
from models.user import Role

router = APIRouter(prefix="/demo-data", tags=["demo-data"])

#: Route dependency gating every route behind ``admin`` (``super_admin`` passes).
_requires_admin = [Depends(require_roles(Role.admin))]


class DemoDataStatus(BaseModel):
    """Whether the caller's tenant holds the demo dataset.

    Attributes:
        loaded: Whether any demo record is present in the tenant.
        kept_count: After a clear, how many demo records were kept because
            other records still reference them; ``0`` otherwise.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    loaded: bool
    kept_count: int = 0


@router.get(
    "", response_model=ApiResponse[DemoDataStatus], dependencies=_requires_admin
)
async def get_demo_data(
    tenant_id: CurrentTenantIdDep,
    db: DBSessionDep,
    meta: ApiMetaDep,
) -> ApiResponse[DemoDataStatus]:
    """Report whether the caller's tenant holds the demo dataset."""
    return ApiResponse(
        meta=meta, data=DemoDataStatus(loaded=await has_demo_data(db, tenant_id))
    )


@router.post(
    "", response_model=ApiResponse[DemoDataStatus], dependencies=_requires_admin
)
async def load_tenant_demo_data(
    tenant_id: CurrentTenantIdDep,
    db: DBSessionDep,
    background: BackgroundTasks,
    sync_job: SkillSyncJobDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[DemoDataStatus]:
    """Load the demo dataset into the caller's tenant, restoring what is missing.

    The demo agent skills this creates are cloned in the background, as for a
    skill registered by hand, so the response does not wait on the network.
    """
    for skill_id in await load_demo_data(db, tenant_id):
        background.add_task(sync_job, skill_id, user_id=user_id)
    return ApiResponse(meta=meta, data=DemoDataStatus(loaded=True))


@router.delete(
    "", response_model=ApiResponse[DemoDataStatus], dependencies=_requires_admin
)
async def clear_tenant_demo_data(
    tenant_id: CurrentTenantIdDep,
    db: DBSessionDep,
    meta: ApiMetaDep,
) -> ApiResponse[DemoDataStatus]:
    """Delete the demo dataset from the caller's tenant.

    Records other data has come to depend on are kept; ``keptCount`` says how
    many, and ``loaded`` stays true while any are left.
    """
    kept = await clear_demo_data(db, tenant_id)
    return ApiResponse(
        meta=meta,
        data=DemoDataStatus(loaded=await has_demo_data(db, tenant_id), kept_count=kept),
    )
