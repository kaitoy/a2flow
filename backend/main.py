"""FastAPI application entry point for A2Flow.

Configures middleware, exception handlers, and the API router,
then starts the application with Uvicorn when run directly.
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from dependencies import APP_NAME
from infrastructure.bootstrap import (
    apply_system_settings_env_overrides,
    seed_default_tenant_and_admin_user,
    seed_root_user,
    seed_system_settings,
    seed_system_user,
)
from infrastructure.database import engine
from infrastructure.demo_data import sync_demo_data
from infrastructure.logging_context import setup_logging
from infrastructure.migrations import run_migrations
from middleware.envelope import RequestContextMiddleware
from models.user import SYSTEM_USER_ID
from repositories.exceptions import (
    ApprovalAlreadyResolvedError,
    AvatarValidationError,
    CsrfError,
    DependencyCycleError,
    EmailSendError,
    ForbiddenError,
    ForeignKeyViolationError,
    McpConnectionError,
    McpServerValidationError,
    NotFoundError,
    QueryValidationError,
    ReferencedError,
    RegistryUnavailableError,
    SecretResolutionError,
    SecretValidationError,
    SessionRunInProgressError,
    SkillCloneError,
    SkillNotReadyError,
    SummarizationFailedError,
    SystemSettingsValidationError,
    UnauthorizedError,
    UniqueViolationError,
    UserValidationError,
    WorkflowDescriptionNotGeneratableError,
    WorkflowNotDeactivatableError,
    WorkflowNotModifiedError,
    WorkflowNotRunnableError,
)
from routers import api_router
from routers.exception_handlers import (
    approval_already_resolved_exception_handler,
    avatar_validation_exception_handler,
    csrf_exception_handler,
    dependency_cycle_exception_handler,
    email_send_exception_handler,
    forbidden_exception_handler,
    foreign_key_violation_exception_handler,
    http_exception_handler,
    mcp_connection_exception_handler,
    mcp_server_validation_exception_handler,
    not_found_exception_handler,
    query_validation_exception_handler,
    referenced_exception_handler,
    registry_unavailable_exception_handler,
    secret_resolution_exception_handler,
    secret_validation_exception_handler,
    session_run_in_progress_exception_handler,
    skill_clone_exception_handler,
    skill_not_ready_exception_handler,
    summarization_failed_exception_handler,
    system_settings_validation_exception_handler,
    unauthorized_exception_handler,
    unhandled_exception_handler,
    unique_violation_exception_handler,
    user_validation_exception_handler,
    validation_exception_handler,
    workflow_description_not_generatable_exception_handler,
    workflow_not_deactivatable_exception_handler,
    workflow_not_modified_exception_handler,
    workflow_not_runnable_exception_handler,
)
from services.agent_skill_sync import sync_agent_skill

# Populates os.environ from backend/.env so vendor SDKs (litellm, google-genai)
# that read GOOGLE_API_KEY/OPENAI_API_KEY/ANTHROPIC_API_KEY/AWS_BEARER_TOKEN_BEDROCK
# straight out of the environment still see them. config.Settings loads the
# same file independently for A2Flow's own typed configuration below.
load_dotenv()

setup_logging()

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Apply pending migrations, seed the baseline users and settings, and sync the demo data.

    Seeds the system, root, and Default-tenant admin users and the singleton
    system-settings row, applies any ``APP_BASE_URL``/``SMTP_*`` environment
    overrides onto that row, then registers or removes the optional demo
    dataset depending on ``DEMO_DATA``. A demo agent skill registered by this
    run still needs its repository cloned; that runs as a background task
    rather than inline, so a slow or unreachable remote delays nothing
    (``sync_agent_skill`` records every failure on the skill row itself).
    """
    await run_migrations()
    # Holds a strong reference to the clone task for as long as the
    # application runs, so it cannot be garbage-collected mid-flight.
    background: set[asyncio.Task[None]] = set()
    async with AsyncSession(engine) as session:
        await seed_system_user(session)
        await seed_system_settings(session)
        await apply_system_settings_env_overrides(session)
        # seed_root_user's skip check ("any real user exists") must run
        # before seed_default_tenant_and_admin_user creates its own real
        # user, or root would never be seeded on a fresh database. The demo
        # users are real users too, so sync_demo_data comes after both.
        await seed_root_user(session)
        await seed_default_tenant_and_admin_user(session)
        demo_skill_id = await sync_demo_data(session)
    if demo_skill_id is not None:
        clone = asyncio.create_task(
            sync_agent_skill(demo_skill_id, user_id=SYSTEM_USER_ID)
        )
        background.add(clone)
        clone.add_done_callback(background.discard)
    yield


