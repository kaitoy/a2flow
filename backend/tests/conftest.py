import importlib
import math
import os
import pkgutil
from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import Request
from google.adk.sessions import InMemorySessionService
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import configure_mappers
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

import models
from config import Settings, get_settings
from models.user import SYSTEM_USER_ID, User
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users

# Import every model submodule (mirroring alembic/env.py) and configure
# SQLAlchemy's mappers before any test runs. Without this, whichever test
# happens to be first to build a User via ``User.model_construct(...)`` (the
# header-driven auth override below) and read a mapped attribute off it --
# ``id``, ``tenant_id``, anything -- crashes with a cryptic
# ``AttributeError: 'NoneType' object has no attribute 'supports_population'``:
# ``model_construct`` bypasses the real ``__init__``, so it never triggers
# SQLAlchemy's normal lazy mapper configuration itself.
for _finder, _module_name, _is_pkg in pkgutil.iter_modules(models.__path__):
    importlib.import_module(f"models.{_module_name}")
configure_mappers()

_WORKER_CPU_RATIO = 0.5  # matches frontend/vitest.config.ts's `maxWorkers: "50%"`


@pytest.hookimpl(tryfirst=True)
def pytest_xdist_auto_num_workers(config: pytest.Config) -> int:
    """Cap pytest-xdist's ``-n auto`` worker count at 50% of host CPU cores.

    Mirrors ``frontend/vitest.config.ts``'s ``maxWorkers: "50%"`` so a
    ``lefthook`` pre-commit run that spins up both suites concurrently
    doesn't oversubscribe the CPU. As a conftest.py plugin this hookimpl
    registers after xdist's own, and since the hookspec is
    ``firstresult=True``, its return value short-circuits xdist's own
    ``psutil``/``os.sched_getaffinity`` fallback chain before it runs.
    ``psutil`` isn't a project dependency and ``os.sched_getaffinity``
    doesn't exist on Windows, so on this Windows-first dev stack xdist's own
    chain already bottoms out at ``os.cpu_count()`` today anyway -- using it
    directly here isn't a loss of fidelity.

    Args:
        config: The pytest config object. Unused, but required by the
            ``pytest_xdist_auto_num_workers`` hookspec signature.

    Returns:
        Half the host's logical CPU count, floored, with a floor of 1 so a
        single-core host still gets one worker.
    """
    cpu_count = os.cpu_count() or 1
    return max(1, math.floor(cpu_count * _WORKER_CPU_RATIO))


