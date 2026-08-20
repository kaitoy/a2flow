"""Tests for the optional demo dataset in ``infrastructure.demo_data``.

Covers both directions of the ``DEMO_DATA`` flag: enabled, every missing demo
record is registered in the seeded ``Default`` tenant (idempotently, and
returning the agent skill's id exactly once so its clone is scheduled only on
first registration); disabled, every demo record is removed again, tolerating
records that other data has come to reference.
"""

import logging
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from infrastructure.bootstrap import DEFAULT_TENANT_NAME, seed_system_user
from infrastructure.demo_data import (
    DEMO_ACCESS_KEY_ENTRY_KEY,
    DEMO_AGENT_SKILL_ID,
    DEMO_AGENT_SKILL_NAME,
    DEMO_APPROVAL_TAG_ID,
    DEMO_APPROVAL_TAG_NAME,
    DEMO_APPROVER_2_USER_ID,
    DEMO_APPROVER_USER_ID,
    DEMO_APPROVERS_GROUP_ID,
    DEMO_AWS_SECRET_ID,
    DEMO_AWS_SECRET_NAME,
    DEMO_AWS_TAG_ID,
    DEMO_AWS_TAG_NAME,
    DEMO_DEVELOPER_USER_ID,
    DEMO_DEVELOPERS_GROUP_ID,
    DEMO_MCP_SERVER_ID,
    DEMO_MCP_SERVER_NAME,
    DEMO_REQUESTER_USER_ID,
    DEMO_REQUESTERS_GROUP_ID,
    DEMO_SECRET_KEY_ENTRY_KEY,
    sync_demo_data,
)
from infrastructure.password import verify_password
from infrastructure.secret_cipher import get_secret_cipher
from models.agent_skill import AgentSkill, SkillSyncStatus
from models.mcp_server import McpCommand, MCPServer, McpTransport
from models.secret import Secret, SecretType
from models.tag import AgentSkillTag, McpServerTag, SecretTag, Tag
from models.tenant import Tenant
from models.user import SYSTEM_USER_ID, Role, User
from models.user_group import UserGroup, UserGroupMember
from repositories.effective_roles import SqlEffectiveRoleRepository

#: Fixed id of the ``Default`` tenant the fixture seeds, so tests can assert on
#: the ``tenant_id`` the demo records land in without re-querying it.
TENANT_ID = "tenant-default"

_BOOTSTRAP_LOGGER = "infrastructure.bootstrap"
_DEMO_LOGGER = "infrastructure.demo_data"


