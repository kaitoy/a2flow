"""Test helpers for seeding the state a write needs before it can happen.

Every persistent entity records ``created_by`` / ``updated_by`` as a foreign key
to ``users.id``. Tests therefore need the acting users to exist before they write
any record. These helpers seed the system user plus a small set of named test
actors so existing tests can keep using ``X-User-Id: alice`` style headers.

:func:`grant_tool_certificate` covers the other precondition a test that drives
MCP tool calls has to reproduce: the certificate a task is granted when it goes
``in_progress``. A test that inserts a task straight into the table skips the
service that would have issued it, and without it every proxied call is refused.
"""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.bootstrap import seed_system_settings, seed_system_user
from models.tenant import Tenant
from models.user import SYSTEM_USER_ID, Role, User
from models.workflow_task import (
    WorkflowTask,
    WorkflowTaskDependency,
    WorkflowTaskStatus,
    WorkflowTaskToolBinding,
)

#: Named test actors seeded with ``id == username`` so ``X-User-Id: alice`` works.
DEFAULT_TEST_USER_IDS: tuple[str, ...] = ("alice", "bob", "carol", "owner", "tester")

#: Roles granted to every seeded test actor. ``approver`` keeps the pre-RBAC
#: test semantics: any named actor can be designated as an approval's approver
#: (the ``request_approval`` tool validates approver eligibility).
DEFAULT_TEST_USER_ROLES: tuple[Role, ...] = (Role.approver,)

#: Tenant id every test client is scoped to by default (see conftest.py's
#: ``X-User-Tenant-Id`` header handling).
DEFAULT_TEST_TENANT_ID = "tenant-default"


async def seed_tenant(
    engine: AsyncEngine, tenant_id: str = DEFAULT_TEST_TENANT_ID
) -> None:
    """Seed a single Tenant row if it does not already exist.

    Args:
        engine: The async engine bound to the test database.
        tenant_id: Id of the tenant to seed.
    """
    async with AsyncSession(engine) as session:
        if await session.get(Tenant, tenant_id) is None:
            session.add(
                Tenant(
                    id=tenant_id,
                    display_name=f"Test Tenant ({tenant_id})",
                    name=tenant_id,
                    enabled=True,
                    created_by=SYSTEM_USER_ID,
                    updated_by=SYSTEM_USER_ID,
                )
            )
            await session.commit()


async def seed_users(
    engine: AsyncEngine,
    ids: Sequence[str] = DEFAULT_TEST_USER_IDS,
    *,
    roles: Sequence[Role] = DEFAULT_TEST_USER_ROLES,
    tenant_id: str | None = None,
) -> None:
    """Seed the system user and the given named test actors into the database.

    Args:
        engine: The async engine bound to the test database.
        ids: User ids to seed; each becomes a user whose ``id`` equals its
            ``username`` so it can be referenced by ``X-User-Id`` headers.
        roles: Roles granted to each seeded actor; defaults to ``approver`` so
            actors stay eligible as approval approvers.
        tenant_id: Tenant each seeded actor belongs to. Defaults to ``None``,
            which resolves to :data:`DEFAULT_TEST_TENANT_ID` unless ``roles``
            includes ``super_admin`` (which must stay tenant-less) — every
            other user must carry a ``tenant_id``
            (``ck_users_non_super_admin_requires_tenant``). Pass an explicit
            value to opt out. The resolved tenant is seeded automatically if
            missing, so callers don't need to seed it themselves first.
    """
    if tenant_id is None:
        tenant_id = None if Role.super_admin in roles else DEFAULT_TEST_TENANT_ID
    async with AsyncSession(engine) as session:
        await seed_system_user(session)
        # Mirrors main.py's lifespan: every reader of the settings row assumes
        # the startup seed created it, so tests need it too.
        await seed_system_settings(session)
    if tenant_id is not None:
        await seed_tenant(engine, tenant_id)
    async with AsyncSession(engine) as session:
        for uid in ids:
            if await session.get(User, uid) is None:
                session.add(
                    User(
                        id=uid,
                        username=uid,
                        first_name=uid.capitalize(),
                        last_name="Test",
                        password="testpassword",
                        email=f"{uid}@test.local",
                        roles=[role.value for role in roles],
                        tenant_id=tenant_id,
                        created_by=SYSTEM_USER_ID,
                        updated_by=SYSTEM_USER_ID,
                    )
                )
        await session.commit()