@pytest.fixture(autouse=True)
def _reset_settings_cache(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear the memoized ``Settings`` singleton and isolate it from ``.env``.

    ``config.get_settings`` is process-wide ``@lru_cache``d; without clearing
    it before and after every test, the first test that constructs it would
    freeze every later test's view of env-driven config (``ADMIN_PASSWORD``,
    ``ROOT_PASSWORD``, ``SESSION_IDLE_TIMEOUT_SECONDS``,
    ``SECRET_ENCRYPTION_KEY``/``SECRET_KEY_FILE``, ...) regardless of
    ``monkeypatch.setenv``/``delenv`` calls made during the test.

    ``Settings`` also reads ``backend/.env`` directly (independent of
    ``os.environ``), so real values a developer has set there (e.g. a local
    ``ADMIN_PASSWORD`` or ``ROOT_PASSWORD``) would otherwise leak into tests
    that expect the variable to be unset and rely on ``monkeypatch.delenv``
    to simulate that. Disabling the dotenv source here keeps tests seeing
    only ``os.environ``.
    """
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _override_get_current_user_id(request: Request) -> str:
    """Test stand-in for the auth dependency that trusts the ``X-User-Id`` header.

    Returns the id straight from the header (defaulting to ``""``), so existing
    tests keep selecting their acting user via ``X-User-Id`` and the
    repository's foreign-key enforcement still rejects unknown ids exactly as
    before — without going through real login.
    """
    return request.headers.get("X-User-Id", "")


async def _override_get_current_user(request: Request) -> User:
    """Test stand-in for the route guard; returns a synthetic user holding the id.

    Roles are taken from the ``X-User-Roles`` header (comma-separated),
    defaulting to ``super_admin`` so pre-RBAC tests keep passing every role
    and ownership check. Role-specific tests opt in by setting the header
    explicitly (e.g. ``X-User-Roles: requester`` or an empty value for a
    role-less user).

    ``tenant_id`` is taken from the ``X-User-Tenant-Id`` header, defaulting to
    :data:`tests._seed.DEFAULT_TEST_TENANT_ID` when the header is absent so
    tenant-scoped routes work out of the box; passing an explicit empty value
    opts a test into a platform-scoped (``tenant_id=None``) caller, mirroring
    the ``X-User-Roles`` absent-vs-empty convention above.
    """
    roles_header = request.headers.get("X-User-Roles")
    if roles_header is None:
        roles = ["super_admin"]
    else:
        roles = [r.strip() for r in roles_header.split(",") if r.strip()]
    tenant_header = request.headers.get("X-User-Tenant-Id")
    tenant_id = (
        DEFAULT_TEST_TENANT_ID if tenant_header is None else (tenant_header or None)
    )
    return User.model_construct(
        id=request.headers.get("X-User-Id", ""), roles=roles, tenant_id=tenant_id
    )


def _override_verify_csrf() -> None:
    """Test stand-in that disables CSRF validation for header-authenticated tests."""
    return None


def _install_auth_overrides(app: Any) -> None:
    """Override the auth and CSRF dependencies with the header-based test stand-ins.

    ``get_session_user`` (``RealUserDep``'s dependency -- the real,
    non-impersonated identity) is overridden with the same stand-in as
    ``get_current_user``: these header-driven tests have no real session
    cookie at all, so without this override anything depending on
    ``RealUserDep`` (``require_actor_roles``, the impersonate routes, ``GET
    /auth/me``) would 401 trying to read a cookie that was never set.
    """
    from dependencies.auth import (
        get_current_user,
        get_current_user_id,
        get_session_user,
        verify_csrf,
    )

    app.dependency_overrides[get_current_user] = _override_get_current_user
    app.dependency_overrides[get_session_user] = _override_get_current_user
    app.dependency_overrides[get_current_user_id] = _override_get_current_user_id
    app.dependency_overrides[verify_csrf] = _override_verify_csrf


@pytest.fixture(autouse=True)
def _isolated_secret_key_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point the secret-encryption key file at a per-test temp path.

    Without this, the first test that touches the LRU-cached
    ``get_secret_cipher`` singleton would generate a ``.secret_key`` file next
    to the developer's working directory. Tests that exercise the key-loading
    precedence re-patch these variables within the test body.
    """
    monkeypatch.setenv("SECRET_KEY_FILE", str(tmp_path / "secret.key"))
    monkeypatch.delenv("SECRET_ENCRYPTION_KEY", raising=False)


@pytest.fixture(autouse=True)
def _fake_dns_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub DNS resolution used by SSRF host validation for all tests by default.

    Existing fixtures use placeholder hostnames (``example.com``, ``x``, ``y``,
    ``mcp.example.com``) that aren't expected to resolve over real DNS. This
    makes every non-literal hostname resolve to a fixed public IP so existing
    MCPServer/AgentSkill create/update tests keep passing without network
    access. Tests exercising SSRF rejection re-patch this within the test body
    (monkeypatch stacks per-test, so the later call wins for that test).
    """
    monkeypatch.setattr(
        "infrastructure.url_safety.resolve_host", lambda host: ["93.184.216.34"]
    )


@pytest.fixture(autouse=True)
def _fast_bcrypt_rounds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use bcrypt's minimum cost factor for password hashing in tests.

    Nearly every test pays a real bcrypt hash via fixture setup alone (e.g.
    ``tests/_seed.py``'s ``seed_users``, which every per-file DB client
    fixture calls, hashes a random token for the system user). Lowering the
    cost to 4 -- bcrypt's minimum -- cuts that cost sharply; ``verify_password``
    still round-trips correctly regardless of the rounds used to create the
    hash.
    """
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")


@pytest.fixture()
def real_session_service() -> InMemorySessionService:
    return InMemorySessionService()  # type: ignore[no-untyped-call]


@pytest.fixture()
def mock_adk_agent() -> MagicMock:
    agent = MagicMock()

    async def _empty_gen(
        *args: object, **kwargs: object
    ) -> AsyncGenerator[object, None]:
        return
        yield

    agent.run = _empty_gen
    return agent


@pytest.fixture()
def mock_agent_registry(mock_adk_agent: MagicMock) -> MagicMock:
    registry = MagicMock()
    registry.get.return_value = mock_adk_agent
    return registry


