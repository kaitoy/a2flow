from typing import Any

from httpx import Response


def assert_ok(response: Response, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    body = response.json()
    assert body["error"] is None, body
    assert body["meta"]["request_id"]
    return body["data"]


def assert_err(response: Response, code: str, status: int) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert body["data"] is None, body
    assert body["error"]["code"] == code, body
    err: dict[str, Any] = body["error"]
    return err
