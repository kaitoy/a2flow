"""Tests for the optional demo dataset in ``infrastructure.demo_data``.

Covers both directions: loading registers every missing demo record in the
tenant (idempotently, and returning the agent skill's id exactly once so its
clone is scheduled only on first registration); clearing removes every demo
record again, tolerating records that other data has come to reference. Most
tests load into the ``Default`` tenant, which keeps the legacy fixed ids the
``DEMO_*_ID`` constants name; the multi-tenant tests near the end load into a
second tenant too.
"""

import logging
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import col, select
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
    DEMO_AWS_DEVELOPER_USER_ID,
    DEMO_AWS_GROUP_ID,
    DEMO_AWS_REQUESTER_USER_ID,
    DEMO_AWS_REVIEWER_USER_ID,
    DEMO_AWS_SECRET_ID,
    DEMO_AWS_SECRET_NAME,
    DEMO_AWS_TAG_ID,
    DEMO_AWS_TAG_NAME,
    DEMO_AZURE_CLIENT_ID_ENTRY_KEY,
    DEMO_AZURE_CLIENT_SECRET_ENTRY_KEY,
    DEMO_AZURE_DEVELOPER_USER_ID,
    DEMO_AZURE_GROUP_ID,
    DEMO_AZURE_MCP_SERVER_ID,
    DEMO_AZURE_MCP_SERVER_NAME,
    DEMO_AZURE_REQUESTER_USER_ID,
    DEMO_AZURE_REVIEWER_USER_ID,
    DEMO_AZURE_SECRET_ID,
    DEMO_AZURE_SECRET_NAME,
    DEMO_AZURE_SKILL_ID,
    DEMO_AZURE_SKILL_NAME,
    DEMO_AZURE_TAG_ID,
    DEMO_AZURE_TAG_NAME,
    DEMO_AZURE_TENANT_ENTRY_KEY,
    DEMO_CALL_AWS_MOCK_ID,
    DEMO_COST_ESTIMATOR_MCP_SERVER_ID,
    DEMO_COST_ESTIMATOR_MCP_SERVER_NAME,
    DEMO_DELETE_POD_MOCK_ID,
    DEMO_DEVELOPERS_GROUP_ID,
    DEMO_GCP_CREDENTIALS_ENTRY_KEY,
    DEMO_GCP_DEVELOPER_USER_ID,
    DEMO_GCP_GROUP_ID,
    DEMO_GCP_REQUESTER_USER_ID,
    DEMO_GCP_REVIEWER_USER_ID,
    DEMO_GCP_SECRET_ID,
    DEMO_GCP_SECRET_NAME,
    DEMO_GCP_TAG_ID,
    DEMO_GCP_TAG_NAME,
    DEMO_GKE_MCP_SERVER_ID,
    DEMO_GKE_MCP_SERVER_NAME,
    DEMO_GKE_SKILL_ID,
    DEMO_GKE_SKILL_NAME,
    DEMO_K8S_TOOLKIT_MCP_SERVER_ID,
    DEMO_K8S_TOOLKIT_MCP_SERVER_NAME,
    DEMO_MCP_SERVER_ID,
    DEMO_MCP_SERVER_NAME,
    DEMO_PATCH_WORKLOAD_MOCK_ID,
    DEMO_PRICING_FILE_NAME,
    DEMO_PRICING_KB_ID,
    DEMO_PRICING_KB_NAME,
    DEMO_PRICING_SOURCE_ID,
    DEMO_REQUEST_APPROVAL_MOCK_ID,
    DEMO_REQUESTERS_GROUP_ID,
    DEMO_REVIEWERS_GROUP_ID,
    DEMO_RUN_SCRIPT_MOCK_ID,
    DEMO_SECRET_CREATE_MOCK_ID,
    DEMO_SECRET_GENERATOR_MCP_SERVER_ID,
    DEMO_SECRET_GENERATOR_MCP_SERVER_NAME,
    DEMO_SECRET_KEY_ENTRY_KEY,
    DEMO_SECRET_LIST_MOCK_ID,
    clear_demo_data,
    has_demo_data,
    load_demo_data,
)
from infrastructure.password import verify_password
from models.agent_skill import AgentSkill, SkillSyncStatus
from models.approval import Approval
from models.knowledge import (
    KnowledgeBase,
    KnowledgeSource,
    KnowledgeSourceKind,
    KnowledgeSourceStatus,
)
from models.mcp_server import (
    McpCommand,
    MCPServer,
    McpTransport,
    ScriptLanguage,
    lint_python_script,
)
from models.mcp_tool_mock import MCPToolMock
from models.secret import Secret, SecretType
from models.tag import (
    AgentSkillTag,
    KnowledgeBaseTag,
    McpServerTag,
    McpToolMockTag,
    SecretTag,
    Tag,
    UserGroupTag,
)
from models.tenant import Tenant
from models.user import SYSTEM_USER_ID, Role, User
from models.user_group import UserGroup, UserGroupMember
from models.workflow import Workflow, WorkflowStatus
from models.workflow_execution import WorkflowExecution
from models.workflow_task import WorkflowTask
from repositories.effective_roles import SqlEffectiveRoleRepository
from repositories.metrics import SqlMetricsRepository
from repositories.outbound_email import SqlOutboundEmailRepository
from services.metrics import MetricsService
from tests._engine import make_test_engine
from tests._seed import tenant_cipher

#: Fixed id of the ``Default`` tenant the fixture seeds, so tests can assert on
#: the ``tenant_id`` the demo records land in without re-querying it.
TENANT_ID = "tenant-default"

#: Id (and name) of the second, non-``Default`` tenant the multi-tenant tests
#: add with :func:`_add_tenant`.
OTHER_TENANT_ID = "tenant-acme"

_DEMO_LOGGER = "infrastructure.demo_data"


