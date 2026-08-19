"""Unit tests for :class:`services.approver_groups.ApproverGroupResolver`.

The resolver is the single place that decides which groups a caller counts as
an eligible approver for. Its role gate is the security-relevant half: without
it, ``ApprovalRepository.exists_for_approver`` would hand the shared workflow
chat to every member of an approver group, including the ones who cannot
approve anything. These tests pin that behaviour directly rather than only
through the API, so a refactor that drops the gate fails here first.
"""

from collections.abc import AsyncGenerator
from typing import Any

import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from models.user import Role, User
from models.user_group import UserGroup, UserGroupMember
from repositories import SqlEffectiveRoleRepository, SqlUserGroupRepository
from repositories.user import SqlUserRepository
from services.approver_groups import ApproverGroupResolver
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users


@pytest_asyncio.fixture()
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """Yield an in-memory engine with the schema, a tenant, and test users seeded."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa_event.listens_for(eng.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await seed_users(eng)
    await seed_tenant(eng)
    try:
        yield eng
    finally:
        await eng.dispose()


async def _make_group(
    eng: AsyncEngine,
    *,
    group_id: str,
    roles: list[str],
    member_ids: tuple[str, ...],
) -> None:
    """Insert a group granting ``roles`` with ``member_ids`` as its members."""
    async with AsyncSession(eng) as db:
        db.add(
            UserGroup(
                id=group_id,
                tenant_id=DEFAULT_TEST_TENANT_ID,
                name=group_id,
                roles=roles,
                created_by="owner",
                updated_by="owner",
            )
        )
        for member_id in member_ids:
            db.add(UserGroupMember(group_id=group_id, user_id=member_id))
        await db.commit()


def _resolver(db: AsyncSession) -> ApproverGroupResolver:
    """Build a resolver wired to the tenant every fixture seeds."""
    return ApproverGroupResolver(
        SqlUserGroupRepository(
            db, SqlUserRepository(db), tenant_id=DEFAULT_TEST_TENANT_ID
        ),
        SqlEffectiveRoleRepository(db),
    )


def _user(user_id: str, roles: list[Role]) -> User:
    """Build the in-memory caller the authorization layer passes around."""
    return User.model_construct(
        id=user_id, roles=[r.value for r in roles], tenant_id=DEFAULT_TEST_TENANT_ID
    )


async def test_returns_group_ids_for_a_direct_approver(engine: AsyncEngine) -> None:
    await _make_group(engine, group_id="g1", roles=[], member_ids=("bob",))
    async with AsyncSession(engine) as db:
        result = await _resolver(db).group_ids_for(_user("bob", [Role.approver]))
    assert result == ("g1",)


async def test_returns_nothing_without_the_approver_role(engine: AsyncEngine) -> None:
    """Membership alone must confer nothing -- this is the gate that matters."""
    await _make_group(engine, group_id="g1", roles=[], member_ids=("bob",))
    async with AsyncSession(engine) as db:
        result = await _resolver(db).group_ids_for(_user("bob", [Role.developer]))
    assert result == ()


async def test_role_inherited_from_a_group_qualifies(engine: AsyncEngine) -> None:
    """The union of direct and group-granted roles is what the gate reads."""
    await _make_group(
        engine, group_id="g1", roles=[Role.approver.value], member_ids=("bob",)
    )
    async with AsyncSession(engine) as db:
        result = await _resolver(db).group_ids_for(_user("bob", []))
    assert result == ("g1",)


async def test_returns_nothing_for_a_user_in_no_group(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as db:
        result = await _resolver(db).group_ids_for(_user("bob", [Role.approver]))
    assert result == ()


async def test_returns_every_group_the_caller_belongs_to(engine: AsyncEngine) -> None:
    await _make_group(engine, group_id="g1", roles=[], member_ids=("bob",))
    await _make_group(engine, group_id="g2", roles=[], member_ids=("bob", "carol"))
    async with AsyncSession(engine) as db:
        result = await _resolver(db).group_ids_for(_user("bob", [Role.approver]))
    assert set(result) == {"g1", "g2"}


async def test_supplied_roles_take_precedence_over_a_lookup(
    engine: AsyncEngine,
) -> None:
    """The ``caller_roles`` fast path is used as given, not re-resolved.

    Callers that already hold ``EffectiveRolesDep`` pass it in to save a query;
    passing roles that do not include ``approver`` must therefore short-circuit
    even for a user the database would qualify.
    """
    await _make_group(
        engine, group_id="g1", roles=[Role.approver.value], member_ids=("bob",)
    )
    async with AsyncSession(engine) as db:
        resolver = _resolver(db)
        assert await resolver.group_ids_for(_user("bob", []), []) == ()
        assert await resolver.group_ids_for(_user("bob", []), ["approver"]) == ("g1",)


async def test_a_platform_scoped_super_admin_resolves_to_no_groups(
    engine: AsyncEngine,
) -> None:
    """A super admin passes the role test but can never be in a tenant group."""
    async with AsyncSession(engine) as db:
        result = await _resolver(db).group_ids_for(
            User.model_construct(id="root", roles=["super_admin"], tenant_id=None)
        )
    assert result == ()