async def _fresh_engine(*, with_default_tenant: bool = True) -> AsyncEngine:
    """Create an in-memory SQLite engine with the schema and system user seeded.

    Args:
        with_default_tenant: Whether to also insert the seeded ``Default``
            tenant the demo records hang off.

    Returns:
        The prepared engine.
    """
    mem_engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa_event.listens_for(mem_engine.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with mem_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(mem_engine) as session:
        await seed_system_user(session)
        if with_default_tenant:
            session.add(
                Tenant(
                    id=TENANT_ID,
                    display_name="Default",
                    name=DEFAULT_TENANT_NAME,
                    enabled=True,
                    created_by=SYSTEM_USER_ID,
                    updated_by=SYSTEM_USER_ID,
                )
            )
            await session.commit()
    return mem_engine


@pytest_asyncio.fixture()
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """Provide an engine with the schema, system user, and Default tenant seeded."""
    mem_engine = await _fresh_engine()
    try:
        yield mem_engine
    finally:
        await mem_engine.dispose()


@pytest.fixture(autouse=True)
def _demo_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test from a clean, fully unset demo configuration."""
    for name in (
        "DEMO_DATA",
        "DEMO_PASSWORD",
        "DEMO_AWS_ACCESS_KEY_ID",
        "DEMO_AWS_SECRET_ACCESS_KEY",
        "DEMO_AWS_REGION",
    ):
        monkeypatch.delenv(name, raising=False)


def _enable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn the demo dataset on for the next :func:`_sync`."""
    monkeypatch.setenv("DEMO_DATA", "true")


def _disable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn the demo dataset off for the next :func:`_sync`."""
    monkeypatch.delenv("DEMO_DATA", raising=False)


async def _sync(engine: AsyncEngine) -> str | None:
    """Run :func:`sync_demo_data` on a session of its own, as one app start would.

    Clears the memoized ``Settings`` singleton first so a test that flips
    ``DEMO_DATA`` between calls really does model two separate startups —
    without it, the value read by the first call would be frozen for the rest
    of the test.

    Args:
        engine: Engine to open the session on.

    Returns:
        Whatever :func:`sync_demo_data` returned.
    """
    get_settings.cache_clear()
    async with AsyncSession(engine) as session:
        return await sync_demo_data(session)


def _bootstrap_warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """Return only the records the seed-password helper emitted.

    Other startup machinery logs at ``WARNING`` too (notably
    ``infrastructure.secret_cipher`` when it generates a key file), so the
    password assertions have to look at this logger alone.

    Args:
        caplog: The pytest log-capture fixture.

    Returns:
        The captured records emitted by ``infrastructure.bootstrap``.
    """
    return [record for record in caplog.records if record.name == _BOOTSTRAP_LOGGER]


async def _rows(engine: AsyncEngine, model: Any) -> list[Any]:
    """Return every persisted row of the given table model.

    Args:
        engine: Engine to open the session on.
        model: Table model class to select.

    Returns:
        All rows currently persisted.
    """
    async with AsyncSession(engine) as session:
        return list((await session.exec(select(model))).all())


async def _demo_users(engine: AsyncEngine) -> list[User]:
    """Return the non-system users, ordered by username."""
    async with AsyncSession(engine) as session:
        stmt = select(User).where(col(User.id) != SYSTEM_USER_ID)
        users = list((await session.exec(stmt)).all())
    return sorted(users, key=lambda user: user.username)


# ---------- seeding ----------


async def test_sync_demo_data_seeds_the_full_dataset(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    await _sync(engine)
    assert len(await _demo_users(engine)) == 4
    assert len(await _rows(engine, Secret)) == 1
    assert len(await _rows(engine, MCPServer)) == 1
    assert len(await _rows(engine, AgentSkill)) == 1
    assert len(await _rows(engine, Tag)) == 2


async def test_sync_demo_data_returns_the_new_skill_id(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The caller schedules the clone, so the id comes back on first seed."""
    _enable(monkeypatch)
    assert await _sync(engine) == DEMO_AGENT_SKILL_ID


async def test_sync_demo_data_returns_none_on_a_second_run(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A restart must not re-clone a skill that is already registered."""
    _enable(monkeypatch)
    await _sync(engine)
    assert await _sync(engine) is None


async def test_sync_demo_data_is_idempotent(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    await _sync(engine)
    await _sync(engine)
    assert len(await _demo_users(engine)) == 4
    assert len(await _rows(engine, Secret)) == 1
    assert len(await _rows(engine, MCPServer)) == 1
    assert len(await _rows(engine, AgentSkill)) == 1
    assert len(await _rows(engine, Tag)) == 2
    assert len(await _rows(engine, SecretTag)) == 1
    assert len(await _rows(engine, McpServerTag)) == 1
    assert len(await _rows(engine, AgentSkillTag)) == 2


async def test_demo_tags_classify_the_secret_mcp_server_and_agent_skill(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    await _sync(engine)
    tags = {tag.id: tag for tag in await _rows(engine, Tag)}
    assert set(tags) == {DEMO_AWS_TAG_ID, DEMO_APPROVAL_TAG_ID}
    assert tags[DEMO_AWS_TAG_ID].name == DEMO_AWS_TAG_NAME
    assert tags[DEMO_APPROVAL_TAG_ID].name == DEMO_APPROVAL_TAG_NAME
    secret_tags = {
        (row.resource_id, row.tag_id) for row in await _rows(engine, SecretTag)
    }
    assert secret_tags == {(DEMO_AWS_SECRET_ID, DEMO_AWS_TAG_ID)}
    mcp_server_tags = {
        (row.resource_id, row.tag_id) for row in await _rows(engine, McpServerTag)
    }
    assert mcp_server_tags == {(DEMO_MCP_SERVER_ID, DEMO_AWS_TAG_ID)}
    agent_skill_tags = {
        (row.resource_id, row.tag_id) for row in await _rows(engine, AgentSkillTag)
    }
    assert agent_skill_tags == {
        (DEMO_AGENT_SKILL_ID, DEMO_AWS_TAG_ID),
        (DEMO_AGENT_SKILL_ID, DEMO_APPROVAL_TAG_ID),
    }


async def test_demo_users_hold_no_direct_roles(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    await _sync(engine)
    approver, approver_2, developer, requester = await _demo_users(engine)
    assert approver.id == DEMO_APPROVER_USER_ID
    assert approver.username == "demo-approver-1"
    assert approver_2.id == DEMO_APPROVER_2_USER_ID
    assert approver_2.username == "demo-approver-2"
    assert developer.id == DEMO_DEVELOPER_USER_ID
    assert developer.username == "demo-developer"
    assert requester.id == DEMO_REQUESTER_USER_ID
    assert requester.username == "demo-requester"
    for user in (approver, approver_2, developer, requester):
        assert user.roles == []
        assert user.tenant_id == TENANT_ID
        assert user.enabled is True
        assert user.created_by == SYSTEM_USER_ID


async def test_demo_groups_grant_the_approver_requester_and_developer_roles(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    await _sync(engine)
    groups = {group.id: group for group in await _rows(engine, UserGroup)}
    assert len(groups) == 3
    expected = {
        DEMO_APPROVERS_GROUP_ID: ("Demo Approvers", Role.approver),
        DEMO_REQUESTERS_GROUP_ID: ("Demo Requesters", Role.requester),
        DEMO_DEVELOPERS_GROUP_ID: ("Demo Developers", Role.developer),
    }
    for group_id, (name, role) in expected.items():
        group = groups[group_id]
        assert group.name == name
        assert group.roles == [role.value]
        assert group.tenant_id == TENANT_ID
        assert group.created_by == SYSTEM_USER_ID


async def test_demo_approvers_group_holds_both_approvers_the_rest_hold_one(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    await _sync(engine)
    members = {
        (row.group_id, row.user_id) for row in await _rows(engine, UserGroupMember)
    }
    assert members == {
        (DEMO_APPROVERS_GROUP_ID, DEMO_APPROVER_USER_ID),
        (DEMO_APPROVERS_GROUP_ID, DEMO_APPROVER_2_USER_ID),
        (DEMO_REQUESTERS_GROUP_ID, DEMO_REQUESTER_USER_ID),
        (DEMO_DEVELOPERS_GROUP_ID, DEMO_DEVELOPER_USER_ID),
    }


async def test_demo_users_effective_roles_come_from_their_group(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    await _sync(engine)
    async with AsyncSession(engine) as session:
        inherited = await SqlEffectiveRoleRepository(session).group_roles_for_users(
            [
                DEMO_APPROVER_USER_ID,
                DEMO_APPROVER_2_USER_ID,
                DEMO_REQUESTER_USER_ID,
                DEMO_DEVELOPER_USER_ID,
            ]
        )
    assert inherited == {
        DEMO_APPROVER_USER_ID: frozenset({Role.approver.value}),
        DEMO_APPROVER_2_USER_ID: frozenset({Role.approver.value}),
        DEMO_REQUESTER_USER_ID: frozenset({Role.requester.value}),
        DEMO_DEVELOPER_USER_ID: frozenset({Role.developer.value}),
    }


async def test_reviving_an_older_demo_user_strips_its_direct_roles(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A database seeded before groups existed migrates to pure inheritance."""
    _enable(monkeypatch)
    await _sync(engine)
    async with AsyncSession(engine) as session:
        legacy = await session.get(User, DEMO_APPROVER_USER_ID)
        assert legacy is not None
        legacy.roles = [Role.approver.value]
        session.add(legacy)
        await session.commit()

    await _sync(engine)

    async with AsyncSession(engine) as session:
        migrated = await session.get(User, DEMO_APPROVER_USER_ID)
        assert migrated is not None
        assert migrated.roles == []


async def test_removing_demo_data_deletes_the_groups(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    await _sync(engine)
    monkeypatch.setenv("DEMO_DATA", "false")
    get_settings.cache_clear()
    await _sync(engine)
    assert await _rows(engine, UserGroup) == []
    assert await _rows(engine, UserGroupMember) == []


async def test_demo_users_honour_the_configured_password(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _enable(monkeypatch)
    monkeypatch.setenv("DEMO_PASSWORD", "demo-secret-pw")
    with caplog.at_level(logging.WARNING, logger=_BOOTSTRAP_LOGGER):
        await _sync(engine)
    for user in await _demo_users(engine):
        assert verify_password("demo-secret-pw", user.password)
    assert _bootstrap_warnings(caplog) == []


async def test_demo_password_is_generated_and_logged_exactly_once(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Both accounts share one generated password, so it is logged once, not twice."""
    _enable(monkeypatch)
    with caplog.at_level(logging.WARNING, logger=_BOOTSTRAP_LOGGER):
        await _sync(engine)
    records = _bootstrap_warnings(caplog)
    assert len(records) == 1
    assert "DEMO_PASSWORD not set" in records[0].getMessage()
    args = records[0].args
    assert isinstance(args, tuple)
    password = args[0]
    assert isinstance(password, str)
    for user in await _demo_users(engine):
        assert verify_password(password, user.password)


async def test_demo_password_is_not_generated_when_nothing_is_missing(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _enable(monkeypatch)
    await _sync(engine)
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=_BOOTSTRAP_LOGGER):
        await _sync(engine)
    assert _bootstrap_warnings(caplog) == []


async def test_demo_secrets_store_the_configured_values_encrypted(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    monkeypatch.setenv("DEMO_AWS_ACCESS_KEY_ID", "AKIAEXAMPLE")
    monkeypatch.setenv("DEMO_AWS_SECRET_ACCESS_KEY", "s3cr3t-key")
    await _sync(engine)
    async with AsyncSession(engine) as session:
        secret = await session.get(Secret, DEMO_AWS_SECRET_ID)
    assert secret is not None
    assert secret.name == DEMO_AWS_SECRET_NAME
    assert secret.description
    assert secret.type is SecretType.local
    assert secret.tenant_id == TENANT_ID
    assert sorted(secret.entries) == [
        DEMO_ACCESS_KEY_ENTRY_KEY,
        DEMO_SECRET_KEY_ENTRY_KEY,
    ]
    access_key = secret.entries[DEMO_ACCESS_KEY_ENTRY_KEY]
    assert access_key != "AKIAEXAMPLE"  # stored as ciphertext
    cipher = get_secret_cipher()
    assert cipher.decrypt(access_key) == "AKIAEXAMPLE"
    assert cipher.decrypt(secret.entries[DEMO_SECRET_KEY_ENTRY_KEY]) == "s3cr3t-key"


async def test_demo_secrets_fall_back_to_a_placeholder(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    await _sync(engine)
    async with AsyncSession(engine) as session:
        secret = await session.get(Secret, DEMO_AWS_SECRET_ID)
    assert secret is not None
    decrypted = get_secret_cipher().decrypt(secret.entries[DEMO_ACCESS_KEY_ENTRY_KEY])
    assert decrypted == "REPLACE_ME"


async def test_demo_mcp_server_proxies_the_managed_aws_server(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    monkeypatch.setenv("DEMO_AWS_REGION", "ap-northeast-1")
    await _sync(engine)
    async with AsyncSession(engine) as session:
        server = await session.get(MCPServer, DEMO_MCP_SERVER_ID)
    assert server is not None
    assert server.name == DEMO_MCP_SERVER_NAME
    assert server.description
    assert server.tenant_id == TENANT_ID
    assert server.transport is McpTransport.stdio
    assert server.command is McpCommand.uvx
    assert server.args == [
        "mcp-proxy-for-aws@1.6.4",
        "https://aws-mcp.us-east-1.api.aws/mcp",
        "--region",
        "us-east-1",
        "--metadata",
        "AWS_REGION=${env:AWS_REGION}",
    ]
    assert server.url is None
    assert server.headers == {}
    assert server.env == {
        "AWS_ACCESS_KEY_ID": (
            f"${{secret:{DEMO_AWS_SECRET_NAME}/{DEMO_ACCESS_KEY_ENTRY_KEY}}}"
        ),
        "AWS_SECRET_ACCESS_KEY": (
            f"${{secret:{DEMO_AWS_SECRET_NAME}/{DEMO_SECRET_KEY_ENTRY_KEY}}}"
        ),
        "AWS_REGION": "ap-northeast-1",
    }


async def test_demo_mcp_server_defaults_the_region(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    await _sync(engine)
    async with AsyncSession(engine) as session:
        server = await session.get(MCPServer, DEMO_MCP_SERVER_ID)
    assert server is not None
    assert server.args[-2:] == ["--metadata", "AWS_REGION=${env:AWS_REGION}"]
    assert server.env["AWS_REGION"] == "us-east-1"


async def test_demo_agent_skill_points_at_the_sample_skill(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    await _sync(engine)
    async with AsyncSession(engine) as session:
        skill = await session.get(AgentSkill, DEMO_AGENT_SKILL_ID)
    assert skill is not None
    assert skill.name == DEMO_AGENT_SKILL_NAME
    assert skill.tenant_id == TENANT_ID
    assert skill.repo_url == "https://github.com/kaitoy/a2flow"
    assert skill.repo_path == "sample_skills/aws-ec2-launch"
    assert skill.repo_auth_password is None
    # Cloning is the caller's job, so the row starts out unpublished.
    assert skill.sync_status is SkillSyncStatus.pending
    assert skill.commit_sha is None


async def test_seeding_without_the_default_tenant_is_skipped(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("DEMO_DATA", "true")
    mem_engine = await _fresh_engine(with_default_tenant=False)
    try:
        with caplog.at_level(logging.WARNING, logger=_DEMO_LOGGER):
            assert await _sync(mem_engine) is None
        assert len(await _demo_users(mem_engine)) == 0
        assert len(await _rows(mem_engine, Secret)) == 0
    finally:
        await mem_engine.dispose()
    assert "tenant does not exist" in caplog.records[-1].getMessage()


async def test_a_name_collision_is_skipped_without_failing(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An operator's own record under a demo name blocks only that one record."""
    _enable(monkeypatch)
    async with AsyncSession(engine) as session:
        session.add(
            Secret(
                id="operator-secret",
                tenant_id=TENANT_ID,
                name=DEMO_AWS_SECRET_NAME,
                type=SecretType.local,
                entries={"token": "ciphertext"},
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        await session.commit()
    with caplog.at_level(logging.WARNING, logger=_DEMO_LOGGER):
        assert await _sync(engine) == DEMO_AGENT_SKILL_ID
    async with AsyncSession(engine) as session:
        assert await session.get(Secret, DEMO_AWS_SECRET_ID) is None
        assert await session.get(MCPServer, DEMO_MCP_SERVER_ID) is not None
    assert any("conflicts with an existing" in r.getMessage() for r in caplog.records)
    # The AWS tag itself is still created and attached to the MCP server and
    # agent skill; only the link to the missing secret is skipped.
    assert await _rows(engine, SecretTag) == []
    mcp_server_tags = {
        (row.resource_id, row.tag_id) for row in await _rows(engine, McpServerTag)
    }
    assert mcp_server_tags == {(DEMO_MCP_SERVER_ID, DEMO_AWS_TAG_ID)}


# ---------- removal ----------


async def test_disabling_removes_the_full_dataset(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    await _sync(engine)
    _disable(monkeypatch)
    assert await _sync(engine) is None
    assert await _demo_users(engine) == []
    assert await _rows(engine, Secret) == []
    assert await _rows(engine, MCPServer) == []
    assert await _rows(engine, AgentSkill) == []
    assert await _rows(engine, Tag) == []
    assert await _rows(engine, SecretTag) == []
    assert await _rows(engine, McpServerTag) == []
    assert await _rows(engine, AgentSkillTag) == []


async def test_removal_on_a_database_without_demo_data_is_a_noop(
    engine: AsyncEngine,
) -> None:
    assert await _sync(engine) is None
    assert await _demo_users(engine) == []


async def test_removal_is_idempotent(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    await _sync(engine)
    _disable(monkeypatch)
    await _sync(engine)
    await _sync(engine)
    assert await _demo_users(engine) == []


async def test_removal_leaves_non_demo_records_untouched(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    await _sync(engine)
    async with AsyncSession(engine) as session:
        session.add(
            Secret(
                id="operator-secret",
                tenant_id=TENANT_ID,
                name="operator-token",
                type=SecretType.local,
                value="ciphertext",
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        session.add(
            User(
                id="operator-user",
                username="operator",
                first_name="Ops",
                last_name="User",
                password="hash",
                email="operator@localhost",
                roles=[Role.admin.value],
                tenant_id=TENANT_ID,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        await session.commit()
    _disable(monkeypatch)
    await _sync(engine)
    async with AsyncSession(engine) as session:
        assert await session.get(Secret, "operator-secret") is not None
        assert await session.get(User, "operator-user") is not None


async def test_removal_soft_deletes_a_referenced_demo_user(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A demo user who has created records survives as a soft-deleted row."""
    _enable(monkeypatch)
    await _sync(engine)
    async with AsyncSession(engine) as session:
        session.add(
            Tenant(
                id="owned-tenant",
                display_name="Owned",
                name="owned",
                enabled=True,
                created_by=DEMO_APPROVER_USER_ID,
                updated_by=DEMO_APPROVER_USER_ID,
            )
        )
        await session.commit()
    _disable(monkeypatch)
    await _sync(engine)
    async with AsyncSession(engine) as session:
        approver = await session.get(User, DEMO_APPROVER_USER_ID)
        requester = await session.get(User, DEMO_REQUESTER_USER_ID)
    assert approver is not None
    assert approver.deleted_at is not None
    assert approver.enabled is False
    # The unreferenced account is still deleted outright.
    assert requester is None


async def test_reenabling_revives_a_soft_deleted_demo_user(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    await _sync(engine)
    async with AsyncSession(engine) as session:
        session.add(
            Tenant(
                id="owned-tenant",
                display_name="Owned",
                name="owned",
                enabled=True,
                created_by=DEMO_APPROVER_USER_ID,
                updated_by=DEMO_APPROVER_USER_ID,
            )
        )
        await session.commit()
    _disable(monkeypatch)
    await _sync(engine)
    _enable(monkeypatch)
    await _sync(engine)
    async with AsyncSession(engine) as session:
        approver = await session.get(User, DEMO_APPROVER_USER_ID)
    assert approver is not None
    assert approver.deleted_at is None
    assert approver.enabled is True


async def test_removal_keeps_a_referenced_demo_skill(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A workflow built on the demo skill blocks its deletion without failing."""
    from models.workflow import Workflow

    _enable(monkeypatch)
    await _sync(engine)
    async with AsyncSession(engine) as session:
        session.add(
            Workflow(
                id="operator-workflow",
                tenant_id=TENANT_ID,
                name="Launch EC2",
                agent_skill_id=DEMO_AGENT_SKILL_ID,
                session_id="operator-workflow-design",
                agent_skill_commit_sha="a" * 40,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        await session.commit()
    _disable(monkeypatch)
    await _sync(engine)
    async with AsyncSession(engine) as session:
        assert await session.get(AgentSkill, DEMO_AGENT_SKILL_ID) is not None
        # Everything not blocked is still removed.
        assert await session.get(MCPServer, DEMO_MCP_SERVER_ID) is None
