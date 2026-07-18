from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from models.agent_skill import AgentSkill
from models.user import SYSTEM_USER_ID
from tests._envelope import assert_err, assert_ok
from tests._seed import seed_tenant, seed_users
from tests.conftest import _install_auth_overrides


@pytest_asyncio.fixture()
async def skill_client(
    mock_agent_registry: MagicMock,
    mock_sync_job: AsyncMock,
) -> AsyncGenerator[AsyncClient, None]:
    from dependencies import get_agent_registry, get_skill_sync_job
    from infrastructure.database import get_session
    from main import app
    from models.agent_skill import (
        AgentSkill as _AgentSkill,  # noqa: F401 — registers model
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

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_agent_registry] = lambda: mock_agent_registry
    # Without this the router's BackgroundTasks would run the real clone job,
    # which opens its own session on the *application* engine — the developer's
    # database, not this in-memory one.
    app.dependency_overrides[get_skill_sync_job] = lambda: mock_sync_job
    _install_auth_overrides(app)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-User-Id": SYSTEM_USER_ID},
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
        await mem_engine.dispose()


_CREATE_BODY = {"name": "my-skill", "repo_url": "https://github.com/example/repo"}


# ---------- create ----------


async def test_create_skill_returns_201(skill_client: AsyncClient) -> None:
    response = await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY)
    assert response.status_code == 201


async def test_create_skill_response_has_id(skill_client: AsyncClient) -> None:
    response = await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY)
    assert "id" in assert_ok(response, status=201)


async def test_create_skill_response_has_correct_name(
    skill_client: AsyncClient,
) -> None:
    response = await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY)
    assert assert_ok(response, status=201)["name"] == "my-skill"


async def test_create_skill_missing_name_returns_422(skill_client: AsyncClient) -> None:
    response = await skill_client.post(
        "/api/v1/agent-skills", json={"repo_url": "https://github.com/example/repo"}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_skill_missing_repo_url_returns_422(
    skill_client: AsyncClient,
) -> None:
    response = await skill_client.post(
        "/api/v1/agent-skills", json={"name": "my-skill"}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


# ---------- list ----------


async def test_list_skills_empty_initially(skill_client: AsyncClient) -> None:
    response = await skill_client.get("/api/v1/agent-skills")
    assert assert_ok(response) == []


async def test_list_skills_returns_created_skill(skill_client: AsyncClient) -> None:
    await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY)
    response = await skill_client.get("/api/v1/agent-skills")
    assert len(assert_ok(response)) == 1


async def test_list_skills_respects_limit_param(skill_client: AsyncClient) -> None:
    for i in range(3):
        await skill_client.post(
            "/api/v1/agent-skills",
            json={"name": f"skill-{i}", "repo_url": "https://github.com/x/y"},
        )
    response = await skill_client.get("/api/v1/agent-skills", params={"limit": 2})
    assert len(assert_ok(response)) == 2


async def test_list_skills_respects_offset_param(skill_client: AsyncClient) -> None:
    for i in range(3):
        await skill_client.post(
            "/api/v1/agent-skills",
            json={"name": f"skill-{i}", "repo_url": "https://github.com/x/y"},
        )
    response = await skill_client.get(
        "/api/v1/agent-skills", params={"limit": 10, "offset": 2}
    )
    assert len(assert_ok(response)) == 1


# ---------- sort & filter ----------


async def _create_named_skills(skill_client: AsyncClient) -> None:
    for i in range(3):
        await skill_client.post(
            "/api/v1/agent-skills",
            json={"name": f"skill-{i}", "repo_url": "https://github.com/x/y"},
        )


async def test_list_skills_sort_by_name_asc(skill_client: AsyncClient) -> None:
    await _create_named_skills(skill_client)
    response = await skill_client.get("/api/v1/agent-skills", params={"s": "name"})
    names = [s["name"] for s in assert_ok(response)]
    assert names == ["skill-0", "skill-1", "skill-2"]


async def test_list_skills_sort_by_name_desc(skill_client: AsyncClient) -> None:
    await _create_named_skills(skill_client)
    response = await skill_client.get("/api/v1/agent-skills", params={"s": "-name"})
    names = [s["name"] for s in assert_ok(response)]
    assert names == ["skill-2", "skill-1", "skill-0"]


async def test_list_skills_filter_eq(skill_client: AsyncClient) -> None:
    await _create_named_skills(skill_client)
    response = await skill_client.get(
        "/api/v1/agent-skills", params={"q": "name:eq:skill-1"}
    )
    data = assert_ok(response)
    assert [s["name"] for s in data] == ["skill-1"]


async def test_list_skills_filter_like_is_case_insensitive(
    skill_client: AsyncClient,
) -> None:
    await _create_named_skills(skill_client)
    response = await skill_client.get(
        "/api/v1/agent-skills", params={"q": "name:like:skill"}
    )
    assert len(assert_ok(response)) == 3


async def test_list_skills_invalid_sort_field_returns_400(
    skill_client: AsyncClient,
) -> None:
    response = await skill_client.get(
        "/api/v1/agent-skills", params={"s": "bogusField"}
    )
    assert_err(response, code="INVALID_QUERY", status=400)


async def test_list_skills_invalid_filter_operator_returns_400(
    skill_client: AsyncClient,
) -> None:
    response = await skill_client.get(
        "/api/v1/agent-skills", params={"q": "name:bogus:foo"}
    )
    assert_err(response, code="INVALID_QUERY", status=400)


async def test_list_skills_malformed_filter_returns_400(
    skill_client: AsyncClient,
) -> None:
    response = await skill_client.get("/api/v1/agent-skills", params={"q": "name=foo"})
    assert_err(response, code="INVALID_QUERY", status=400)


# ---------- get ----------


async def test_get_skill_returns_200(skill_client: AsyncClient) -> None:
    created = assert_ok(
        await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY), status=201
    )
    response = await skill_client.get(f"/api/v1/agent-skills/{created['id']}")
    assert response.status_code == 200


