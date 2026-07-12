"""Health check router."""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from dependencies import DBSessionDep

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health(db: DBSessionDep) -> JSONResponse:
    """Return 200 if the database is reachable, 503 otherwise.

    Used by orchestrators/load balancers for both liveness and readiness
    gating. Returns a response instead of raising so a failed check produces
    a definitive status code rather than a 500 with a stack trace in the
    body. Access to this route is excluded from the uvicorn access log (see
    ``infrastructure.logging_context``) since it's polled frequently.
    """
    try:
        # session.exec() doesn't accept a raw text() clause (only Select /
        # SelectOfScalar / UpdateBase), so this intentionally uses the
        # deprecated execute() passthrough instead.
        await db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.warning("Health check failed: database unreachable", exc_info=True)
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return JSONResponse(status_code=200, content={"status": "ok"})
