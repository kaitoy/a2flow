"""Tests for the ``/user-groups`` endpoints and role inheritance through them.

Covers the group CRUD surface, its tenant boundary, the ``super_admin``
prohibition, membership validation, and — the point of the whole feature — that
a user holding a role only through a group is authorized as if they held it
directly.
"""

from collections.abc import AsyncGenerator
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.bootstrap import seed_system_user
from models.approval import Approval
from models.user import SYSTEM_USER_ID, Role, User
from models.user_group import UserGroup, UserGroupMember
from models.workflow_execution import WorkflowExecution
from repositories.effective_roles import SqlEffectiveRoleRepository
from repositories.user import SqlUserRepository
from repositories.user_group import SqlUserGroupRepository
from tests._engine import make_test_engine
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users
from tests.conftest import _install_auth_overrides

#: A second tenant used by the isolation tests.
OTHER_TENANT_ID = "tenant-other"

#: Headers selecting a plain (non-super-admin) admin of the default tenant.
ADMIN: dict[str, str] = {"X-User-Id": "alice", "X-User-Roles": "admin"}

#: Headers selecting a role-less user of the default tenant.
NOBODY: dict[str, str] = {"X-User-Id": "bob", "X-User-Roles": ""}


@pytest_asyncio.fixture()
async def group_env() -> AsyncGenerator[tuple[AsyncClient, AsyncEngine], None]:
    """Yield an API client plus the throwaway engine backing it."""
    from infrastructure.database import get_session
    from main import app

    mem_engine = await make_test_engine()
    async with AsyncSession(mem_engine) as session:
        await seed_system_user(session)
    await seed_tenant(mem_engine, DEFAULT_TEST_TENANT_ID)
    await seed_tenant(mem_engine, OTHER_TENANT_ID)
    await seed_users(mem_engine, ("alice", "bob", "carol"), roles=())
    await seed_users(mem_engine, ("outsider",), roles=(), tenant_id=OTHER_TENANT_ID)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(mem_engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    _install_auth_overrides(app)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-User-Id": SYSTEM_USER_ID},
        ) as ac:
            yield ac, mem_engine
    finally:
        app.dependency_overrides.clear()
        await mem_engine.dispose()


async def _create(client: AsyncClient, **overrides: Any) -> dict[str, Any]:
    """Create a group through the API and return its read model."""
    body: dict[str, Any] = {"name": "Developers", "roles": ["developer"]}
    body.update(overrides)
    response = await client.post("/api/v1/user-groups", json=body, headers=ADMIN)
    return dict(assert_ok(response, 201))


# ---------- CRUD ----------