async def test_get_skill_returns_correct_data(skill_client: AsyncClient) -> None:
    created = assert_ok(
        await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY), status=201
    )
    response = await skill_client.get(f"/api/v1/agent-skills/{created['id']}")
    assert assert_ok(response)["name"] == "my-skill"


async def test_get_skill_unknown_id_returns_404(skill_client: AsyncClient) -> None:
    response = await skill_client.get("/api/v1/agent-skills/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- patch ----------


async def test_update_skill_returns_200(skill_client: AsyncClient) -> None:
    created = assert_ok(
        await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY), status=201
    )
    response = await skill_client.patch(
        f"/api/v1/agent-skills/{created['id']}", json={"name": "Renamed"}
    )
    assert response.status_code == 200


async def test_update_skill_partial_update_leaves_other_fields_unchanged(
    skill_client: AsyncClient,
) -> None:
    created = assert_ok(
        await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY), status=201
    )
    response = await skill_client.patch(
        f"/api/v1/agent-skills/{created['id']}", json={"name": "Renamed"}
    )
    assert assert_ok(response)["repoUrl"] == _CREATE_BODY["repo_url"]


async def test_update_skill_unknown_id_returns_404(skill_client: AsyncClient) -> None:
    response = await skill_client.patch(
        "/api/v1/agent-skills/nonexistent", json={"name": "X"}
    )
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- delete ----------


async def test_delete_skill_returns_200(skill_client: AsyncClient) -> None:
    created = assert_ok(
        await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY), status=201
    )
    response = await skill_client.delete(f"/api/v1/agent-skills/{created['id']}")
    assert assert_ok(response, status=200) is None


async def test_delete_skill_removes_from_list(skill_client: AsyncClient) -> None:
    created = assert_ok(
        await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY), status=201
    )
    await skill_client.delete(f"/api/v1/agent-skills/{created['id']}")
    response = await skill_client.get("/api/v1/agent-skills")
    assert assert_ok(response) == []