#: Commit sha the fake skill store reports for every clone, and that tests
#: expect a WorkflowSession to be pinned to.
FAKE_COMMIT_SHA = "a" * 40


@pytest.fixture()
def mock_skill_manager(tmp_path: Path) -> MagicMock:
    """A skill store whose revision directories exist but are never really cloned.

    ``skill_dir`` returns a real, existing path because ``resolve_agent`` checks
    for it before handing the directory to ADK; the directory is empty, which is
    fine since the agent registry is mocked too.
    """
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    manager = MagicMock()
    manager.clone = AsyncMock(return_value=FAKE_COMMIT_SHA)
    manager.skill_dir = MagicMock(return_value=skill_dir)
    manager.prune = AsyncMock()
    return manager


@pytest.fixture()
def mock_sync_job() -> AsyncMock:
    """Stand-in for the background clone job scheduled by the agent-skills router.

    The real job opens a database session on the application engine, which a
    test driving the router over an in-memory database cannot redirect — so it
    is replaced wholesale. ``workflow_client`` gives it a side effect that
    publishes :data:`FAKE_COMMIT_SHA` on the skill, standing in for a successful
    clone, so a skill registered through the API ends up runnable exactly as it
    would in production. Tests can still assert on the scheduling, or override
    the side effect to simulate a clone that failed.
    """
    return AsyncMock()


@pytest.fixture()
def mock_generation_job() -> AsyncMock:
    """Stand-in for the background plan-generation job ("Generate workflow").

    The real job runs a full agent turn against an LLM and opens database
    sessions on the application engine, so it is replaced wholesale.
    ``workflow_client`` gives it a side effect that flips the workflow to
    ``draft`` — standing in for a generation run that finished without
    registering templates, which tests then add through the API. Tests can
    override the side effect (e.g. ``None``) to keep the workflow
    ``generating``.
    """
    return AsyncMock()


@pytest_asyncio.fixture()
async def client_with_real_sessions(
    real_session_service: InMemorySessionService,
    mock_agent_registry: MagicMock,
) -> AsyncGenerator[AsyncClient, None]:
    from dependencies import (
        get_agent_registry,
        get_session_service,
    )
    from main import app

    app.dependency_overrides[get_session_service] = lambda: real_session_service
    app.dependency_overrides[get_agent_registry] = lambda: mock_agent_registry
    _install_auth_overrides(app)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


@asynccontextmanager
async def _workflow_client_env(
    mock_agent_registry: MagicMock,
    mock_skill_manager: MagicMock,
    mock_sync_job: AsyncMock,
    mock_generation_job: AsyncMock,
    real_session_service: InMemorySessionService,
) -> AsyncIterator[tuple[AsyncClient, AsyncEngine]]:
    """Set up the workflow API client and its backing in-memory engine.

    Shared by the ``workflow_client`` fixture (client only) and
    ``workflow_client_with_engine`` (client plus engine, for tests that need to
    seed rows — e.g. an Approval — directly via the database).
    """
    from dependencies import (
        get_agent_registry,
        get_session_service,
        get_skill_manager,
        get_skill_sync_job,
        get_workflow_generation_job,
    )
    from infrastructure.database import get_session
    from main import app
    from models.agent_skill import (
        AgentSkill as _AgentSkill,  # noqa: F401 — registers model
    )
    from models.planning_session import (
        PlanningSession as _PlanningSession,  # noqa: F401 — registers model
    )
    from models.workflow import Workflow as _Workflow  # noqa: F401 — registers model
    from models.workflow_session import (
        WorkflowSession as _WorkflowSession,  # noqa: F401 — registers model
    )
    from models.workflow_task import (
        WorkflowTask as _WorkflowTask,  # noqa: F401 — registers model
    )
    from models.workflow_task_template import (
        WorkflowTaskTemplate as _WorkflowTaskTemplate,  # noqa: F401 — registers model
    )

    mem_engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa_event.listens_for(mem_engine.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with mem_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await seed_users(mem_engine)
    await seed_tenant(mem_engine)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(mem_engine) as session:
            yield session

    async def fake_sync(skill_id: str, *, user_id: str) -> None:
        """Publish a revision on the skill, as a successful clone would."""
        from models.agent_skill import SkillSyncStatus
        from repositories.agent_skill import SqlAgentSkillRepository

        async with AsyncSession(mem_engine) as session:
            await SqlAgentSkillRepository(
                session, tenant_id=DEFAULT_TEST_TENANT_ID
            ).set_sync_state(
                skill_id,
                status=SkillSyncStatus.ready,
                commit_sha=FAKE_COMMIT_SHA,
                user_id=user_id,
            )

    mock_sync_job.side_effect = fake_sync

    async def fake_generate(workflow_id: str, prompt: str, *, user_id: str) -> None:
        """Flip the workflow to ``draft``, as a finished generation run would."""
        from models.workflow import WorkflowStatus
        from repositories.agent_skill import SqlAgentSkillRepository
        from repositories.workflow import SqlWorkflowRepository

        async with AsyncSession(mem_engine) as session:
            workflows = SqlWorkflowRepository(
                session,
                SqlAgentSkillRepository(session, tenant_id=DEFAULT_TEST_TENANT_ID),
                tenant_id=DEFAULT_TEST_TENANT_ID,
            )
            await workflows.set_status(
                workflow_id, WorkflowStatus.draft, user_id=user_id
            )

    mock_generation_job.side_effect = fake_generate

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_agent_registry] = lambda: mock_agent_registry
    app.dependency_overrides[get_session_service] = lambda: real_session_service
    app.dependency_overrides[get_skill_manager] = lambda: mock_skill_manager
    app.dependency_overrides[get_skill_sync_job] = lambda: mock_sync_job
    app.dependency_overrides[get_workflow_generation_job] = lambda: mock_generation_job
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


