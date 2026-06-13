"""LRU-cached singleton dependencies for ADK and skill management services.

Provides process-wide singletons (ADK session service, agent registry, skill
manager) created lazily on first resolution and cached for the lifetime of the
process. Tests override the underlying factory functions via
``app.dependency_overrides``.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from google.adk.sessions import BaseSessionService

from infrastructure.agent import AgentRegistry
from infrastructure.database import ASYNC_DB_URL, DB_URL, is_sqlite_url
from infrastructure.session_service import (
    StaleTolerantDatabaseSessionService,
    StaleTolerantSqliteSessionService,
)
from infrastructure.skill_manager import SkillManager

from .context import APP_NAME


@lru_cache(maxsize=1)
def get_session_service() -> BaseSessionService:
    """Return the LRU-cached ADK session service singleton.

    SQLite ``DB_URL``s keep the aiosqlite-based service; any other database
    (e.g. PostgreSQL) uses the SQLAlchemy-based service with the async-driver
    URL, so the ADK session store always lives in the same database as the
    REST API data.
    """
    if is_sqlite_url(DB_URL):
        return StaleTolerantSqliteSessionService(DB_URL)
    return StaleTolerantDatabaseSessionService(ASYNC_DB_URL)


@lru_cache(maxsize=1)
def get_agent_registry() -> AgentRegistry:
    """Return the LRU-cached agent registry singleton."""
    return AgentRegistry(
        session_service=get_session_service(),
        app_name=APP_NAME,
    )


@lru_cache(maxsize=1)
def get_skill_manager() -> SkillManager:
    """Return the LRU-cached SkillManager singleton, reading SKILLS_CACHE_DIR from env."""
    cache_dir = Path(
        os.getenv(
            "SKILLS_CACHE_DIR",
            str(Path(__file__).parent.parent / ".skills_cache"),
        )
    )
    return SkillManager(cache_dir=cache_dir)


SessionServiceDep = Annotated[BaseSessionService, Depends(get_session_service)]
AgentRegistryDep = Annotated[AgentRegistry, Depends(get_agent_registry)]
SkillManagerDep = Annotated[SkillManager, Depends(get_skill_manager)]
