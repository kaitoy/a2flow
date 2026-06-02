"""FastAPI application entry point for A2Flow.

Configures middleware, exception handlers, and the API router,
then starts the application with Uvicorn when run directly.
"""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from dependencies import APP_NAME
from infrastructure.database import init_db
from infrastructure.logging_context import setup_logging
from middleware.envelope import RequestContextMiddleware
from repositories.exceptions import (
    DependencyCycleError,
    ForeignKeyViolationError,
    NotFoundError,
    QueryValidationError,
    ReferencedError,
)
from routers import api_router
from routers.exception_handlers import (
    dependency_cycle_exception_handler,
    foreign_key_violation_exception_handler,
    http_exception_handler,
    not_found_exception_handler,
    query_validation_exception_handler,
    referenced_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)

load_dotenv()

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize the database schema on application startup."""
    await init_db()
    yield


app = FastAPI(
    title=APP_NAME,
    description="Google ADK agent with SSE streaming",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=3600,
)
app.add_middleware(RequestContextMiddleware)

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(NotFoundError, not_found_exception_handler)
app.add_exception_handler(
    ForeignKeyViolationError, foreign_key_violation_exception_handler
)
app.add_exception_handler(ReferencedError, referenced_exception_handler)
app.add_exception_handler(DependencyCycleError, dependency_cycle_exception_handler)
app.add_exception_handler(QueryValidationError, query_validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.main:app", host=host, port=port, reload=True)