async def test_delete_skill_unknown_id_returns_404(skill_client: AsyncClient) -> None:
    response = await skill_client.delete("/api/v1/agent-skills/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- created_by / updated_by ----------


async def test_create_skill_populates_created_and_updated_by_from_header(
    skill_client: AsyncClient,
) -> None:
    response = await skill_client.post(
        "/api/v1/agent-skills", json=_CREATE_BODY, headers={"X-User-Id": "alice"}
    )
    body = assert_ok(response, status=201)
    assert body["createdBy"] == "alice"
    assert body["updatedBy"] == "alice"


async def test_create_skill_with_unknown_user_returns_422(
    skill_client: AsyncClient,
) -> None:
    response = await skill_client.post(
        "/api/v1/agent-skills",
        json=_CREATE_BODY,
        headers={"X-User-Id": "ghost-user"},
    )
    assert_err(response, code="FOREIGN_KEY_VIOLATION", status=422)


async def test_update_skill_preserves_created_by_and_overwrites_updated_by(
    skill_client: AsyncClient,
) -> None:
    created = assert_ok(
        await skill_client.post(
            "/api/v1/agent-skills", json=_CREATE_BODY, headers={"X-User-Id": "alice"}
        ),
        status=201,
    )
    response = await skill_client.patch(
        f"/api/v1/agent-skills/{created['id']}",
        json={"name": "Renamed"},
        headers={"X-User-Id": "bob"},
    )
    body = assert_ok(response)
    assert body["createdBy"] == "alice"
    assert body["updatedBy"] == "bob"


# ---------- field validation ----------


async def test_create_skill_accepts_name_with_spaces(
    skill_client: AsyncClient,
) -> None:
    """Names may contain half-width and full-width spaces and unicode letters."""
    response = await skill_client.post(
        "/api/v1/agent-skills",
        json={"name": "My Skill　日本語", "repo_url": "https://github.com/x/y"},
    )
    assert assert_ok(response, status=201)["name"] == "My Skill　日本語"


async def test_create_skill_rejects_name_with_control_char(
    skill_client: AsyncClient,
) -> None:
    """A name containing a control character is non-printable and returns 422."""
    response = await skill_client.post(
        "/api/v1/agent-skills",
        json={"name": "bad\tname", "repo_url": "https://github.com/x/y"},
    )
    assert_err(response, "VALIDATION_ERROR", 422)


async def test_create_skill_rejects_overlong_name(skill_client: AsyncClient) -> None:
    """A name longer than the 256-character ceiling returns 422."""
    response = await skill_client.post(
        "/api/v1/agent-skills",
        json={"name": "a" * 257, "repo_url": "https://github.com/x/y"},
    )
    assert_err(response, "VALIDATION_ERROR", 422)


async def test_create_skill_rejects_non_http_repo_url(
    skill_client: AsyncClient,
) -> None:
    """A repo_url that is not an http(s) URL returns 422."""
    response = await skill_client.post(
        "/api/v1/agent-skills",
        json={"name": "ok-name", "repo_url": "ftp://example.com/repo"},
    )
    assert_err(response, "VALIDATION_ERROR", 422)


async def test_create_skill_rejects_loopback_repo_url(
    skill_client: AsyncClient,
) -> None:
    """A repo_url whose host is the loopback address returns 422 (SSRF guard)."""
    response = await skill_client.post(
        "/api/v1/agent-skills",
        json={"name": "ok-name", "repo_url": "http://127.0.0.1/x"},
    )
    assert_err(response, "VALIDATION_ERROR", 422)


async def test_create_skill_rejects_repo_url_resolving_to_private_ip(
    skill_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repo_url whose host resolves to a private IP returns 422 (SSRF guard)."""
    monkeypatch.setattr(
        "infrastructure.url_safety.resolve_host", lambda host: ["10.1.2.3"]
    )
    response = await skill_client.post(
        "/api/v1/agent-skills",
        json={"name": "ok-name", "repo_url": "http://internal.example.com/repo"},
    )
    assert_err(response, "VALIDATION_ERROR", 422)


async def test_update_skill_rejects_repo_url_resolving_to_private_ip(
    skill_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Patching repo_url to a host resolving to a private IP returns 422 (SSRF guard)."""
    created = assert_ok(
        await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY), status=201
    )
    monkeypatch.setattr(
        "infrastructure.url_safety.resolve_host", lambda host: ["10.1.2.3"]
    )
    response = await skill_client.patch(
        f"/api/v1/agent-skills/{created['id']}",
        json={"repo_url": "http://internal.example.com/repo"},
    )
    assert_err(response, "VALIDATION_ERROR", 422)


async def test_create_skill_rejects_repo_path_with_parent_segment(
    skill_client: AsyncClient,
) -> None:
    """A repo_path containing a '..' segment could escape the skill cache dir, so it returns 422."""
    response = await skill_client.post(
        "/api/v1/agent-skills",
        json={
            "name": "ok-name",
            "repo_url": "https://github.com/x/y",
            "repo_path": "../../etc",
        },
    )
    assert_err(response, "VALIDATION_ERROR", 422)


async def test_create_skill_rejects_absolute_repo_path(
    skill_client: AsyncClient,
) -> None:
    """A repo_path that is an absolute path returns 422."""
    response = await skill_client.post(
        "/api/v1/agent-skills",
        json={
            "name": "ok-name",
            "repo_url": "https://github.com/x/y",
            "repo_path": "/etc/passwd",
        },
    )
    assert_err(response, "VALIDATION_ERROR", 422)


async def test_create_skill_accepts_nested_repo_path(
    skill_client: AsyncClient,
) -> None:
    """A normal nested repo_path is still accepted."""
    response = await skill_client.post(
        "/api/v1/agent-skills",
        json={
            "name": "ok-name",
            "repo_url": "https://github.com/x/y",
            "repo_path": "skills/my-skill",
        },
    )
    assert assert_ok(response, status=201)["repoPath"] == "skills/my-skill"


# ---------- clone / pull ----------


async def test_create_skill_starts_out_unpublished(skill_client: AsyncClient) -> None:
    """A fresh skill is not runnable: nothing has been cloned for it yet."""
    body = assert_ok(
        await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY), status=201
    )
    assert body["syncStatus"] == "pending"
    assert body["commitSha"] is None
    assert body["syncError"] is None