@pytest_asyncio.fixture()
async def workflow_client(
    mock_agent_registry: MagicMock,
    mock_skill_manager: MagicMock,
    mock_sync_job: AsyncMock,
    mock_generation_job: AsyncMock,
    real_session_service: InMemorySessionService,
) -> AsyncGenerator[AsyncClient, None]:
    async with _workflow_client_env(
        mock_agent_registry,
        mock_skill_manager,
        mock_sync_job,
        mock_generation_job,
        real_session_service,
    ) as (ac, _engine):
        yield ac


@pytest_asyncio.fixture()
async def workflow_client_with_engine(
    mock_agent_registry: MagicMock,
    mock_skill_manager: MagicMock,
    mock_sync_job: AsyncMock,
    mock_generation_job: AsyncMock,
    real_session_service: InMemorySessionService,
) -> AsyncGenerator[tuple[AsyncClient, AsyncEngine], None]:
    """Like ``workflow_client``, but also yields the backing engine.

    For tests that need to seed rows directly via the database (e.g. an
    Approval, which has no ``POST`` create endpoint — only the agent's
    ``request_approval`` tool creates them).
    """
    async with _workflow_client_env(
        mock_agent_registry,
        mock_skill_manager,
        mock_sync_job,
        mock_generation_job,
        real_session_service,
    ) as (ac, eng):
        yield ac, eng


#: Credentials of the enabled user seeded for the real-auth ``auth_client``.
AUTH_USERNAME = "loginuser"
AUTH_PASSWORD = "login-password-123"


@pytest_asyncio.fixture()
async def auth_client() -> AsyncGenerator[AsyncClient, None]:
    """Yield a client exercising the real auth/CSRF flow (no dependency overrides).

    Backed by an in-memory database seeded with the system user and one enabled
    login user (:data:`AUTH_USERNAME` / :data:`AUTH_PASSWORD`, password hashed),
    so tests can drive ``/auth/login``, ``/auth/me``, and ``/auth/logout`` end
    to end. The ``httpx`` client keeps a cookie jar across requests, so cookies
    set at login are sent automatically on later calls.
    """
    from dependencies.auth import get_current_user, verify_csrf  # noqa: F401
    from infrastructure.database import get_session
    from infrastructure.password import hash_password
    from main import app
    from models.auth_session import AuthSession as _AuthSession  # noqa: F401
    from models.user import User as _User  # noqa: F401

    mem_engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa_event.listens_for(mem_engine.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with mem_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await seed_users(mem_engine, ids=())
    async with AsyncSession(mem_engine) as session:
        session.add(
            _User(
                username=AUTH_USERNAME,
                first_name="Login",
                last_name="User",
                password=hash_password(AUTH_PASSWORD),
                email="login@test.local",
                enabled=True,
                tenant_id=DEFAULT_TEST_TENANT_ID,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        await session.commit()

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(mem_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
        await mem_engine.dispose()