async def grant_tool_certificate(
    engine: AsyncEngine,
    execution_id: str,
    task_id: str,
    *,
    tenant_id: str = DEFAULT_TEST_TENANT_ID,
) -> None:
    """Take out the run initiator's tool grant for a task seeded in progress.

    Stands in for the ``_settle_certificate`` call both task-write paths make.
    Tests that seed tasks straight into the table bypass those paths, so without
    this the task holds no certificate and
    :class:`infrastructure.mcp_policies.TaskCertificatePolicy` refuses every call
    it makes.

    A no-op when the service declines to issue -- the task is not in progress,
    binds no tools, already holds a grant, or is covered by an approval that has
    not been granted -- so it is safe to call unconditionally after seeding a
    task.

    Args:
        engine: The test engine to write through.
        execution_id: The run the task belongs to.
        task_id: The task to grant.
        tenant_id: Tenant both belong to.
    """
    from repositories.mcp_server import SqlMCPServerRepository
    from repositories.workflow_execution import SqlWorkflowExecutionRepository
    from repositories.workflow_task import SqlWorkflowTaskRepository
    from services.mcp_tool_certificate import build_mcp_tool_certificate_service

    async with AsyncSession(engine, expire_on_commit=False) as db:
        executions = SqlWorkflowExecutionRepository(db, tenant_id=tenant_id)
        tasks = SqlWorkflowTaskRepository(
            db,
            executions,
            SqlMCPServerRepository(db, tenant_id=tenant_id),
            tenant_id=tenant_id,
        )
        execution = await executions.get(execution_id)
        task = await tasks.get(task_id)
        if execution is None or task is None:
            return
        service = build_mcp_tool_certificate_service(db, tenant_id=tenant_id)
        await service.issue_for_started_task(task, execution, user_id=SYSTEM_USER_ID)


async def seed_workflow_task(
    engine: AsyncEngine,
    execution_id: str,
    *,
    title: str = "Task",
    description: str | None = None,
    status: WorkflowTaskStatus = WorkflowTaskStatus.pending,
    depends_on_ids: Sequence[str] = (),
    tool_bindings: Sequence[tuple[str, str]] = (),
    input_approval_exempt: Sequence[tuple[str, str]] = (),
    tenant_id: str = DEFAULT_TEST_TENANT_ID,
    user_id: str = "owner",
) -> str:
    """Insert a WorkflowTask, its dependency edges, and its tool bindings.

    Stands in for the ``create_workflow_task`` agent tool that tests once called
    for setup. A run's tasks are copied from the workflow's published templates
    at execute time, so the execution agent can no longer create them; a test
    that needs a task to already exist seeds it straight into the table here.

    Certificate issuance is left to the caller (:func:`grant_tool_certificate`),
    which is a no-op unless the task is in progress and binds tools.

    Args:
        engine: The async engine bound to the test database.
        execution_id: The WorkflowExecution the task belongs to.
        title: The task title.
        description: Optional longer description.
        status: The task's lifecycle status.
        depends_on_ids: Ids of same-run tasks this task depends on; one
            dependency edge is written per id.
        tool_bindings: ``(mcp_server_id, tool_name)`` pairs to bind to the task.
        input_approval_exempt: Which of ``tool_bindings`` to write with
            ``requires_input_approval`` cleared — the workflow design saying that
            tool only reads. Named separately rather than widening the pairs so
            the many callers that never exempt anything stay as they are.
        tenant_id: Tenant the task belongs to.
        user_id: Actor recorded in ``created_by`` / ``updated_by``.

    Returns:
        The new task's id.
    """
    async with AsyncSession(engine) as session:
        task = WorkflowTask(
            workflow_execution_id=execution_id,
            title=title,
            description=description,
            status=status,
            tenant_id=tenant_id,
            created_by=user_id,
            updated_by=user_id,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        # Captured before the second commit: that commit expires ``task``, and
        # reading an expired attribute outside a greenlet context raises
        # MissingGreenlet on an async session.
        task_id = task.id
        for depends_on_id in depends_on_ids:
            session.add(
                WorkflowTaskDependency(task_id=task_id, depends_on_id=depends_on_id)
            )
        exempt = set(input_approval_exempt)
        for server_id, tool_name in tool_bindings:
            session.add(
                WorkflowTaskToolBinding(
                    task_id=task_id,
                    mcp_server_id=server_id,
                    tool_name=tool_name,
                    requires_input_approval=(server_id, tool_name) not in exempt,
                )
            )
        await session.commit()
        return task_id
