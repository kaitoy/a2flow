from datetime import datetime

from httpx import AsyncClient

from tests._envelope import assert_err, assert_ok


async def test_create_session_returns_201(
    client_with_real_sessions: AsyncClient,
) -> None:
    response = await client_with_real_sessions.post(
        "/sessions", json={"user_id": "alice"}
    )
    assert response.status_code == 201


async def test_create_session_response_shape(
    client_with_real_sessions: AsyncClient,
) -> None:
    response = await client_with_real_sessions.post(
        "/sessions", json={"user_id": "alice"}
    )
    body = assert_ok(response, status=201)
    assert "id" in body
    assert body["userId"] == "alice"
    assert isinstance(body["lastUpdateTime"], str)
    datetime.fromisoformat(body["lastUpdateTime"])


async def test_create_session_with_explicit_id(
    client_with_real_sessions: AsyncClient,
) -> None:
    response = await client_with_real_sessions.post(
        "/sessions", json={"user_id": "alice", "id": "my-session-42"}
    )
    body = assert_ok(response, status=201)
    assert body["id"] == "my-session-42"


async def test_create_session_generates_uuid_when_no_id_given(
    client_with_real_sessions: AsyncClient,
) -> None:
    response = await client_with_real_sessions.post(
        "/sessions", json={"user_id": "alice"}
    )
    session_id = assert_ok(response, status=201)["id"]
    assert len(session_id) == 36
    assert session_id.count("-") == 4


async def test_create_session_missing_user_id_returns_422(
    client_with_real_sessions: AsyncClient,
) -> None:
    response = await client_with_real_sessions.post("/sessions", json={})
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_list_sessions_empty_for_new_user(
    client_with_real_sessions: AsyncClient,
) -> None:
    response = await client_with_real_sessions.get(
        "/sessions", params={"user_id": "nobody"}
    )
    assert assert_ok(response) == []


async def test_list_sessions_returns_created_sessions(
    client_with_real_sessions: AsyncClient,
) -> None:
    await client_with_real_sessions.post("/sessions", json={"user_id": "bob"})
    await client_with_real_sessions.post("/sessions", json={"user_id": "bob"})
    response = await client_with_real_sessions.get(
        "/sessions", params={"user_id": "bob"}
    )
    assert len(assert_ok(response)) == 2


async def test_list_sessions_does_not_mix_users(
    client_with_real_sessions: AsyncClient,
) -> None:
    await client_with_real_sessions.post("/sessions", json={"user_id": "carol"})
    await client_with_real_sessions.post("/sessions", json={"user_id": "dave"})
    carol_sessions = assert_ok(
        await client_with_real_sessions.get("/sessions", params={"user_id": "carol"})
    )
    dave_sessions = assert_ok(
        await client_with_real_sessions.get("/sessions", params={"user_id": "dave"})
    )
    assert len(carol_sessions) == 1
    assert len(dave_sessions) == 1
    assert carol_sessions[0]["userId"] == "carol"
    assert dave_sessions[0]["userId"] == "dave"


async def test_list_sessions_missing_user_id_returns_422(
    client_with_real_sessions: AsyncClient,
) -> None:
    response = await client_with_real_sessions.get("/sessions")
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_get_messages_returns_empty_list_for_new_session(
    client_with_real_sessions: AsyncClient,
) -> None:
    create_resp = await client_with_real_sessions.post(
        "/sessions", json={"user_id": "eve"}
    )
    session_id = assert_ok(create_resp, status=201)["id"]
    response = await client_with_real_sessions.get(
        f"/sessions/{session_id}/messages", params={"user_id": "eve"}
    )
    assert assert_ok(response) == []


async def test_get_messages_returns_404_for_unknown_session(
    client_with_real_sessions: AsyncClient,
) -> None:
    response = await client_with_real_sessions.get(
        "/sessions/nonexistent-id/messages", params={"user_id": "eve"}
    )
    err = assert_err(response, code="NOT_FOUND", status=404)
    assert err["details"]["entity"] == "Session"


async def test_get_messages_missing_user_id_returns_422(
    client_with_real_sessions: AsyncClient,
) -> None:
    response = await client_with_real_sessions.get("/sessions/some-id/messages")
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_delete_session_returns_200(
    client_with_real_sessions: AsyncClient,
) -> None:
    create_resp = await client_with_real_sessions.post(
        "/sessions", json={"user_id": "frank"}
    )
    session_id = assert_ok(create_resp, status=201)["id"]
    response = await client_with_real_sessions.delete(
        f"/sessions/{session_id}", params={"user_id": "frank"}
    )
    assert assert_ok(response, status=200) is None


async def test_delete_session_removes_session_from_list(
    client_with_real_sessions: AsyncClient,
) -> None:
    create_resp = await client_with_real_sessions.post(
        "/sessions", json={"user_id": "grace"}
    )
    session_id = assert_ok(create_resp, status=201)["id"]
    await client_with_real_sessions.delete(
        f"/sessions/{session_id}", params={"user_id": "grace"}
    )
    list_resp = await client_with_real_sessions.get(
        "/sessions", params={"user_id": "grace"}
    )
    assert assert_ok(list_resp) == []


async def test_delete_session_returns_404_for_unknown_session(
    client_with_real_sessions: AsyncClient,
) -> None:
    response = await client_with_real_sessions.delete(
        "/sessions/nonexistent-id", params={"user_id": "grace"}
    )
    assert_err(response, code="NOT_FOUND", status=404)


async def test_delete_session_missing_user_id_returns_422(
    client_with_real_sessions: AsyncClient,
) -> None:
    response = await client_with_real_sessions.delete("/sessions/some-id")
    assert_err(response, code="VALIDATION_ERROR", status=422)
