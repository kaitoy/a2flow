"""Response envelope middleware that wraps JSON responses in a ``{meta, data, error}`` structure."""

import json
import uuid
from datetime import UTC, datetime
from typing import cast

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import StreamingResponse

from logging_context import request_id_var

EXCLUDED_PATHS = frozenset({"/api/v1/agent", "/api/v1/health"})


def _format_iso_z(dt: datetime) -> str:
    """Format a UTC datetime as an ISO-8601 string with a ``Z`` suffix."""
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ResponseEnvelopeMiddleware(BaseHTTPMiddleware):
    """Wrap every JSON response in a ``{meta, data, error}`` envelope.

    SSE streaming endpoints and the health endpoint are excluded from wrapping.
    HTTP 204 responses are converted to 200 with ``data: null``.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = str(uuid.uuid4())
        received_at = datetime.now(UTC)
        request.state.request_id = request_id
        request.state.received_at = received_at

        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)

        if request.url.path in EXCLUDED_PATHS:
            return response

        content_type = response.headers.get("content-type", "")
        is_json = content_type.startswith("application/json")
        if not is_json and response.status_code != 204:
            return response

        streaming = cast(StreamingResponse, response)
        body_bytes = b""
        async for chunk in streaming.body_iterator:
            if isinstance(chunk, str):
                body_bytes += chunk.encode()
            else:
                body_bytes += bytes(chunk)
        inner = json.loads(body_bytes) if body_bytes else None

        meta = {
            "requestId": request_id,
            "receivedAt": _format_iso_z(received_at),
            "respondedAt": _format_iso_z(datetime.now(UTC)),
        }

        if 200 <= response.status_code < 300:
            envelope = {"meta": meta, "data": inner, "error": None}
            status_code = 200 if response.status_code == 204 else response.status_code
        else:
            envelope = {"meta": meta, "data": None, "error": inner}
            status_code = response.status_code

        new_response = JSONResponse(envelope, status_code=status_code)
        new_response.headers["X-Request-Id"] = request_id
        for key, value in response.headers.items():
            if key.lower() in {"content-length", "content-type"}:
                continue
            new_response.headers.setdefault(key, value)
        return new_response