async def test_create_skill_schedules_the_clone(
    skill_client: AsyncClient, mock_sync_job: AsyncMock
) -> None:
    """Registration returns immediately and leaves the clone to the background."""
    body = assert_ok(
        await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY), status=201
    )
    mock_sync_job.assert_awaited_once_with(body["id"], user_id=SYSTEM_USER_ID)


async def test_create_skill_does_not_accept_server_managed_sync_fields(
    skill_client: AsyncClient,
) -> None:
    """A client must not be able to declare its own skill published."""
    body = assert_ok(
        await skill_client.post(
            "/api/v1/agent-skills",
            json={**_CREATE_BODY, "syncStatus": "ready", "commitSha": "a" * 40},
        ),
        status=201,
    )
    assert body["syncStatus"] == "pending"
    assert body["commitSha"] is None


async def test_pull_schedules_the_clone_and_marks_the_skill_pending(
    skill_client: AsyncClient, mock_sync_job: AsyncMock
) -> None:
    skill = assert_ok(
        await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY), status=201
    )
    mock_sync_job.reset_mock()

    body = assert_ok(
        await skill_client.post(f"/api/v1/agent-skills/{skill['id']}/pull"), status=202
    )

    assert body["syncStatus"] == "pending"
    mock_sync_job.assert_awaited_once_with(skill["id"], user_id=SYSTEM_USER_ID)


async def test_pull_unknown_skill_returns_404(skill_client: AsyncClient) -> None:
    response = await skill_client.post("/api/v1/agent-skills/nonexistent/pull")
    assert_err(response, code="NOT_FOUND", status=404)


async def test_pull_requires_the_developer_role(skill_client: AsyncClient) -> None:
    skill = assert_ok(
        await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY), status=201
    )
    response = await skill_client.post(
        f"/api/v1/agent-skills/{skill['id']}/pull",
        headers={"X-User-Roles": "requester"},
    )
    assert_err(response, code="FORBIDDEN", status=403)


# ---------- serialization ----------


def test_synced_at_is_serialized_with_a_z_suffix() -> None:
    """The frontend's generated Zod schema rejects Pydantic's default ``+00:00`` offset."""
    skill = AgentSkill(
        name="my-skill",
        repo_url="https://github.com/example/repo",
        created_by=SYSTEM_USER_ID,
        updated_by=SYSTEM_USER_ID,
        synced_at=datetime(2026, 7, 14, 12, 0, tzinfo=UTC),
    )
    assert skill.model_dump(mode="json", by_alias=True)["syncedAt"] == (
        "2026-07-14T12:00:00.000Z"
    )


def test_synced_at_is_null_before_the_first_clone() -> None:
    skill = AgentSkill(
        name="my-skill",
        repo_url="https://github.com/example/repo",
        created_by=SYSTEM_USER_ID,
        updated_by=SYSTEM_USER_ID,
    )
    assert skill.model_dump(mode="json", by_alias=True)["syncedAt"] is None
