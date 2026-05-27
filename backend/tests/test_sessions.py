from google.adk.sessions import InMemorySessionService
from httpx import AsyncClient

from dependencies import APP_NAME
from tests._envelope import assert_err, assert_ok


async def _create_session(
    service: InMemorySessionService, user_id: str, session_id: str | None = None
) -> str:
    session = await service.create_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    return session.id


async def test_list_sessions_empty_for_new_user(
    client_with_real_sessions: AsyncClient,
) -> None:
    response = await client_with_real_sessions.get(
        "/api/v1/sessions", headers={"X-User-Id": "nobody"}
    )
    assert assert_ok(response) == []


async def test_list_sessions_returns_created_sessions(
    client_with_real_sessions: AsyncClient,
    real_session_service: InMemorySessionService,
) -> None:
    await _create_session(real_session_service, "bob")
    await _create_session(real_session_service, "bob")
    response = await client_with_real_sessions.get(
        "/api/v1/sessions", headers={"X-User-Id": "bob"}
    )
    assert len(assert_ok(response)) == 2


async def test_list_sessions_does_not_mix_users(
    client_with_real_sessions: AsyncClient,
    real_session_service: InMemorySessionService,
) -> None:
    await _create_session(real_session_service, "carol")
    await _create_session(real_session_service, "dave")
    carol_sessions = assert_ok(
        await client_with_real_sessions.get(
            "/api/v1/sessions", headers={"X-User-Id": "carol"}
        )
    )
    dave_sessions = assert_ok(
        await client_with_real_sessions.get(
            "/api/v1/sessions", headers={"X-User-Id": "dave"}
        )
    )
    assert len(carol_sessions) == 1
    assert len(dave_sessions) == 1
    assert carol_sessions[0]["userId"] == "carol"
    assert dave_sessions[0]["userId"] == "dave"


async def test_get_messages_returns_empty_list_for_new_session(
    client_with_real_sessions: AsyncClient,
    real_session_service: InMemorySessionService,
) -> None:
    session_id = await _create_session(real_session_service, "eve")
    response = await client_with_real_sessions.get(
        f"/api/v1/sessions/{session_id}/messages", headers={"X-User-Id": "eve"}
    )
    assert assert_ok(response) == []


async def test_get_messages_returns_404_for_unknown_session(
    client_with_real_sessions: AsyncClient,
) -> None:
    response = await client_with_real_sessions.get(
        "/api/v1/sessions/nonexistent-id/messages", headers={"X-User-Id": "eve"}
    )
    err = assert_err(response, code="NOT_FOUND", status=404)
    assert err["details"]["entity"] == "Session"


async def test_delete_session_returns_200(
    client_with_real_sessions: AsyncClient,
    real_session_service: InMemorySessionService,
) -> None:
    session_id = await _create_session(real_session_service, "frank")
    response = await client_with_real_sessions.delete(
        f"/api/v1/sessions/{session_id}", headers={"X-User-Id": "frank"}
    )
    assert assert_ok(response, status=200) is None


async def test_delete_session_removes_session_from_list(
    client_with_real_sessions: AsyncClient,
    real_session_service: InMemorySessionService,
) -> None:
    session_id = await _create_session(real_session_service, "grace")
    await client_with_real_sessions.delete(
        f"/api/v1/sessions/{session_id}", headers={"X-User-Id": "grace"}
    )
    list_resp = await client_with_real_sessions.get(
        "/api/v1/sessions", headers={"X-User-Id": "grace"}
    )
    assert assert_ok(list_resp) == []


async def test_delete_session_returns_404_for_unknown_session(
    client_with_real_sessions: AsyncClient,
) -> None:
    response = await client_with_real_sessions.delete(
        "/api/v1/sessions/nonexistent-id", headers={"X-User-Id": "grace"}
    )
    assert_err(response, code="NOT_FOUND", status=404)
