import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from dependencies import APP_NAME
from exception_handlers import (
    foreign_key_violation_exception_handler,
    http_exception_handler,
    not_found_exception_handler,
    referenced_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from logging_context import setup_logging
from middleware.envelope import ResponseEnvelopeMiddleware
from repositories.exceptions import (
    ForeignKeyViolationError,
    NotFoundError,
    ReferencedError,
)
from routers import agent, agent_skills, health, sessions, workflows

load_dotenv()

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
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
)
app.add_middleware(ResponseEnvelopeMiddleware)

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(NotFoundError, not_found_exception_handler)
app.add_exception_handler(
    ForeignKeyViolationError, foreign_key_violation_exception_handler
)
app.add_exception_handler(ReferencedError, referenced_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(agent.router)
app.include_router(agent_skills.router)
app.include_router(sessions.router)
app.include_router(workflows.router)
app.include_router(health.router)


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.main:app", host=host, port=port, reload=True)