async def test_create_returns_the_group_with_its_members(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    group = await _create(client, memberIds=["alice", "bob"])
    assert group["name"] == "Developers"
    assert group["roles"] == ["developer"]
    assert group["memberIds"] == ["alice", "bob"]
    assert group["tenantId"] == DEFAULT_TEST_TENANT_ID


async def test_create_defaults_to_an_empty_group(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    group = await _create(client, roles=[])
    assert group["roles"] == []
    assert group["memberIds"] == []


async def test_get_returns_the_group(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    created = await _create(client, memberIds=["carol"])
    fetched = assert_ok(
        await client.get(f"/api/v1/user-groups/{created['id']}", headers=NOBODY)
    )
    assert fetched["id"] == created["id"]
    assert fetched["memberIds"] == ["carol"]


async def test_get_unknown_group_returns_404(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    response = await client.get("/api/v1/user-groups/missing", headers=ADMIN)
    assert_err(response, "NOT_FOUND", 404)


async def test_list_returns_the_tenants_groups(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    await _create(client, name="Developers")
    await _create(client, name="Approvers", roles=["approver"])
    items = assert_ok(await client.get("/api/v1/user-groups", headers=NOBODY))
    assert {item["name"] for item in items} == {"Developers", "Approvers"}


async def test_update_replaces_members_wholesale(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    created = await _create(client, memberIds=["alice", "bob"])
    updated = assert_ok(
        await client.patch(
            f"/api/v1/user-groups/{created['id']}",
            json={"memberIds": ["carol"]},
            headers=ADMIN,
        )
    )
    assert updated["memberIds"] == ["carol"]


async def test_update_without_member_ids_leaves_membership_alone(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    created = await _create(client, memberIds=["alice"])
    updated = assert_ok(
        await client.patch(
            f"/api/v1/user-groups/{created['id']}",
            json={"description": "renamed"},
            headers=ADMIN,
        )
    )
    assert updated["memberIds"] == ["alice"]
    assert updated["description"] == "renamed"


async def test_update_with_an_empty_member_list_empties_the_group(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    created = await _create(client, memberIds=["alice"])
    updated = assert_ok(
        await client.patch(
            f"/api/v1/user-groups/{created['id']}",
            json={"memberIds": []},
            headers=ADMIN,
        )
    )
    assert updated["memberIds"] == []


async def test_delete_removes_the_group_and_its_memberships(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = group_env
    created = await _create(client, memberIds=["alice"])
    assert_ok(
        await client.delete(f"/api/v1/user-groups/{created['id']}", headers=ADMIN)
    )
    async with AsyncSession(engine) as session:
        assert await session.get(UserGroup, created["id"]) is None
        assert await session.get(UserGroupMember, (created["id"], "alice")) is None


async def test_duplicate_name_in_one_tenant_conflicts(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    await _create(client, name="Developers")
    response = await client.post(
        "/api/v1/user-groups",
        json={"name": "Developers", "roles": []},
        headers=ADMIN,
    )
    assert_err(response, "CONFLICT_UNIQUE", 409)


# ---------- validation ----------


async def test_super_admin_role_is_rejected(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    response = await client.post(
        "/api/v1/user-groups",
        json={"name": "Gods", "roles": ["super_admin"]},
        headers=ADMIN,
    )
    assert_err(response, "VALIDATION_ERROR", 422)


async def test_super_admin_role_is_rejected_on_update(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    created = await _create(client)
    response = await client.patch(
        f"/api/v1/user-groups/{created['id']}",
        json={"roles": ["super_admin"]},
        headers=ADMIN,
    )
    assert response.status_code == 422


async def test_a_user_of_another_tenant_cannot_be_a_member(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    response = await client.post(
        "/api/v1/user-groups",
        json={"name": "Developers", "roles": [], "memberIds": ["outsider"]},
        headers=ADMIN,
    )
    # Reported as a missing reference, never as "exists in another tenant".
    error = assert_err(response, "FOREIGN_KEY_VIOLATION", 422)
    assert error["details"]["id"] == "outsider"


async def test_an_unknown_user_cannot_be_a_member(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    response = await client.post(
        "/api/v1/user-groups",
        json={"name": "Developers", "roles": [], "memberIds": ["ghost"]},
        headers=ADMIN,
    )
    assert response.status_code == 422


async def test_the_system_user_cannot_be_a_member(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    response = await client.post(
        "/api/v1/user-groups",
        json={"name": "Developers", "roles": [], "memberIds": [SYSTEM_USER_ID]},
        headers=ADMIN,
    )
    assert response.status_code == 422


async def test_member_ids_cannot_be_filtered_or_sorted_on(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    response = await client.get(
        "/api/v1/user-groups?q=memberIds:eq:alice", headers=ADMIN
    )
    assert_err(response, "INVALID_QUERY", 400)


# ---------- authorization ----------


async def test_writes_require_the_admin_role(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    response = await client.post(
        "/api/v1/user-groups", json={"name": "Developers", "roles": []}, headers=NOBODY
    )
    assert response.status_code == 403


async def test_reads_are_open_to_any_authenticated_user(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    response = await client.get("/api/v1/user-groups", headers=NOBODY)
    assert response.status_code == 200


async def test_another_tenants_group_is_not_found(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    created = await _create(client)
    other_tenant = {
        "X-User-Id": "outsider",
        "X-User-Roles": "admin",
        "X-User-Tenant-Id": OTHER_TENANT_ID,
    }
    response = await client.get(
        f"/api/v1/user-groups/{created['id']}", headers=other_tenant
    )
    assert response.status_code == 404


async def test_list_does_not_mix_tenants(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    await _create(client, name="Developers")
    other_tenant = {
        "X-User-Id": "outsider",
        "X-User-Roles": "admin",
        "X-User-Tenant-Id": OTHER_TENANT_ID,
    }
    items = assert_ok(await client.get("/api/v1/user-groups", headers=other_tenant))
    assert items == []


# ---------- role inheritance ----------


async def _inherited(engine: AsyncEngine, user_id: str) -> frozenset[str]:
    """Return the roles ``user_id`` inherits from group membership."""
    async with AsyncSession(engine) as session:
        return await SqlEffectiveRoleRepository(session).group_roles_for_user(user_id)


async def test_a_member_inherits_the_groups_roles(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = group_env
    await _create(client, roles=["developer", "requester"], memberIds=["alice"])
    assert await _inherited(engine, "alice") == {"developer", "requester"}


async def test_roles_from_several_groups_are_unioned(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = group_env
    await _create(client, name="Developers", roles=["developer"], memberIds=["alice"])
    await _create(client, name="Approvers", roles=["approver"], memberIds=["alice"])
    assert await _inherited(engine, "alice") == {"developer", "approver"}


async def test_removing_a_member_revokes_the_inherited_roles(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = group_env
    created = await _create(client, memberIds=["alice"])
    assert await _inherited(engine, "alice") == {"developer"}
    assert_ok(
        await client.patch(
            f"/api/v1/user-groups/{created['id']}",
            json={"memberIds": []},
            headers=ADMIN,
        )
    )
    assert await _inherited(engine, "alice") == frozenset()


async def test_deleting_a_group_revokes_the_inherited_roles(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = group_env
    created = await _create(client, memberIds=["alice"])
    assert_ok(
        await client.delete(f"/api/v1/user-groups/{created['id']}", headers=ADMIN)
    )
    assert await _inherited(engine, "alice") == frozenset()


async def test_changing_a_groups_roles_changes_what_members_hold(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = group_env
    created = await _create(client, memberIds=["alice"])
    assert_ok(
        await client.patch(
            f"/api/v1/user-groups/{created['id']}",
            json={"roles": ["approver"]},
            headers=ADMIN,
        )
    )
    assert await _inherited(engine, "alice") == {"approver"}


async def test_deleting_a_member_user_drops_their_membership(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """The user side of the join cascades, so a grouped user stays hard-deletable."""
    client, engine = group_env
    created = await _create(client, memberIds=["carol"])
    async with AsyncSession(engine) as session:
        carol = await session.get(User, "carol")
        assert carol is not None
        await session.delete(carol)
        await session.commit()
    async with AsyncSession(engine) as session:
        assert await session.get(UserGroupMember, (created["id"], "carol")) is None


# ---------- membership from the user side ----------


async def test_put_user_groups_replaces_membership(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = group_env
    devs = await _create(client, name="Developers", roles=["developer"])
    approvers = await _create(client, name="Approvers", roles=["approver"])
    user = assert_ok(
        await client.put(
            "/api/v1/users/alice/groups",
            json={"groupIds": [devs["id"], approvers["id"]]},
            headers=ADMIN,
        )
    )
    assert sorted(user["groupRoles"]) == ["approver", "developer"]
    assert user["roles"] == []
    assert await _inherited(engine, "alice") == {"developer", "approver"}

    cleared = assert_ok(
        await client.put(
            "/api/v1/users/alice/groups", json={"groupIds": []}, headers=ADMIN
        )
    )
    assert cleared["groupRoles"] == []


async def test_put_user_groups_requires_admin(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    response = await client.put(
        "/api/v1/users/alice/groups", json={"groupIds": []}, headers=NOBODY
    )
    assert response.status_code == 403


async def test_put_user_groups_rejects_another_tenants_group(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    created = await _create(client)
    other_tenant = {
        "X-User-Id": "outsider",
        "X-User-Roles": "admin",
        "X-User-Tenant-Id": OTHER_TENANT_ID,
    }
    response = await client.put(
        "/api/v1/users/outsider/groups",
        json={"groupIds": [created["id"]]},
        headers=other_tenant,
    )
    assert_err(response, "FOREIGN_KEY_VIOLATION", 422)


async def test_put_user_groups_on_another_tenants_user_is_not_found(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    response = await client.put(
        "/api/v1/users/outsider/groups", json={"groupIds": []}, headers=ADMIN
    )
    assert response.status_code == 404


# ---------- read models ----------


async def test_user_read_reports_direct_and_inherited_roles_separately(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = group_env
    created = await _create(client, memberIds=["alice"])
    assert created["memberIds"] == ["alice"]
    async with AsyncSession(engine) as session:
        alice = await session.get(User, "alice")
        assert alice is not None
        alice.roles = [Role.approver.value]
        session.add(alice)
        await session.commit()

    user = assert_ok(await client.get("/api/v1/users/alice", headers=ADMIN))
    assert user["roles"] == ["approver"]
    assert user["groupRoles"] == ["developer"]


async def test_user_list_reports_inherited_roles(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    await _create(client, memberIds=["alice"])
    users = assert_ok(await client.get("/api/v1/users", headers=ADMIN))
    by_id = {user["id"]: user for user in users}
    assert by_id["alice"]["groupRoles"] == ["developer"]
    assert by_id["bob"]["groupRoles"] == []


# ---------- membership read from the user side ----------


async def test_groups_for_user_returns_the_groups_they_belong_to(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    await _create(client, name="Developers", memberIds=["alice"])
    await _create(client, name="Approvers", roles=["approver"], memberIds=["bob"])

    groups = assert_ok(await client.get("/api/v1/users/alice/groups", headers=ADMIN))

    assert [group["name"] for group in groups] == ["Developers"]
    assert groups[0]["memberIds"] == ["alice"]


async def test_groups_for_user_is_readable_without_the_admin_role(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    await _create(client, memberIds=["carol"])

    groups = assert_ok(await client.get("/api/v1/users/carol/groups", headers=NOBODY))

    assert [group["name"] for group in groups] == ["Developers"]


async def test_groups_for_user_is_empty_when_they_belong_to_none(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    await _create(client, memberIds=["alice"])

    groups = assert_ok(await client.get("/api/v1/users/bob/groups", headers=ADMIN))

    assert groups == []


async def test_groups_for_user_404s_for_a_user_of_another_tenant(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env

    response = await client.get("/api/v1/users/outsider/groups", headers=ADMIN)

    assert_err(response, "NOT_FOUND", 404)


async def test_delete_is_refused_while_an_approval_is_addressed_to_the_group(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A group that is still some approval's destination cannot be deleted.

    ``fk_approvals_approver_group_id`` is ``ON DELETE RESTRICT``, because
    dropping the group would leave a request nobody could ever resolve. The
    repository translates the resulting IntegrityError, so the caller sees 409
    rather than a 500.
    """
    client, engine = group_env
    created = await _create(client, memberIds=["alice"])
    async with AsyncSession(engine) as session:
        session.add(
            WorkflowExecution(
                id="exec-1",
                session_id="sess-1",
                name="wf",
                agent_skill_id="skill-1",
                agent_skill_name="skill",
                agent_skill_repo_url="https://example.com/repo",
                agent_skill_repo_path=".",
                initiator_id="alice",
                tenant_id=DEFAULT_TEST_TENANT_ID,
                created_by="alice",
                updated_by="alice",
            )
        )
        await session.commit()
        session.add(
            Approval(
                workflow_execution_id="exec-1",
                title="Approve me",
                approver_group_id=created["id"],
                tenant_id=DEFAULT_TEST_TENANT_ID,
                created_by="alice",
                updated_by="alice",
            )
        )
        await session.commit()

    assert_err(
        await client.delete(f"/api/v1/user-groups/{created['id']}", headers=ADMIN),
        "CONFLICT_REFERENCED",
        409,
    )
    async with AsyncSession(engine) as session:
        assert await session.get(UserGroup, created["id"]) is not None


# ---------- IdP-mapped groups ----------


async def test_idp_group_unique_within_tenant(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    await _create(client, idpGroup="eng")
    response = await client.post(
        "/api/v1/user-groups",
        json={"name": "Other", "idpGroup": "eng"},
        headers=ADMIN,
    )
    error = assert_err(response, "CONFLICT_UNIQUE", 409)
    assert error["details"] == {"field": "idpGroup", "value": "eng"}


async def test_empty_idp_group_is_rejected(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    response = await client.post(
        "/api/v1/user-groups", json={"name": "G", "idpGroup": ""}, headers=ADMIN
    )
    assert_err(response, "VALIDATION_ERROR", 422)


async def test_mapped_group_members_cannot_change(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    group = await _create(client, idpGroup="eng")
    url = f"/api/v1/user-groups/{group['id']}"
    assert_err(
        await client.patch(url, json={"memberIds": ["alice"]}, headers=ADMIN),
        "INVALID_USER_GROUP",
        422,
    )
    renamed = assert_ok(
        await client.patch(url, json={"name": "Renamed"}, headers=ADMIN)
    )
    assert renamed["name"] == "Renamed"
    assert_err(
        await client.post(
            "/api/v1/user-groups",
            json={"name": "New", "idpGroup": "ops", "memberIds": ["alice"]},
            headers=ADMIN,
        ),
        "INVALID_USER_GROUP",
        422,
    )


async def test_mapping_a_group_and_changing_members_together_is_refused(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    group = await _create(client, memberIds=["alice"])
    url = f"/api/v1/user-groups/{group['id']}"
    assert_err(
        await client.patch(
            url, json={"idpGroup": "eng", "memberIds": ["bob"]}, headers=ADMIN
        ),
        "INVALID_USER_GROUP",
        422,
    )


async def test_unmapping_a_group_makes_its_members_editable(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    group = await _create(client, idpGroup="eng")
    url = f"/api/v1/user-groups/{group['id']}"
    cleared = assert_ok(await client.patch(url, json={"idpGroup": None}, headers=ADMIN))
    assert cleared["idpGroup"] is None
    updated = assert_ok(
        await client.patch(url, json={"memberIds": ["alice"]}, headers=ADMIN)
    )
    assert updated["memberIds"] == ["alice"]


async def test_patch_unknown_group_is_still_404_with_member_ids(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    assert_err(
        await client.patch(
            "/api/v1/user-groups/nope", json={"memberIds": ["alice"]}, headers=ADMIN
        ),
        "NOT_FOUND",
        404,
    )


async def test_put_user_groups_cannot_touch_mapped_group(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = group_env
    mapped = await _create(client, name="Mapped", idpGroup="eng")
    plain = await _create(client, name="Plain", roles=[])
    other = await _create(client, name="Other", roles=[])
    url = "/api/v1/users/alice/groups"
    # Adding a mapped group is refused.
    assert_err(
        await client.put(url, json={"groupIds": [mapped["id"]]}, headers=ADMIN),
        "INVALID_USER_GROUP",
        422,
    )
    # Put alice in the mapped group the way a sign-in sync would.
    async with AsyncSession(engine) as session:
        session.add(UserGroupMember(group_id=mapped["id"], user_id="alice"))
        await session.commit()
    # Dropping it is refused too.
    assert_err(
        await client.put(url, json={"groupIds": [plain["id"]]}, headers=ADMIN),
        "INVALID_USER_GROUP",
        422,
    )
    # Changing only unmapped groups while keeping the mapped one is fine.
    assert_ok(
        await client.put(
            url, json={"groupIds": [mapped["id"], plain["id"]]}, headers=ADMIN
        )
    )
    assert_ok(
        await client.put(
            url, json={"groupIds": [mapped["id"], other["id"]]}, headers=ADMIN
        )
    )


async def test_sync_mapped_membership_leaves_unmapped_groups(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    _, engine = group_env
    async with AsyncSession(engine) as session:
        for gid, idp in (("g0", None), ("g1", "a"), ("g2", "b")):
            session.add(
                UserGroup(
                    id=gid,
                    name=gid,
                    idp_group=idp,
                    tenant_id=DEFAULT_TEST_TENANT_ID,
                    created_by="alice",
                    updated_by="alice",
                )
            )
        await session.commit()
        session.add(UserGroupMember(group_id="g0", user_id="alice"))
        session.add(UserGroupMember(group_id="g1", user_id="alice"))
        await session.commit()

        repo = SqlUserGroupRepository(
            session, SqlUserRepository(session), tenant_id=DEFAULT_TEST_TENANT_ID
        )
        assert {g.id for g in await repo.list_mapped()} == {"g1", "g2"}
        await repo.sync_mapped_membership("alice", ["b"])
        assert await repo.group_ids_for_user("alice") == ["g0", "g2"]
