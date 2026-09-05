"""Repository tests for reading a workflow's published snapshot.

``SqlWorkflowPublishedVersionRepository.list_templates`` is the one query in the
codebase that reads *into* a JSON column, and it is spelled differently on each
dialect: ``jsonb_array_elements`` with ``WITH ORDINALITY`` on PostgreSQL,
``json_each`` on SQLite. Every test here therefore runs against both, so the two
spellings cannot drift apart.

SQLite runs always. PostgreSQL runs only when ``A2FLOW_TEST_PG_URL`` names a
reachable server, and is skipped otherwise. Note that this module names both
dialects explicitly, where every other module takes whichever one that variable
selects: a run that covered only one of the two spellings could not show that
they still agree.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from models.agent_skill import AgentSkill
from models.user import SYSTEM_USER_ID
from models.workflow import Workflow, WorkflowStatus
from models.workflow_published_version import (
    WorkflowPublishedVersion,
    WorkflowPublishedVersionTemplate,
    dump_templates,
    parse_templates,
)
from models.workflow_task import ToolBinding
from repositories.exceptions import QueryValidationError
from repositories.query import FilterSpec, SortSpec
from repositories.workflow_published_version import (
    SqlWorkflowPublishedVersionRepository,
)
from tests._engine import (
    PG_URL_ENV,
    make_postgres_engine,
    make_sqlite_engine,
    pg_url,
)
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users

OTHER_TENANT_ID = "tenant-other"
WORKFLOW_ID = "wf-published"
OTHER_WORKFLOW_ID = "wf-other-tenant"


def _template(
    template_id: str, title: str, minute: int
) -> WorkflowPublishedVersionTemplate:
    """Build one snapshot template with a distinct title and audit timestamp."""
    stamp = datetime(2026, 1, 1, 0, minute, tzinfo=UTC)
    return WorkflowPublishedVersionTemplate(
        id=template_id,
        title=title,
        description=f"description of {title}",
        depends_on_ids=[],
        tool_bindings=[ToolBinding(mcp_server_id="srv-1", tool_name=f"tool-{title}")],
        created_at=stamp,
        updated_at=stamp,
        created_by="alice",
        updated_by="alice",
    )


#: Published in this order, deliberately neither alphabetical nor chronological,
#: so "stored order" is distinguishable from every other ordering under test.
PUBLISHED = [
    _template("t-charlie", "Charlie", 30),
    _template("t-alpha", "alpha", 10),
    _template("t-bravo", "Bravo", 20),
]


async def _seed(engine: AsyncEngine) -> None:
    """Seed the tenant chain, a workflow per tenant, and their snapshots."""
    await seed_users(engine)
    await seed_tenant(engine, OTHER_TENANT_ID)
    async with AsyncSession(engine) as session:
        for tenant_id, workflow_id, skill_id in (
            (DEFAULT_TEST_TENANT_ID, WORKFLOW_ID, "skill-1"),
            (OTHER_TENANT_ID, OTHER_WORKFLOW_ID, "skill-2"),
        ):
            session.add(
                AgentSkill(
                    id=skill_id,
                    name=f"skill for {tenant_id}",
                    repo_url="https://example.invalid/skill.git",
                    tenant_id=tenant_id,
                    created_by=SYSTEM_USER_ID,
                    updated_by=SYSTEM_USER_ID,
                )
            )
            session.add(
                Workflow(
                    id=workflow_id,
                    name=f"workflow for {tenant_id}",
                    agent_skill_id=skill_id,
                    session_id=f"session-{workflow_id}",
                    agent_skill_commit_sha="a" * 40,
                    status=WorkflowStatus.modified,
                    tenant_id=tenant_id,
                    created_by=SYSTEM_USER_ID,
                    updated_by=SYSTEM_USER_ID,
                )
            )
        await session.commit()

    async with AsyncSession(engine) as session:
        for tenant_id, workflow_id in (
            (DEFAULT_TEST_TENANT_ID, WORKFLOW_ID),
            (OTHER_TENANT_ID, OTHER_WORKFLOW_ID),
        ):
            repo = SqlWorkflowPublishedVersionRepository(session, tenant_id=tenant_id)
            await repo.upsert(
                workflow_id,
                name=f"published name for {tenant_id}",
                description="published description",
                templates=dump_templates(PUBLISHED),
                user_id=SYSTEM_USER_ID,
            )


@pytest_asyncio.fixture(params=["sqlite", "postgresql"])
async def repo(
    request: pytest.FixtureRequest,
) -> AsyncGenerator[SqlWorkflowPublishedVersionRepository, None]:
    """Yield a repository over a freshly seeded database, once per dialect.

    Both dialects are named explicitly rather than following whichever backend
    ``A2FLOW_TEST_PG_URL`` selects for the rest of the suite: the point of this
    module is that the two spellings agree, which a run covering only one of
    them cannot show.
    """
    if request.param == "sqlite":
        engine = await make_sqlite_engine()
    else:
        if pg_url() is None:
            pytest.skip(f"{PG_URL_ENV} is not set; skipping the PostgreSQL dialect")
        engine = await make_postgres_engine()

    try:
        await _seed(engine)
        async with AsyncSession(engine) as session:
            yield SqlWorkflowPublishedVersionRepository(
                session, tenant_id=DEFAULT_TEST_TENANT_ID
            )
    finally:
        await engine.dispose()


async def _titles(
    repo: SqlWorkflowPublishedVersionRepository, **kwargs: object
) -> list[str]:
    """Return the titles of a page of published templates."""
    rows = await repo.list_templates(WORKFLOW_ID, **kwargs)  # type: ignore[arg-type]
    return [t.title for t in rows]


# ---------- list_templates: ordering ----------


async def test_list_templates_defaults_to_the_published_order(
    repo: SqlWorkflowPublishedVersionRepository,
) -> None:
    """With no sort, templates come back in the order they were published."""
    assert await _titles(repo, limit=10, offset=0) == ["Charlie", "alpha", "Bravo"]


async def test_list_templates_sorts_by_a_snapshot_field(
    repo: SqlWorkflowPublishedVersionRepository,
) -> None:
    """A sort spec orders by the value read out of the JSON payload."""
    assert await _titles(
        repo,
        limit=10,
        offset=0,
        sort=[SortSpec(field="createdAt", descending=True)],
    ) == ["Charlie", "Bravo", "alpha"]


async def test_list_templates_sorts_ascending_too(
    repo: SqlWorkflowPublishedVersionRepository,
) -> None:
    """Ascending order is the mirror of descending, not the stored order."""
    assert await _titles(
        repo,
        limit=10,
        offset=0,
        sort=[SortSpec(field="createdAt", descending=False)],
    ) == ["alpha", "Bravo", "Charlie"]


# ---------- list_templates: filtering ----------


async def test_list_templates_filters_by_substring(
    repo: SqlWorkflowPublishedVersionRepository,
) -> None:
    """``like`` matches case-insensitively, as it does on the live rows."""
    assert await _titles(
        repo,
        limit=10,
        offset=0,
        filters=[FilterSpec(field="title", op="like", value="BRAV")],
    ) == ["Bravo"]


async def test_list_templates_filters_by_id_list(
    repo: SqlWorkflowPublishedVersionRepository,
) -> None:
    """``in`` matches any of the listed ids."""
    assert await _titles(
        repo,
        limit=10,
        offset=0,
        filters=[FilterSpec(field="id", op="in", value="t-alpha,t-bravo")],
    ) == ["alpha", "Bravo"]


async def test_list_templates_compares_timestamps_chronologically(
    repo: SqlWorkflowPublishedVersionRepository,
) -> None:
    """A datetime filter compares as time, even though the value is JSON text."""
    assert await _titles(
        repo,
        limit=10,
        offset=0,
        filters=[FilterSpec(field="createdAt", op="gt", value="2026-01-01T00:15:00Z")],
    ) == ["Charlie", "Bravo"]


async def test_list_templates_filters_by_the_workflow_it_belongs_to(
    repo: SqlWorkflowPublishedVersionRepository,
) -> None:
    """``workflowId`` resolves even though the snapshot does not store it."""
    assert (
        len(
            await _titles(
                repo,
                limit=10,
                offset=0,
                filters=[FilterSpec(field="workflowId", op="eq", value=WORKFLOW_ID)],
            )
        )
        == 3
    )
    assert (
        await _titles(
            repo,
            limit=10,
            offset=0,
            filters=[FilterSpec(field="workflowId", op="eq", value="somewhere-else")],
        )
        == []
    )


async def test_list_templates_rejects_a_field_the_read_model_hides(
    repo: SqlWorkflowPublishedVersionRepository,
) -> None:
    """``tenantId`` is off the read model, so it is unaddressable here too."""
    with pytest.raises(QueryValidationError):
        await repo.list_templates(
            WORKFLOW_ID,
            limit=10,
            offset=0,
            filters=[FilterSpec(field="tenantId", op="eq", value="tenant-default")],
        )


async def test_list_templates_rejects_an_unknown_field(
    repo: SqlWorkflowPublishedVersionRepository,
) -> None:
    """A field on neither model is rejected before any SQL is built."""
    with pytest.raises(QueryValidationError):
        await repo.list_templates(
            WORKFLOW_ID,
            limit=10,
            offset=0,
            sort=[SortSpec(field="nonsense", descending=False)],
        )


# ---------- list_templates: paging and payload ----------


async def test_list_templates_pages_within_the_snapshot(
    repo: SqlWorkflowPublishedVersionRepository,
) -> None:
    """``limit``/``offset`` window the array, not the snapshot rows."""
    assert await _titles(repo, limit=1, offset=1) == ["alpha"]
    assert await _titles(repo, limit=2, offset=1) == ["alpha", "Bravo"]


async def test_list_templates_restores_the_whole_payload(
    repo: SqlWorkflowPublishedVersionRepository,
) -> None:
    """Every stored field survives the round trip, audit columns included."""
    (template,) = await repo.list_templates(
        WORKFLOW_ID,
        limit=10,
        offset=0,
        filters=[FilterSpec(field="id", op="eq", value="t-alpha")],
    )
    assert template.title == "alpha"
    assert template.description == "description of alpha"
    assert template.created_by == "alice"
    assert template.created_at == datetime(2026, 1, 1, 0, 10, tzinfo=UTC)
    assert [b.tool_name for b in template.tool_bindings] == ["tool-alpha"]


def test_publishing_freezes_whether_a_tool_needs_input_approval() -> None:
    """The flag is part of the design, so it is part of what publishing freezes.

    A run reads its tools from this snapshot, and the approval it later asks for
    is built from what the run's tasks carry — so a flag lost in the JSON column
    would quietly put a tool back under bounds the design said it did not need.
    """
    template = WorkflowPublishedVersionTemplate(
        id="t-read-only",
        title="Look around",
        tool_bindings=[
            ToolBinding(
                mcp_server_id="srv-1",
                tool_name="list_instances",
                requires_input_approval=False,
            ),
            ToolBinding(mcp_server_id="srv-1", tool_name="launch"),
        ],
    )
    version = WorkflowPublishedVersion(
        workflow_id=WORKFLOW_ID,
        name="wf",
        templates=dump_templates([template]),
        tenant_id=DEFAULT_TEST_TENANT_ID,
        created_by=SYSTEM_USER_ID,
        updated_by=SYSTEM_USER_ID,
    )

    (restored,) = parse_templates(version)
    assert [
        (b.tool_name, b.requires_input_approval) for b in restored.tool_bindings
    ] == [("list_instances", False), ("launch", True)]


async def test_list_templates_of_an_unpublished_workflow_is_empty(
    repo: SqlWorkflowPublishedVersionRepository,
) -> None:
    """No snapshot means nothing to show — never a fallback to the live rows."""
    assert await repo.list_templates("no-such-workflow", limit=10, offset=0) == []


async def test_list_templates_does_not_cross_tenants(
    repo: SqlWorkflowPublishedVersionRepository,
) -> None:
    """Another tenant's snapshot is invisible even by exact workflow id."""
    assert await repo.list_templates(OTHER_WORKFLOW_ID, limit=10, offset=0) == []


# ---------- get_many ----------


async def test_get_many_returns_the_snapshots_keyed_by_workflow(
    repo: SqlWorkflowPublishedVersionRepository,
) -> None:
    """Ids without a snapshot are simply absent from the mapping."""
    found = await repo.get_many([WORKFLOW_ID, "no-such-workflow"])
    assert list(found) == [WORKFLOW_ID]
    assert found[WORKFLOW_ID].name == f"published name for {DEFAULT_TEST_TENANT_ID}"


async def test_get_many_does_not_cross_tenants(
    repo: SqlWorkflowPublishedVersionRepository,
) -> None:
    """Another tenant's snapshot never appears, even when asked for by id."""
    assert await repo.get_many([OTHER_WORKFLOW_ID]) == {}


async def test_get_many_of_nothing_queries_nothing(
    repo: SqlWorkflowPublishedVersionRepository,
) -> None:
    """An empty request short-circuits instead of building a degenerate IN ()."""
    assert await repo.get_many([]) == {}