app = FastAPI(
    title=APP_NAME,
    description="Google ADK agent with SSE streaming",
    lifespan=lifespan,
)


def _validate_cors_origins(origins: list[str]) -> None:
    """Raise if ``origins`` combines a wildcard with credentialed CORS requests.

    ``allow_credentials=True`` is unconditional below, and the CORS spec
    forbids pairing a wildcard origin with credentialed requests — browsers
    enforce this, but not every non-browser client does, so a wildcard here
    would silently disable the origin check for those callers. Fail at import
    time instead of shipping that misconfiguration.
    """
    if "*" in origins:
        raise ValueError(
            "CORS_ORIGINS must not include '*' because allow_credentials=True "
            "is enabled; list explicit origins instead."
        )


_cors_origins = settings.cors_origins
_validate_cors_origins(_cors_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
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
app.add_exception_handler(
    SessionRunInProgressError, session_run_in_progress_exception_handler
)
app.add_exception_handler(UniqueViolationError, unique_violation_exception_handler)
app.add_exception_handler(DependencyCycleError, dependency_cycle_exception_handler)
app.add_exception_handler(McpConnectionError, mcp_connection_exception_handler)
app.add_exception_handler(SkillCloneError, skill_clone_exception_handler)
app.add_exception_handler(SkillNotReadyError, skill_not_ready_exception_handler)
app.add_exception_handler(
    WorkflowNotRunnableError, workflow_not_runnable_exception_handler
)
app.add_exception_handler(
    ApprovalAlreadyResolvedError, approval_already_resolved_exception_handler
)
app.add_exception_handler(
    WorkflowNotModifiedError, workflow_not_modified_exception_handler
)
app.add_exception_handler(
    WorkflowNotDeactivatableError, workflow_not_deactivatable_exception_handler
)
app.add_exception_handler(
    WorkflowDescriptionNotGeneratableError,
    workflow_description_not_generatable_exception_handler,
)
app.add_exception_handler(
    SummarizationFailedError, summarization_failed_exception_handler
)
app.add_exception_handler(
    RegistryUnavailableError, registry_unavailable_exception_handler
)
app.add_exception_handler(QueryValidationError, query_validation_exception_handler)
app.add_exception_handler(AvatarValidationError, avatar_validation_exception_handler)
app.add_exception_handler(SecretValidationError, secret_validation_exception_handler)
app.add_exception_handler(
    McpServerValidationError, mcp_server_validation_exception_handler
)
app.add_exception_handler(UserValidationError, user_validation_exception_handler)
app.add_exception_handler(
    SystemSettingsValidationError, system_settings_validation_exception_handler
)
app.add_exception_handler(EmailSendError, email_send_exception_handler)
app.add_exception_handler(SecretResolutionError, secret_resolution_exception_handler)
app.add_exception_handler(UnauthorizedError, unauthorized_exception_handler)
app.add_exception_handler(CsrfError, csrf_exception_handler)
app.add_exception_handler(ForbiddenError, forbidden_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn

    # log_config=None keeps uvicorn from re-applying its default logging config
    # after import, so the timestamped setup from setup_logging() stays in effect.
    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_config=None,
    )