async def _fresh_engine(*, with_default_tenant: bool = True) -> AsyncEngine:
    """Create a throwaway engine with the schema and system user seeded.

    Args:
        with_default_tenant: Whether to also insert the seeded ``Default``
            tenant the demo records hang off.

    Returns:
        The prepared engine.
    """
    mem_engine = await make_test_engine()
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
    """Start every test from a clean, fully unset demo configuration.

    Every ``DEMO_*`` variable a test in this module sets is listed here, so an
    ambient value (a developer's shell, CI) or one left by an earlier test that
    skipped its teardown cannot bleed into the next test's :func:`_load`.
    """
    for name in (
        "DEMO_AWS_ACCESS_KEY_ID",
        "DEMO_AWS_SECRET_ACCESS_KEY",
        "DEMO_GCP_CREDENTIALS_JSON",
        "DEMO_AZURE_TENANT_ID",
        "DEMO_AZURE_CLIENT_ID",
        "DEMO_AZURE_CLIENT_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)


async def _load(engine: AsyncEngine, tenant_id: str = TENANT_ID) -> list[str]:
    """Run :func:`load_demo_data` on a session of its own, as one request would.

    Clears the memoized ``Settings`` singleton first, so a ``DEMO_*``
    credential a test sets is the one the load reads.

    Args:
        engine: Engine to open the session on.
        tenant_id: Tenant to load the dataset into; ``Default`` by default.

    Returns:
        Whatever :func:`load_demo_data` returned.
    """
    get_settings.cache_clear()
    async with AsyncSession(engine) as session:
        return await load_demo_data(session, tenant_id)


async def _clear(engine: AsyncEngine, tenant_id: str = TENANT_ID) -> int:
    """Run :func:`clear_demo_data` on a session of its own, as one request would.

    Args:
        engine: Engine to open the session on.
        tenant_id: Tenant to clear the dataset from; ``Default`` by default.

    Returns:
        Whatever :func:`clear_demo_data` returned.
    """
    async with AsyncSession(engine) as session:
        return await clear_demo_data(session, tenant_id)


async def _has(engine: AsyncEngine, tenant_id: str = TENANT_ID) -> bool:
    """Run :func:`has_demo_data` on a session of its own."""
    async with AsyncSession(engine) as session:
        return await has_demo_data(session, tenant_id)


async def _add_tenant(engine: AsyncEngine, tenant_id: str = OTHER_TENANT_ID) -> None:
    """Insert a second, non-``Default`` tenant.

    Args:
        engine: Engine to open the session on.
        tenant_id: Id of the tenant, also used as its name.
    """
    async with AsyncSession(engine) as session:
        session.add(
            Tenant(
                id=tenant_id,
                display_name="Acme",
                name=tenant_id,
                enabled=True,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        await session.commit()


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


async def test_load_demo_data_seeds_the_full_dataset(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    assert len(await _demo_users(engine)) == 11
    assert len(await _rows(engine, Secret)) == 3
    assert len(await _rows(engine, MCPServer)) == 6
    assert len(await _rows(engine, MCPToolMock)) == 7
    assert len(await _rows(engine, AgentSkill)) == 3
    assert len(await _rows(engine, Tag)) == 4
    assert len(await _rows(engine, UserGroup)) == 7
    assert len(await _rows(engine, KnowledgeBase)) == 1
    assert len(await _rows(engine, KnowledgeSource)) == 1
    assert len(await _rows(engine, Workflow)) == 4


async def test_load_demo_data_returns_the_new_skill_ids(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The caller schedules the clones, so every skill id comes back on first seed."""
    assert set(await _load(engine)) == {
        DEMO_AGENT_SKILL_ID,
        DEMO_GKE_SKILL_ID,
        DEMO_AZURE_SKILL_ID,
    }


async def test_load_demo_data_returns_no_skill_ids_on_a_second_run(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Loading again must not re-clone skills that are already registered."""
    await _load(engine)
    assert await _load(engine) == []


async def test_load_demo_data_is_idempotent(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    await _load(engine)
    assert len(await _demo_users(engine)) == 11
    assert len(await _rows(engine, Secret)) == 3
    assert len(await _rows(engine, MCPServer)) == 6
    assert len(await _rows(engine, MCPToolMock)) == 7
    assert len(await _rows(engine, AgentSkill)) == 3
    assert len(await _rows(engine, Tag)) == 4
    assert len(await _rows(engine, UserGroup)) == 7
    assert len(await _rows(engine, KnowledgeBase)) == 1
    assert len(await _rows(engine, KnowledgeSource)) == 1
    assert len(await _rows(engine, SecretTag)) == 3
    assert len(await _rows(engine, McpServerTag)) == 6
    assert len(await _rows(engine, AgentSkillTag)) == 6
    assert len(await _rows(engine, McpToolMockTag)) == 6
    assert len(await _rows(engine, UserGroupTag)) == 6
    assert len(await _rows(engine, KnowledgeBaseTag)) == 1


async def test_demo_tags_classify_records_across_six_taggable_kinds(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    tags = {tag.id: tag for tag in await _rows(engine, Tag)}
    assert set(tags) == {
        DEMO_AWS_TAG_ID,
        DEMO_GCP_TAG_ID,
        DEMO_AZURE_TAG_ID,
        DEMO_APPROVAL_TAG_ID,
    }
    assert tags[DEMO_AWS_TAG_ID].name == DEMO_AWS_TAG_NAME
    assert tags[DEMO_GCP_TAG_ID].name == DEMO_GCP_TAG_NAME
    assert tags[DEMO_AZURE_TAG_ID].name == DEMO_AZURE_TAG_NAME
    assert tags[DEMO_APPROVAL_TAG_ID].name == DEMO_APPROVAL_TAG_NAME
    secret_tags = {
        (row.resource_id, row.tag_id) for row in await _rows(engine, SecretTag)
    }
    assert secret_tags == {
        (DEMO_AWS_SECRET_ID, DEMO_AWS_TAG_ID),
        (DEMO_GCP_SECRET_ID, DEMO_GCP_TAG_ID),
        (DEMO_AZURE_SECRET_ID, DEMO_AZURE_TAG_ID),
    }
    mcp_server_tags = {
        (row.resource_id, row.tag_id) for row in await _rows(engine, McpServerTag)
    }
    assert mcp_server_tags == {
        (DEMO_MCP_SERVER_ID, DEMO_AWS_TAG_ID),
        (DEMO_GKE_MCP_SERVER_ID, DEMO_GCP_TAG_ID),
        (DEMO_COST_ESTIMATOR_MCP_SERVER_ID, DEMO_AWS_TAG_ID),
        (DEMO_K8S_TOOLKIT_MCP_SERVER_ID, DEMO_GCP_TAG_ID),
        (DEMO_AZURE_MCP_SERVER_ID, DEMO_AZURE_TAG_ID),
        (DEMO_SECRET_GENERATOR_MCP_SERVER_ID, DEMO_AZURE_TAG_ID),
    }
    agent_skill_tags = {
        (row.resource_id, row.tag_id) for row in await _rows(engine, AgentSkillTag)
    }
    assert agent_skill_tags == {
        (DEMO_AGENT_SKILL_ID, DEMO_AWS_TAG_ID),
        (DEMO_AGENT_SKILL_ID, DEMO_APPROVAL_TAG_ID),
        (DEMO_GKE_SKILL_ID, DEMO_GCP_TAG_ID),
        (DEMO_GKE_SKILL_ID, DEMO_APPROVAL_TAG_ID),
        (DEMO_AZURE_SKILL_ID, DEMO_AZURE_TAG_ID),
        (DEMO_AZURE_SKILL_ID, DEMO_APPROVAL_TAG_ID),
    }
    tool_mock_tags = {
        (row.resource_id, row.tag_id) for row in await _rows(engine, McpToolMockTag)
    }
    assert tool_mock_tags == {
        (DEMO_CALL_AWS_MOCK_ID, DEMO_AWS_TAG_ID),
        (DEMO_RUN_SCRIPT_MOCK_ID, DEMO_AWS_TAG_ID),
        (DEMO_PATCH_WORKLOAD_MOCK_ID, DEMO_GCP_TAG_ID),
        (DEMO_DELETE_POD_MOCK_ID, DEMO_GCP_TAG_ID),
        (DEMO_SECRET_CREATE_MOCK_ID, DEMO_AZURE_TAG_ID),
        (DEMO_SECRET_LIST_MOCK_ID, DEMO_AZURE_TAG_ID),
    }
    knowledge_base_tags = {
        (row.resource_id, row.tag_id) for row in await _rows(engine, KnowledgeBaseTag)
    }
    assert knowledge_base_tags == {(DEMO_PRICING_KB_ID, DEMO_AWS_TAG_ID)}


async def test_demo_knowledge_base_holds_the_price_sheet_unread(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The PDF is registered but not ingested: the walkthrough reads it."""
    await _load(engine)
    async with AsyncSession(engine) as session:
        kb = await session.get(KnowledgeBase, DEMO_PRICING_KB_ID)
        source = await session.get(KnowledgeSource, DEMO_PRICING_SOURCE_ID)
    assert kb is not None
    assert kb.name == DEMO_PRICING_KB_NAME
    assert source is not None
    assert source.knowledge_base_id == DEMO_PRICING_KB_ID
    assert source.kind is KnowledgeSourceKind.file
    assert source.file_name == DEMO_PRICING_FILE_NAME
    assert source.content_type == "application/pdf"
    assert source.status is KnowledgeSourceStatus.unread
    assert source.data is not None
    assert source.data.startswith(b"%PDF")
    assert source.size_bytes == len(source.data)


async def test_a_deleted_demo_source_is_registered_again(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    async with AsyncSession(engine) as session:
        source = await session.get(KnowledgeSource, DEMO_PRICING_SOURCE_ID)
        await session.delete(source)
        await session.commit()
    await _load(engine)
    assert len(await _rows(engine, KnowledgeSource)) == 1


async def test_demo_users_hold_no_direct_roles(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    users = {user.id: user for user in await _demo_users(engine)}
    assert {user_id: user.username for user_id, user in users.items()} == {
        DEMO_APPROVER_USER_ID: "demo-approver-1",
        DEMO_APPROVER_2_USER_ID: "demo-approver-2",
        DEMO_AWS_DEVELOPER_USER_ID: "demo-aws-developer",
        DEMO_AWS_REQUESTER_USER_ID: "demo-aws-requester",
        DEMO_AWS_REVIEWER_USER_ID: "demo-aws-reviewer",
        DEMO_GCP_DEVELOPER_USER_ID: "demo-gcp-developer",
        DEMO_GCP_REQUESTER_USER_ID: "demo-gcp-requester",
        DEMO_GCP_REVIEWER_USER_ID: "demo-gcp-reviewer",
        DEMO_AZURE_DEVELOPER_USER_ID: "demo-azure-developer",
        DEMO_AZURE_REQUESTER_USER_ID: "demo-azure-requester",
        DEMO_AZURE_REVIEWER_USER_ID: "demo-azure-reviewer",
    }
    for user in users.values():
        assert user.roles == []
        assert user.tenant_id == TENANT_ID
        assert user.enabled is True
        assert user.created_by == SYSTEM_USER_ID


async def test_demo_groups_grant_the_approver_requester_developer_and_reviewer_roles(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    groups = {group.id: group for group in await _rows(engine, UserGroup)}
    assert len(groups) == 7
    expected: dict[str, tuple[str, Role | None]] = {
        DEMO_APPROVERS_GROUP_ID: ("Demo Approvers", Role.approver),
        DEMO_REQUESTERS_GROUP_ID: ("Demo Requesters", Role.requester),
        DEMO_DEVELOPERS_GROUP_ID: ("Demo Developers", Role.developer),
        DEMO_REVIEWERS_GROUP_ID: ("Demo Reviewers", Role.reviewer),
        DEMO_AWS_GROUP_ID: ("Demo AWS Group", None),
        DEMO_GCP_GROUP_ID: ("Demo GCP Group", None),
        DEMO_AZURE_GROUP_ID: ("Demo Azure Group", None),
    }
    for group_id, (name, role) in expected.items():
        group = groups[group_id]
        assert group.name == name
        assert group.roles == ([role.value] if role is not None else [])
        assert group.tenant_id == TENANT_ID
        assert group.created_by == SYSTEM_USER_ID


async def test_demo_groups_hold_their_expected_members(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    members = {
        (row.group_id, row.user_id) for row in await _rows(engine, UserGroupMember)
    }
    assert members == {
        (DEMO_APPROVERS_GROUP_ID, DEMO_APPROVER_USER_ID),
        (DEMO_APPROVERS_GROUP_ID, DEMO_APPROVER_2_USER_ID),
        (DEMO_REQUESTERS_GROUP_ID, DEMO_AWS_REQUESTER_USER_ID),
        (DEMO_REQUESTERS_GROUP_ID, DEMO_GCP_REQUESTER_USER_ID),
        (DEMO_REQUESTERS_GROUP_ID, DEMO_AZURE_REQUESTER_USER_ID),
        (DEMO_DEVELOPERS_GROUP_ID, DEMO_AWS_DEVELOPER_USER_ID),
        (DEMO_DEVELOPERS_GROUP_ID, DEMO_GCP_DEVELOPER_USER_ID),
        (DEMO_DEVELOPERS_GROUP_ID, DEMO_AZURE_DEVELOPER_USER_ID),
        (DEMO_REVIEWERS_GROUP_ID, DEMO_AWS_REVIEWER_USER_ID),
        (DEMO_REVIEWERS_GROUP_ID, DEMO_GCP_REVIEWER_USER_ID),
        (DEMO_REVIEWERS_GROUP_ID, DEMO_AZURE_REVIEWER_USER_ID),
        (DEMO_AWS_GROUP_ID, DEMO_AWS_DEVELOPER_USER_ID),
        (DEMO_AWS_GROUP_ID, DEMO_AWS_REQUESTER_USER_ID),
        (DEMO_AWS_GROUP_ID, DEMO_AWS_REVIEWER_USER_ID),
        (DEMO_GCP_GROUP_ID, DEMO_GCP_DEVELOPER_USER_ID),
        (DEMO_GCP_GROUP_ID, DEMO_GCP_REQUESTER_USER_ID),
        (DEMO_GCP_GROUP_ID, DEMO_GCP_REVIEWER_USER_ID),
        (DEMO_AZURE_GROUP_ID, DEMO_AZURE_DEVELOPER_USER_ID),
        (DEMO_AZURE_GROUP_ID, DEMO_AZURE_REQUESTER_USER_ID),
        (DEMO_AZURE_GROUP_ID, DEMO_AZURE_REVIEWER_USER_ID),
    }


async def test_demo_users_effective_roles_come_from_their_group(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    async with AsyncSession(engine) as session:
        inherited = await SqlEffectiveRoleRepository(session).group_roles_for_users(
            [
                DEMO_APPROVER_USER_ID,
                DEMO_APPROVER_2_USER_ID,
                DEMO_AWS_REQUESTER_USER_ID,
                DEMO_GCP_REQUESTER_USER_ID,
                DEMO_AWS_DEVELOPER_USER_ID,
                DEMO_GCP_DEVELOPER_USER_ID,
                DEMO_AWS_REVIEWER_USER_ID,
                DEMO_GCP_REVIEWER_USER_ID,
                DEMO_AZURE_REQUESTER_USER_ID,
                DEMO_AZURE_DEVELOPER_USER_ID,
                DEMO_AZURE_REVIEWER_USER_ID,
            ]
        )
    assert inherited == {
        DEMO_APPROVER_USER_ID: frozenset({Role.approver.value}),
        DEMO_APPROVER_2_USER_ID: frozenset({Role.approver.value}),
        DEMO_AWS_REQUESTER_USER_ID: frozenset({Role.requester.value}),
        DEMO_GCP_REQUESTER_USER_ID: frozenset({Role.requester.value}),
        DEMO_AWS_DEVELOPER_USER_ID: frozenset({Role.developer.value}),
        DEMO_GCP_DEVELOPER_USER_ID: frozenset({Role.developer.value}),
        DEMO_AWS_REVIEWER_USER_ID: frozenset({Role.reviewer.value}),
        DEMO_GCP_REVIEWER_USER_ID: frozenset({Role.reviewer.value}),
        DEMO_AZURE_REQUESTER_USER_ID: frozenset({Role.requester.value}),
        DEMO_AZURE_DEVELOPER_USER_ID: frozenset({Role.developer.value}),
        DEMO_AZURE_REVIEWER_USER_ID: frozenset({Role.reviewer.value}),
    }


async def test_demo_provider_tags_are_access_control(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    tags = {tag.id: tag for tag in await _rows(engine, Tag)}
    assert tags[DEMO_AWS_TAG_ID].access_control is True
    assert tags[DEMO_GCP_TAG_ID].access_control is True
    assert tags[DEMO_AZURE_TAG_ID].access_control is True
    assert tags[DEMO_APPROVAL_TAG_ID].access_control is False


async def test_demo_access_control_tag_groups_hold_their_tags(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each provider group holds its matching tag; Demo Approvers holds all
    three, so either demo approver is an eligible destination regardless of
    which demo skill's workflow requested the approval."""
    await _load(engine)
    group_tags = {
        (row.resource_id, row.tag_id) for row in await _rows(engine, UserGroupTag)
    }
    assert group_tags == {
        (DEMO_AWS_GROUP_ID, DEMO_AWS_TAG_ID),
        (DEMO_GCP_GROUP_ID, DEMO_GCP_TAG_ID),
        (DEMO_APPROVERS_GROUP_ID, DEMO_AWS_TAG_ID),
        (DEMO_APPROVERS_GROUP_ID, DEMO_GCP_TAG_ID),
        (DEMO_AZURE_GROUP_ID, DEMO_AZURE_TAG_ID),
        (DEMO_APPROVERS_GROUP_ID, DEMO_AZURE_TAG_ID),
    }


async def test_reviving_an_older_demo_tag_gains_access_control(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tag seeded before this module made AWS/GCP access-control picks it up."""
    await _load(engine)
    async with AsyncSession(engine) as session:
        legacy = await session.get(Tag, DEMO_AWS_TAG_ID)
        assert legacy is not None
        legacy.access_control = False
        session.add(legacy)
        await session.commit()

    await _load(engine)

    async with AsyncSession(engine) as session:
        migrated = await session.get(Tag, DEMO_AWS_TAG_ID)
        assert migrated is not None
        assert migrated.access_control is True


async def test_reviving_renames_an_older_demo_username(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A user seeded under this module's previous generic username is renamed."""
    async with AsyncSession(engine) as session:
        session.add(
            User(
                id=DEMO_AWS_DEVELOPER_USER_ID,
                username="demo-developer",
                first_name="Carol",
                last_name="Bennett",
                password="hash",
                email="demo-developer@example.com",
                roles=[],
                tenant_id=TENANT_ID,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        await session.commit()

    await _load(engine)

    async with AsyncSession(engine) as session:
        migrated = await session.get(User, DEMO_AWS_DEVELOPER_USER_ID)
        assert migrated is not None
        assert migrated.username == "demo-aws-developer"


async def test_reviving_an_older_demo_user_strips_its_direct_roles(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A database seeded before groups existed migrates to pure inheritance."""
    await _load(engine)
    async with AsyncSession(engine) as session:
        legacy = await session.get(User, DEMO_APPROVER_USER_ID)
        assert legacy is not None
        legacy.roles = [Role.approver.value]
        session.add(legacy)
        await session.commit()

    await _load(engine)

    async with AsyncSession(engine) as session:
        migrated = await session.get(User, DEMO_APPROVER_USER_ID)
        assert migrated is not None
        assert migrated.roles == []


async def test_removing_demo_data_deletes_the_groups(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    await _clear(engine)
    assert await _rows(engine, UserGroup) == []
    assert await _rows(engine, UserGroupMember) == []


async def test_demo_users_get_their_own_unlogged_random_passwords(
    engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    """Nobody can sign in as a demo user: no password is shared or logged."""
    with caplog.at_level(logging.DEBUG, logger="infrastructure"):
        await _load(engine)
    users = await _demo_users(engine)
    assert len({user.password for user in users}) == len(users)
    for user in users:
        assert not verify_password(user.username, user.password)
    assert not any(
        "password" in r.getMessage().lower()
        for r in caplog.records
        if r.name.startswith("infrastructure")
    )


async def test_demo_secrets_store_the_configured_values_encrypted(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_AWS_ACCESS_KEY_ID", "AKIAEXAMPLE")
    monkeypatch.setenv("DEMO_AWS_SECRET_ACCESS_KEY", "s3cr3t-key")
    await _load(engine)
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
    cipher = await tenant_cipher(engine, TENANT_ID)
    assert cipher.decrypt(access_key) == "AKIAEXAMPLE"
    assert cipher.decrypt(secret.entries[DEMO_SECRET_KEY_ENTRY_KEY]) == "s3cr3t-key"


async def test_demo_secrets_fall_back_to_a_placeholder(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    async with AsyncSession(engine) as session:
        secret = await session.get(Secret, DEMO_AWS_SECRET_ID)
    assert secret is not None
    decrypted = (await tenant_cipher(engine, TENANT_ID)).decrypt(
        secret.entries[DEMO_ACCESS_KEY_ENTRY_KEY]
    )
    assert decrypted == "REPLACE_ME"


async def test_a_reload_with_every_demo_secret_seeded_needs_no_data_key(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A data key that no longer unwraps must not fail a load over secrets that exist."""
    await _load(engine)
    async with AsyncSession(engine) as session:
        tenant = await session.get(Tenant, TENANT_ID)
        assert tenant is not None
        tenant.data_key = "not-under-the-master-key"
        session.add(tenant)
        await session.commit()

    await _load(engine)


async def test_demo_gcp_secret_stores_the_configured_credential_encrypted(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    credential = '{"type": "service_account", "client_email": "demo@example"}'
    monkeypatch.setenv("DEMO_GCP_CREDENTIALS_JSON", credential)
    await _load(engine)
    async with AsyncSession(engine) as session:
        secret = await session.get(Secret, DEMO_GCP_SECRET_ID)
    assert secret is not None
    assert secret.name == DEMO_GCP_SECRET_NAME
    assert secret.description
    assert secret.type is SecretType.local
    assert secret.tenant_id == TENANT_ID
    assert sorted(secret.entries) == [DEMO_GCP_CREDENTIALS_ENTRY_KEY]
    ciphertext = secret.entries[DEMO_GCP_CREDENTIALS_ENTRY_KEY]
    assert ciphertext != credential  # stored as ciphertext
    assert (await tenant_cipher(engine, TENANT_ID)).decrypt(ciphertext) == credential


async def test_demo_gcp_secret_falls_back_to_a_placeholder(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    async with AsyncSession(engine) as session:
        secret = await session.get(Secret, DEMO_GCP_SECRET_ID)
    assert secret is not None
    decrypted = (await tenant_cipher(engine, TENANT_ID)).decrypt(
        secret.entries[DEMO_GCP_CREDENTIALS_ENTRY_KEY]
    )
    assert decrypted == "REPLACE_ME"


async def test_demo_mcp_server_proxies_the_managed_aws_server(
    engine: AsyncEngine,
) -> None:
    await _load(engine)
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
        "AWS_REGION": "us-east-1",
    }


async def test_demo_cost_estimator_is_a_python_script_server_on_the_aws_secret(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    async with AsyncSession(engine) as session:
        server = await session.get(MCPServer, DEMO_COST_ESTIMATOR_MCP_SERVER_ID)
    assert server is not None
    assert server.name == DEMO_COST_ESTIMATOR_MCP_SERVER_NAME
    assert server.description
    assert server.tenant_id == TENANT_ID
    assert server.transport is McpTransport.script
    assert server.language is ScriptLanguage.python
    assert server.packages == ["boto3==1.43.103"]
    assert server.source is not None
    assert "get_products" in server.source
    # The editor's Python lint must be clean, so the demo shows no warnings.
    assert lint_python_script(server.source, server.packages) == []
    assert server.env == {
        "AWS_ACCESS_KEY_ID": (
            f"${{secret:{DEMO_AWS_SECRET_NAME}/{DEMO_ACCESS_KEY_ENTRY_KEY}}}"
        ),
        "AWS_SECRET_ACCESS_KEY": (
            f"${{secret:{DEMO_AWS_SECRET_NAME}/{DEMO_SECRET_KEY_ENTRY_KEY}}}"
        ),
        "AWS_REGION": "us-east-1",
    }


async def test_demo_k8s_toolkit_is_a_javascript_script_server(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    async with AsyncSession(engine) as session:
        server = await session.get(MCPServer, DEMO_K8S_TOOLKIT_MCP_SERVER_ID)
    assert server is not None
    assert server.name == DEMO_K8S_TOOLKIT_MCP_SERVER_NAME
    assert server.description
    assert server.transport is McpTransport.script
    assert server.language is ScriptLanguage.javascript
    assert server.packages == ["js-yaml@5.4.2"]
    assert server.source is not None
    assert "export function validate_manifest" in server.source
    assert "export function build_restart_patch" in server.source
    assert server.env == {}


async def test_demo_gke_mcp_server_uses_a_gcp_token_bearer_header(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    async with AsyncSession(engine) as session:
        server = await session.get(MCPServer, DEMO_GKE_MCP_SERVER_ID)
    assert server is not None
    assert server.name == DEMO_GKE_MCP_SERVER_NAME
    assert server.description
    assert server.tenant_id == TENANT_ID
    assert server.transport is McpTransport.streamable_http
    assert server.url == "https://container.googleapis.com/mcp"
    assert server.command is None
    assert server.args == []
    assert server.env == {}
    assert server.headers == {
        "Authorization": (
            "Bearer "
            f"${{gcp-token:{DEMO_GCP_SECRET_NAME}/{DEMO_GCP_CREDENTIALS_ENTRY_KEY}}}"
        )
    }


async def test_demo_agent_skill_points_at_the_sample_skill(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
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


async def test_demo_gke_agent_skill_points_at_the_sample_skill(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    async with AsyncSession(engine) as session:
        skill = await session.get(AgentSkill, DEMO_GKE_SKILL_ID)
    assert skill is not None
    assert skill.name == DEMO_GKE_SKILL_NAME
    assert skill.tenant_id == TENANT_ID
    assert skill.repo_url == "https://github.com/kaitoy/a2flow"
    assert skill.repo_path == "sample_skills/gke-pod-restart"
    assert skill.repo_auth_password is None
    # Cloning is the caller's job, so the row starts out unpublished.
    assert skill.sync_status is SkillSyncStatus.pending
    assert skill.commit_sha is None


async def test_demo_azure_secret_stores_the_configured_principal_encrypted(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_AZURE_TENANT_ID", "tenant-guid")
    monkeypatch.setenv("DEMO_AZURE_CLIENT_ID", "client-guid")
    monkeypatch.setenv("DEMO_AZURE_CLIENT_SECRET", "client-s3cr3t")
    await _load(engine)
    async with AsyncSession(engine) as session:
        secret = await session.get(Secret, DEMO_AZURE_SECRET_ID)
    assert secret is not None
    assert secret.name == DEMO_AZURE_SECRET_NAME
    assert secret.description
    assert secret.type is SecretType.local
    assert secret.tenant_id == TENANT_ID
    cipher = await tenant_cipher(engine, TENANT_ID)
    assert {key: cipher.decrypt(value) for key, value in secret.entries.items()} == {
        DEMO_AZURE_TENANT_ENTRY_KEY: "tenant-guid",
        DEMO_AZURE_CLIENT_ID_ENTRY_KEY: "client-guid",
        DEMO_AZURE_CLIENT_SECRET_ENTRY_KEY: "client-s3cr3t",
    }
    assert secret.entries[DEMO_AZURE_CLIENT_SECRET_ENTRY_KEY] != "client-s3cr3t"


async def test_demo_azure_secret_falls_back_to_a_placeholder(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    async with AsyncSession(engine) as session:
        secret = await session.get(Secret, DEMO_AZURE_SECRET_ID)
    assert secret is not None
    cipher = await tenant_cipher(engine, TENANT_ID)
    assert {cipher.decrypt(value) for value in secret.entries.values()} == {
        "REPLACE_ME"
    }


async def test_demo_azure_mcp_server_launches_the_key_vault_tools_with_npx(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    async with AsyncSession(engine) as session:
        server = await session.get(MCPServer, DEMO_AZURE_MCP_SERVER_ID)
    assert server is not None
    assert server.name == DEMO_AZURE_MCP_SERVER_NAME
    assert server.description
    assert server.tenant_id == TENANT_ID
    assert server.transport is McpTransport.stdio
    assert server.command is McpCommand.npx
    assert server.args == [
        "-y",
        "@azure/mcp@3.0.0-beta.50",
        "server",
        "start",
        "--namespace",
        "keyvault",
        "--mode",
        "all",
    ]
    assert server.url is None
    assert server.headers == {}
    assert server.env == {
        "AZURE_TENANT_ID": (
            f"${{secret:{DEMO_AZURE_SECRET_NAME}/{DEMO_AZURE_TENANT_ENTRY_KEY}}}"
        ),
        "AZURE_CLIENT_ID": (
            f"${{secret:{DEMO_AZURE_SECRET_NAME}/{DEMO_AZURE_CLIENT_ID_ENTRY_KEY}}}"
        ),
        "AZURE_CLIENT_SECRET": (
            f"${{secret:{DEMO_AZURE_SECRET_NAME}/{DEMO_AZURE_CLIENT_SECRET_ENTRY_KEY}}}"
        ),
        "AZURE_TOKEN_CREDENTIALS": "EnvironmentCredential",
    }


async def test_an_older_azure_server_stops_skipping_consent_on_reload(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A row seeded with the retired flag loses it, so the server asks again."""
    await _load(engine)
    async with AsyncSession(engine) as session:
        legacy = await session.get(MCPServer, DEMO_AZURE_MCP_SERVER_ID)
        assert legacy is not None
        legacy.args = [*legacy.args, "--dangerously-disable-elicitation"]
        session.add(legacy)
        await session.commit()

    await _load(engine)

    async with AsyncSession(engine) as session:
        migrated = await session.get(MCPServer, DEMO_AZURE_MCP_SERVER_ID)
    assert migrated is not None
    assert "--dangerously-disable-elicitation" not in migrated.args
    assert migrated.args[-2:] == ["--mode", "all"]


async def test_a_demo_server_under_its_retired_id_is_registered_again(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A server seeded under the old zero-padded id moves to the new one."""
    retired = "00000000-0000-0000-0000-00000000d201"
    await _load(engine)
    # Rebuild what an older version left: the AWS server, and the mocks
    # pointing at it, under the old id.
    async with AsyncSession(engine) as session:
        server = await session.get(MCPServer, DEMO_MCP_SERVER_ID)
        assert server is not None
        mocks = (
            await session.exec(
                select(MCPToolMock).where(
                    col(MCPToolMock.mcp_server_id) == DEMO_MCP_SERVER_ID
                )
            )
        ).all()
        legacy_server = server.model_dump()
        legacy_mocks = [m.model_dump() for m in mocks]
        for mock in mocks:
            await session.delete(mock)
        await session.flush()
        await session.delete(server)
        await session.commit()
        session.add(MCPServer.model_validate({**legacy_server, "id": retired}))
        await session.flush()
        for fields in legacy_mocks:
            session.add(
                MCPToolMock.model_validate({**fields, "mcp_server_id": retired})
            )
        await session.commit()
    async with AsyncSession(engine) as session:
        assert await session.get(MCPServer, retired) is not None

    await _load(engine)

    async with AsyncSession(engine) as session:
        assert await session.get(MCPServer, retired) is None
        assert await session.get(MCPServer, DEMO_MCP_SERVER_ID) is not None
        reseeded = await session.get(MCPToolMock, DEMO_CALL_AWS_MOCK_ID)
    assert reseeded is not None
    assert reseeded.mcp_server_id == DEMO_MCP_SERVER_ID
    assert len(await _rows(engine, MCPServer)) == 6
    assert len(await _rows(engine, MCPToolMock)) == 7


async def test_demo_secret_generator_is_a_javascript_script_server(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    async with AsyncSession(engine) as session:
        server = await session.get(MCPServer, DEMO_SECRET_GENERATOR_MCP_SERVER_ID)
    assert server is not None
    assert server.name == DEMO_SECRET_GENERATOR_MCP_SERVER_NAME
    assert server.description
    assert server.transport is McpTransport.script
    assert server.language is ScriptLanguage.javascript
    assert server.packages == []
    assert server.source is not None
    assert "export function generate_secret_value" in server.source
    assert "generate_secret_value.inputSchema" in server.source
    assert server.env == {}


async def test_demo_azure_agent_skill_points_at_the_sample_skill(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    async with AsyncSession(engine) as session:
        skill = await session.get(AgentSkill, DEMO_AZURE_SKILL_ID)
    assert skill is not None
    assert skill.name == DEMO_AZURE_SKILL_NAME
    assert skill.tenant_id == TENANT_ID
    assert skill.repo_url == "https://github.com/kaitoy/a2flow"
    assert skill.repo_path == "sample_skills/azure-keyvault-secret-rotation"
    assert skill.repo_auth_password is None
    assert skill.sync_status is SkillSyncStatus.pending
    assert skill.commit_sha is None


async def test_a_second_tenant_gets_its_own_copy_under_its_own_ids(
    engine: AsyncEngine,
) -> None:
    await _load(engine)
    await _add_tenant(engine)
    new_skill_ids = await _load(engine, OTHER_TENANT_ID)

    assert len(new_skill_ids) == 3
    assert not set(new_skill_ids) & {
        DEMO_AGENT_SKILL_ID,
        DEMO_GKE_SKILL_ID,
        DEMO_AZURE_SKILL_ID,
    }
    for model in (User, UserGroup, Secret, MCPServer, MCPToolMock, AgentSkill, Tag):
        rows = [r for r in await _rows(engine, model) if r.id != SYSTEM_USER_ID]
        by_tenant = {
            tenant: {r.id for r in rows if r.tenant_id == tenant}
            for tenant in (TENANT_ID, OTHER_TENANT_ID)
        }
        assert by_tenant[TENANT_ID], model
        assert len(by_tenant[TENANT_ID]) == len(by_tenant[OTHER_TENANT_ID]), model
        assert not by_tenant[TENANT_ID] & by_tenant[OTHER_TENANT_ID], model
    async with AsyncSession(engine) as session:
        # The Default tenant keeps the legacy ids the constants name.
        server = await session.get(MCPServer, DEMO_MCP_SERVER_ID)
    assert server is not None and server.tenant_id == TENANT_ID


async def test_a_second_tenants_records_reference_its_own_rows(
    engine: AsyncEngine,
) -> None:
    await _add_tenant(engine)
    await _load(engine, OTHER_TENANT_ID)
    async with AsyncSession(engine) as session:
        ids = {
            model: {r.id for r in (await session.exec(select(model))).all()}
            for model in (User, UserGroup, MCPServer, AgentSkill, Tag)
        }
        for mock in (await session.exec(select(MCPToolMock))).all():
            assert mock.mcp_server_id is None or mock.mcp_server_id in ids[MCPServer]
        for member in (await session.exec(select(UserGroupMember))).all():
            assert member.group_id in ids[UserGroup]
            assert member.user_id in ids[User]
        for link in (await session.exec(select(AgentSkillTag))).all():
            assert link.resource_id in ids[AgentSkill]
            assert link.tag_id in ids[Tag]
        for workflow in (await session.exec(select(Workflow))).all():
            assert workflow.agent_skill_id in ids[AgentSkill]
        executions = (await session.exec(select(WorkflowExecution))).all()
        assert executions
        assert all(e.tenant_id == OTHER_TENANT_ID for e in executions)
        assert all(e.initiator_id in ids[User] for e in executions)
        for approval in (await session.exec(select(Approval))).all():
            assert approval.approver is None or approval.approver in ids[User]
            assert (
                approval.approver_group_id is None
                or approval.approver_group_id in ids[UserGroup]
            )


async def test_only_the_default_tenant_gets_the_configured_credentials(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_AWS_ACCESS_KEY_ID", "AKIAEXAMPLE")
    monkeypatch.setenv("DEMO_GCP_CREDENTIALS_JSON", '{"type":"service_account"}')
    monkeypatch.setenv("DEMO_AZURE_CLIENT_SECRET", "client-s3cr3t")
    await _add_tenant(engine)
    await _load(engine)
    await _load(engine, OTHER_TENANT_ID)

    secrets = await _rows(engine, Secret)
    for tenant_id, expected in (
        (TENANT_ID, {"AKIAEXAMPLE", '{"type":"service_account"}', "client-s3cr3t"}),
        (OTHER_TENANT_ID, set()),
    ):
        cipher = await tenant_cipher(engine, tenant_id)
        values = {
            cipher.decrypt(v)
            for secret in secrets
            if secret.tenant_id == tenant_id
            for v in secret.entries.values()
        }
        assert values - {"REPLACE_ME"} == expected


async def test_clearing_one_tenant_leaves_the_other_untouched(
    engine: AsyncEngine,
) -> None:
    await _add_tenant(engine)
    await _load(engine)
    await _load(engine, OTHER_TENANT_ID)
    before = {
        model: len(await _rows(engine, model))
        for model in (User, Secret, MCPServer, WorkflowExecution)
    }

    assert await _clear(engine, OTHER_TENANT_ID) == 0

    assert not await _has(engine, OTHER_TENANT_ID)
    assert await _has(engine)
    for model in (Secret, MCPServer, WorkflowExecution):
        rows = await _rows(engine, model)
        assert {r.tenant_id for r in rows} == {TENANT_ID}, model
        assert len(rows) * 2 == before[model], model
    assert {u.tenant_id for u in await _demo_users(engine)} == {TENANT_ID}


async def test_has_demo_data_follows_load_and_clear(engine: AsyncEngine) -> None:
    assert not await _has(engine)
    await _load(engine)
    assert await _has(engine)
    await _clear(engine)
    assert not await _has(engine)


async def test_a_name_collision_is_skipped_without_failing(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An operator's own record under a demo name blocks only that one record."""
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
        # Only the AWS secret name collided; every demo skill still registers.
        assert set(await _load(engine)) == {
            DEMO_AGENT_SKILL_ID,
            DEMO_GKE_SKILL_ID,
            DEMO_AZURE_SKILL_ID,
        }
    async with AsyncSession(engine) as session:
        assert await session.get(Secret, DEMO_AWS_SECRET_ID) is None
        assert await session.get(MCPServer, DEMO_MCP_SERVER_ID) is not None
        # Only the AWS secret name collided; the Google Cloud demo records seed.
        assert await session.get(Secret, DEMO_GCP_SECRET_ID) is not None
        assert await session.get(MCPServer, DEMO_GKE_MCP_SERVER_ID) is not None
    assert any("conflicts with an existing" in r.getMessage() for r in caplog.records)
    # The AWS tag itself is still created and attached to the AWS MCP server and
    # agent skill; only the link to the missing AWS secret is skipped. The GCP
    # tag attaches to both of its records unaffected.
    secret_tags = {
        (row.resource_id, row.tag_id) for row in await _rows(engine, SecretTag)
    }
    assert secret_tags == {
        (DEMO_GCP_SECRET_ID, DEMO_GCP_TAG_ID),
        (DEMO_AZURE_SECRET_ID, DEMO_AZURE_TAG_ID),
    }
    mcp_server_tags = {
        (row.resource_id, row.tag_id) for row in await _rows(engine, McpServerTag)
    }
    assert mcp_server_tags == {
        (DEMO_MCP_SERVER_ID, DEMO_AWS_TAG_ID),
        (DEMO_GKE_MCP_SERVER_ID, DEMO_GCP_TAG_ID),
        (DEMO_COST_ESTIMATOR_MCP_SERVER_ID, DEMO_AWS_TAG_ID),
        (DEMO_K8S_TOOLKIT_MCP_SERVER_ID, DEMO_GCP_TAG_ID),
        (DEMO_AZURE_MCP_SERVER_ID, DEMO_AZURE_TAG_ID),
        (DEMO_SECRET_GENERATOR_MCP_SERVER_ID, DEMO_AZURE_TAG_ID),
    }


# ---------- removal ----------


async def test_clearing_removes_the_full_dataset(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    assert await _clear(engine) == 0
    assert await _demo_users(engine) == []
    assert await _rows(engine, Secret) == []
    assert await _rows(engine, MCPServer) == []
    assert await _rows(engine, MCPToolMock) == []
    assert await _rows(engine, AgentSkill) == []
    assert await _rows(engine, Tag) == []
    assert await _rows(engine, UserGroup) == []
    assert await _rows(engine, SecretTag) == []
    assert await _rows(engine, McpServerTag) == []
    assert await _rows(engine, AgentSkillTag) == []
    assert await _rows(engine, McpToolMockTag) == []
    assert await _rows(engine, UserGroupTag) == []
    assert await _rows(engine, KnowledgeBase) == []
    assert await _rows(engine, KnowledgeSource) == []
    assert await _rows(engine, KnowledgeBaseTag) == []
    assert await _rows(engine, Workflow) == []
    assert await _rows(engine, WorkflowExecution) == []
    assert await _rows(engine, WorkflowTask) == []
    assert await _rows(engine, Approval) == []


async def test_clearing_a_tenant_without_demo_data_is_a_noop(
    engine: AsyncEngine,
) -> None:
    assert await _clear(engine) == 0
    assert await _demo_users(engine) == []


async def test_removal_is_idempotent(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    await _clear(engine)
    await _clear(engine)
    assert await _demo_users(engine) == []


async def test_removal_leaves_non_demo_records_untouched(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    async with AsyncSession(engine) as session:
        session.add(
            Secret(
                id="operator-secret",
                tenant_id=TENANT_ID,
                name="operator-token",
                type=SecretType.local,
                entries={"value": "ciphertext"},
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
    await _clear(engine)
    async with AsyncSession(engine) as session:
        assert await session.get(Secret, "operator-secret") is not None
        assert await session.get(User, "operator-user") is not None


async def test_removal_soft_deletes_a_referenced_demo_user(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A demo user who has created records survives as a soft-deleted row."""
    await _load(engine)
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
    await _clear(engine)
    async with AsyncSession(engine) as session:
        approver = await session.get(User, DEMO_APPROVER_USER_ID)
        requester = await session.get(User, DEMO_AWS_REQUESTER_USER_ID)
    assert approver is not None
    assert approver.deleted_at is not None
    assert approver.enabled is False
    # The unreferenced account is still deleted outright.
    assert requester is None


async def test_reloading_revives_a_soft_deleted_demo_user(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
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
    await _clear(engine)
    await _load(engine)
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

    await _load(engine)
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
    await _clear(engine)
    async with AsyncSession(engine) as session:
        assert await session.get(AgentSkill, DEMO_AGENT_SKILL_ID) is not None
        # Everything not blocked is still removed.
        assert await session.get(MCPServer, DEMO_MCP_SERVER_ID) is None


# ---------- tool mocks ----------


async def test_demo_tool_mocks_stub_the_demo_run_tools(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    mocks = {mock.id: mock for mock in await _rows(engine, MCPToolMock)}
    assert set(mocks) == {
        DEMO_CALL_AWS_MOCK_ID,
        DEMO_RUN_SCRIPT_MOCK_ID,
        DEMO_PATCH_WORKLOAD_MOCK_ID,
        DEMO_DELETE_POD_MOCK_ID,
        DEMO_SECRET_CREATE_MOCK_ID,
        DEMO_SECRET_LIST_MOCK_ID,
        DEMO_REQUEST_APPROVAL_MOCK_ID,
    }
    targets = {(mock.mcp_server_id, mock.tool_name) for mock in mocks.values()}
    assert targets == {
        (DEMO_MCP_SERVER_ID, "aws___call_aws"),
        (DEMO_MCP_SERVER_ID, "aws___run_script"),
        (DEMO_GKE_MCP_SERVER_ID, "patch_k8s_resource"),
        (DEMO_GKE_MCP_SERVER_ID, "delete_k8s_resource"),
        (DEMO_AZURE_MCP_SERVER_ID, "keyvault_secret_create"),
        (DEMO_AZURE_MCP_SERVER_ID, "keyvault_secret_get"),
        (None, "request_approval"),
    }
    for mock in mocks.values():
        assert mock.tenant_id == TENANT_ID
        assert mock.created_by == SYSTEM_USER_ID
        assert mock.description
        assert len(mock.responses) == 1
        assert mock.responses[0]["kind"] == "structured"
    approval = mocks[DEMO_REQUEST_APPROVAL_MOCK_ID]
    assert approval.responses[0]["value"] == {"status": "approved"}
    launch = mocks[DEMO_CALL_AWS_MOCK_ID]
    assert launch.responses[0]["value"]["Instances"][0]["InstanceId"].startswith("i-")
    workload_restart = mocks[DEMO_PATCH_WORKLOAD_MOCK_ID]
    assert workload_restart.responses[0]["value"]["status"] == "patched"
    pod_restart = mocks[DEMO_DELETE_POD_MOCK_ID]
    assert pod_restart.responses[0]["value"]["status"] == "deleted"
    rotation = mocks[DEMO_SECRET_CREATE_MOCK_ID]
    # Like the real Azure MCP Server: a write reports when it happened, but no
    # version id.
    assert rotation.responses[0]["value"]["createdOn"]
    assert "version" not in rotation.responses[0]["value"]
    # A mock never carries a secret value, made up or otherwise.
    assert "value" not in rotation.responses[0]["value"]
    listing = mocks[DEMO_SECRET_LIST_MOCK_ID].responses[0]["value"]["secrets"]
    # The real listing is bare names; the secret the write reports is one of them.
    assert all(isinstance(secret, str) for secret in listing)
    assert rotation.responses[0]["value"]["name"] in listing


async def test_clearing_removes_tool_mocks_before_the_mcp_server(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mock's RESTRICT FK on the demo MCP server must not block removal."""
    await _load(engine)
    assert await _clear(engine) == 0
    assert await _rows(engine, MCPToolMock) == []
    assert await _rows(engine, MCPServer) == []


# ---------- workflows and run history ----------


async def _snapshot(engine: AsyncEngine) -> Any:
    """Return the Default tenant's metrics snapshot, as the dashboard reads it."""
    async with AsyncSession(engine) as session:
        service = MetricsService(
            SqlMetricsRepository(session, tenant_id=TENANT_ID),
            SqlOutboundEmailRepository(session, tenant_id=TENANT_ID),
            timezone="UTC",
        )
        return await service.snapshot(threshold_hours=24)


async def test_demo_workflows_are_published(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    workflows = await _rows(engine, Workflow)
    assert {w.status for w in workflows} == {WorkflowStatus.published}
    assert {w.name for w in workflows}.isdisjoint(
        {DEMO_AGENT_SKILL_NAME, DEMO_GKE_SKILL_NAME, DEMO_AZURE_SKILL_NAME}
    )


async def test_demo_run_history_fills_every_dashboard_kpi(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _load(engine)
    snapshot = await _snapshot(engine)
    assert snapshot.executions_active > 0
    assert snapshot.executions_failed_recently > 0
    assert snapshot.approvals_pending > 0
    assert snapshot.approvals_pending_over_threshold > 0
    assert len(snapshot.tasks_failed_recently) >= 2
    assert len(snapshot.executions_started_recently) >= 2


async def test_loading_again_keeps_the_run_history(engine: AsyncEngine) -> None:
    await _load(engine)
    first = {e.id for e in await _rows(engine, WorkflowExecution)}
    await _load(engine)
    assert {e.id for e in await _rows(engine, WorkflowExecution)} == first
    assert len(first) > 100


async def test_clearing_and_loading_regenerates_the_run_history(
    engine: AsyncEngine,
) -> None:
    await _load(engine)
    first = {e.id for e in await _rows(engine, WorkflowExecution)}
    await _clear(engine)
    await _load(engine)
    second = {e.id for e in await _rows(engine, WorkflowExecution)}
    assert len(second) == len(first)
    assert not first & second


async def test_clearing_keeps_a_real_run_of_a_demo_workflow(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Clearing deletes only runs carrying the history marker; a real run stays."""
    from infrastructure.demo_data import DEMO_EC2_WORKFLOW_ID

    await _load(engine)
    async with AsyncSession(engine) as session:
        session.add(
            WorkflowExecution(
                id="real-run",
                tenant_id=TENANT_ID,
                workflow_id=DEMO_EC2_WORKFLOW_ID,
                session_id="real-session",
                name="Provision Dev EC2 Instance",
                agent_skill_id=DEMO_AGENT_SKILL_ID,
                agent_skill_name=DEMO_AGENT_SKILL_NAME,
                agent_skill_repo_url="https://github.com/kaitoy/a2flow",
                agent_skill_repo_path="sample_skills/aws-ec2-launch",
                initiator_id=DEMO_AWS_REQUESTER_USER_ID,
                created_by=DEMO_AWS_REQUESTER_USER_ID,
                updated_by=DEMO_AWS_REQUESTER_USER_ID,
            )
        )
        await session.commit()
    await _clear(engine)
    await _load(engine)
    async with AsyncSession(engine) as session:
        assert await session.get(WorkflowExecution, "real-run") is not None
