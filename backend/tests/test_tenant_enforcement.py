"""Tests for tenant resolution (``get_current_tenant_id``) and its end-to-end effect.

``get_current_tenant_id`` is a plain function once FastAPI's ``Depends()``
wiring is stripped away, so its platform-scoped-caller behavior is tested
directly. The actual enforcement -- cross-tenant access reading as 404 rather
than 403, and a platform-scoped caller being rejected outright -- is tested
end-to-end through the API, since that is what a client actually observes.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from dependencies.auth import get_current_tenant_id
from models.user import SYSTEM_USER_ID, User
from repositories.exceptions import ForbiddenError
from tests._envelope import assert_err, assert_ok
from tests._workflow import create_published_workflow


def _user(tenant_id: str | None) -> User:
    return User(
        id="u1",
        username="u1",
        first_name="Test",
        last_name="User",
        password="pw",
        email="u1@test.local",
        roles=[],
        tenant_id=tenant_id,
        created_by=SYSTEM_USER_ID,
        updated_by=SYSTEM_USER_ID,
    )


def test_get_current_tenant_id_returns_the_users_tenant() -> None:
    assert get_current_tenant_id(_user("tenant-x")) == "tenant-x"


def test_get_current_tenant_id_rejects_platform_scoped_caller() -> None:
    """``tenant_id is None`` means platform-scoped (system user, or an admin
    operating outside any tenant) -- tenant-scoped routes must stay closed to it.
    """
    with pytest.raises(ForbiddenError):
        get_current_tenant_id(_user(None))


async def test_cross_tenant_workflow_access_is_404(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A caller in a different tenant gets 404, not 403, fetching another tenant's workflow.

    404 (not 403) matches the existing cross-user convention for notifications:
    the tenant boundary should not even reveal that the resource exists.
    """
    client, _eng = workflow_client_with_engine
    skill = assert_ok(
        await client.post(
            "/api/v1/agent-skills",
            json={"name": "tenant-skill", "repo_url": "https://github.com/x/y"},
        ),
        status=201,
    )
    workflow = await create_published_workflow(
        client, skill["id"], name="tenant-wf", prompt="do it"
    )

    res = await client.get(
        f"/api/v1/workflows/{workflow['id']}",
        headers={"X-User-Tenant-Id": "tenant-cross"},
    )
    assert_err(res, "NOT_FOUND", 404)

    # The same-tenant caller (no override -- the default test tenant) still can.
    assert_ok(await client.get(f"/api/v1/workflows/{workflow['id']}"))


async def test_platform_scoped_caller_is_forbidden_on_tenant_scoped_route(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """An explicit empty ``X-User-Tenant-Id`` opts into a platform-scoped caller."""
    client, _eng = workflow_client_with_engine
    res = await client.get("/api/v1/workflows", headers={"X-User-Tenant-Id": ""})
    assert_err(res, "FORBIDDEN", 403)
