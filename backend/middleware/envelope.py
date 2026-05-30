"""Per-request context middleware that issues a request ID and records timing.

Each request gets a fresh UUID4 ``request_id`` and the moment it was received
stamped onto ``request.state`` so route dependencies (``ApiMetaDep``) and
exception handlers can build the response envelope's ``ApiMeta`` block. The
request ID is also propagated to ``infrastructure.logging_context.request_id_var`` for log
correlation and echoed back to the client via the ``X-Request-Id`` header.

This file used to wrap every JSON response in the ``{meta, data, error}``
envelope; that responsibility now lives in ``models.response.ApiResponse``
and the routers / exception handlers themselves.
"""

import uuid
from datetime import UTC, datetime

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from infrastructure.logging_context import request_id_var


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Issue a request ID, stamp timing, and expose them via ``request.state``."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.received_at = datetime.now(UTC)

        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)

        response.headers["X-Request-Id"] = request_id
        return response
