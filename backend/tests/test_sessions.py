from httpx import AsyncClient


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
    body = response.json()
    assert "session_id" in body
    assert body["user_id"] == "alice"
    assert isinstance(body["last_update_time"], float)


async def test_create_session_with_explicit_id(
    client_with_real_sessions: AsyncClient,
) -> None:
    response = await client_with_real_sessions.post(
        "/sessions", json={"user_id": "alice", "session_id": "my-session-42"}
    )
    assert response.status_code == 201
    assert response.json()["session_id"] == "my-session-42"


async def test_create_session_generates_uuid_when_no_id_given(
    client_with_real_sessions: AsyncClient,
) -> None:
    response = await client_with_real_sessions.post(
        "/sessions", json={"user_id": "alice"}
    )
    session_id = response.json()["session_id"]
    assert len(session_id) == 36
    assert session_id.count("-") == 4


async def test_create_session_missing_user_id_returns_422(
    client_with_real_sessions: AsyncClient,
) -> None:
    response = await client_with_real_sessions.post("/sessions", json={})
    assert response.status_code == 422


async def test_list_sessions_empty_for_new_user(
    client_with_real_sessions: AsyncClient,
) -> None:
    response = await client_with_real_sessions.get(
        "/sessions", params={"user_id": "nobody"}
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_list_sessions_returns_created_sessions(
    client_with_real_sessions: AsyncClient,
) -> None:
    await client_with_real_sessions.post("/sessions", json={"user_id": "bob"})
    await client_with_real_sessions.post("/sessions", json={"user_id": "bob"})
    response = await client_with_real_sessions.get(
        "/sessions", params={"user_id": "bob"}
    )
    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_list_sessions_does_not_mix_users(
    client_with_real_sessions: AsyncClient,
) -> None:
    await client_with_real_sessions.post("/sessions", json={"user_id": "carol"})
    await client_with_real_sessions.post("/sessions", json={"user_id": "dave"})
    carol_sessions = (
        await client_with_real_sessions.get("/sessions", params={"user_id": "carol"})
    ).json()
    dave_sessions = (
        await client_with_real_sessions.get("/sessions", params={"user_id": "dave"})
    ).json()
    assert len(carol_sessions) == 1
    assert len(dave_sessions) == 1
    assert carol_sessions[0]["user_id"] == "carol"
    assert dave_sessions[0]["user_id"] == "dave"


async def test_list_sessions_missing_user_id_returns_422(
    client_with_real_sessions: AsyncClient,
) -> None:
    response = await client_with_real_sessions.get("/sessions")
    assert response.status_code == 422


async def test_get_messages_returns_empty_list_for_new_session(
    client_with_real_sessions: AsyncClient,
) -> None:
    create_resp = await client_with_real_sessions.post(
        "/sessions", json={"user_id": "eve"}
    )
    session_id = create_resp.json()["session_id"]
    response = await client_with_real_sessions.get(
        f"/sessions/{session_id}/messages", params={"user_id": "eve"}
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_get_messages_returns_404_for_unknown_session(
    client_with_real_sessions: AsyncClient,
) -> None:
    response = await client_with_real_sessions.get(
        "/sessions/nonexistent-id/messages", params={"user_id": "eve"}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"


async def test_get_messages_missing_user_id_returns_422(
    client_with_real_sessions: AsyncClient,
) -> None:
    response = await client_with_real_sessions.get("/sessions/some-id/messages")
    assert response.status_code == 422


async def test_delete_session_returns_204(
    client_with_real_sessions: AsyncClient,
) -> None:
    create_resp = await client_with_real_sessions.post(
        "/sessions", json={"user_id": "frank"}
    )
    session_id = create_resp.json()["session_id"]
    response = await client_with_real_sessions.delete(
        f"/sessions/{session_id}", params={"user_id": "frank"}
    )
    assert response.status_code == 204


async def test_delete_session_removes_session_from_list(
    client_with_real_sessions: AsyncClient,
) -> None:
    create_resp = await client_with_real_sessions.post(
        "/sessions", json={"user_id": "grace"}
    )
    session_id = create_resp.json()["session_id"]
    await client_with_real_sessions.delete(
        f"/sessions/{session_id}", params={"user_id": "grace"}
    )
    list_resp = await client_with_real_sessions.get(
        "/sessions", params={"user_id": "grace"}
    )
    assert list_resp.json() == []


async def test_delete_session_returns_404_for_unknown_session(
    client_with_real_sessions: AsyncClient,
) -> None:
    response = await client_with_real_sessions.delete(
        "/sessions/nonexistent-id", params={"user_id": "grace"}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"


async def test_delete_session_missing_user_id_returns_422(
    client_with_real_sessions: AsyncClient,
) -> None:
    response = await client_with_real_sessions.delete("/sessions/some-id")
    assert response.status_code == 422
