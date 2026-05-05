import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import uuid_utils
from sqlalchemy import Index, UniqueConstraint
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import Field, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

DB_URL = os.getenv("DB_URL", "sqlite+aiosqlite:///a2flow.db")


def _engine() -> AsyncEngine:
    return create_async_engine(DB_URL, echo=False)


engine = _engine()


@sa_event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_foreign_keys(dbapi_conn: Any, _: object) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class AgentSkillUpdate(SQLModel):
    name: str | None = None
    repo_url: str | None = None
    repo_path: str | None = None
    description: str | None = None


class AgentSkillCreate(AgentSkillUpdate):
    name: str
    repo_url: str
    repo_path: str = ""


class AgentSkill(AgentSkillCreate, table=True):
    __tablename__ = "agent_skill"
    __table_args__ = (
        UniqueConstraint("name", name="uq_agent_skill_name"),
        Index("ix_agent_skill_name", "name"),
    )
    id: str = Field(
        default_factory=lambda: str(uuid_utils.uuid7()),
        primary_key=True,
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str = Field(default="")
    updated_by: str = Field(default="")


class WorkflowUpdate(SQLModel):
    name: str | None = None
    prompt: str | None = None
    description: str | None = None
    agent_skill_id: str | None = None


class WorkflowCreate(SQLModel):
    name: str
    prompt: str
    description: str | None = None
    agent_skill_id: str


class Workflow(SQLModel, table=True):
    __tablename__ = "workflow"
    __table_args__ = (
        UniqueConstraint("name", name="uq_workflow_name"),
        Index("ix_workflow_name", "name"),
    )
    id: str = Field(
        default_factory=lambda: str(uuid_utils.uuid7()),
        primary_key=True,
    )
    name: str
    prompt: str
    description: str | None = Field(default=None)
    agent_skill_id: str = Field(foreign_key="agent_skill.id", ondelete="RESTRICT")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str = Field(default="")
    updated_by: str = Field(default="")


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(engine) as session:
        yield session
