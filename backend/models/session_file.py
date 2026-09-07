"""Session file model holding one file attached to a workflow session.

A workflow session -- the chat a :class:`~models.workflow_execution.WorkflowExecution`
runs in -- can carry files: ones a participant attaches from the composer, and ones
the agent writes while working through the run. A :class:`SessionFile` is one such
file, bytes and all.

The bytes live in the database rather than on a shared volume. That is what makes
the two lifetime rules hold without any code to enforce them: the row's
``workflow_execution_id`` is ``ON DELETE CASCADE``, so a file lives exactly as long
as the run it belongs to and disappears with it, and no file is reachable from
another run because every read is filtered by that parent. Files are expected to be
a few megabytes at most (see ``Settings.session_file_max_bytes``); anything larger
belongs in a store of its own.

Only workflow sessions have files. A design session -- the chat a workflow's task
templates are refined in -- has none; if it ever needs them, the dual-parent shape
:class:`~models.message_meta.MessageScope` uses is the one to follow.
"""

from enum import StrEnum

from pydantic.alias_generators import to_camel
from sqlalchemy import ForeignKeyConstraint, Index, LargeBinary, UniqueConstraint
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity
from models.tenant_scoped import TenantScoped

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class SessionFileOrigin(StrEnum):
    """Who put a file into the session.

    Declared user-first because that is the order the two read in: a run starts
    from what its initiator attached, and the agent's own output follows. Enum
    columns sort by declaration position (see ``.claude/rules/api-conventions.md``),
    so this is also the order a listing shows them in.
    """

    user = "user"
    """Uploaded from the chat composer by a session participant."""

    agent = "agent"
    """Written by the agent during a run, through ``write_session_file``."""


class SessionFileCreate(SQLModel):
    """The metadata recorded for a session file, without its bytes."""

    model_config = _alias_config

    workflow_execution_id: str
    """Identifier of the WorkflowExecution whose workflow session holds the file."""

    name: str
    """File name as uploaded or as the agent named it, unique within the session."""

    content_type: str
    """MIME type recorded for the file, for the agent's benefit only.

    Downloads are always served as an attachment under a generic type, so this
    never decides how a browser treats the bytes.
    """

    size_bytes: int
    """Size of the stored file in bytes."""

    origin: SessionFileOrigin
    """Whether a participant uploaded the file or the agent wrote it."""


class SessionFileRead(BaseEntity):
    """Read view of a session file returned by the API and given to the agent.

    Mirrors every column of :class:`SessionFile` **except** ``data``, and that
    omission is the reason this class exists: it is the only shape a session
    file leaves the process in, so a response can never carry the bytes the
    dedicated download route exists to gate.
    """

    model_config = _alias_config
    tenant_id: str
    workflow_execution_id: str
    name: str
    content_type: str
    size_bytes: int
    origin: SessionFileOrigin


class SessionFile(SessionFileCreate, TenantScoped, BaseEntity, table=True):
    """Database-persisted file belonging to one workflow session.

    ``workflow_execution_id`` references the owning run (``ON DELETE CASCADE``),
    so deleting the run removes its files along with its tasks and message
    metadata. ``name`` is unique within that run, which is what lets the agent
    address a file it just wrote by name; a colliding write is renamed rather
    than allowed to overwrite (see :mod:`services.session_file`).

    ``data`` holds the raw bytes and is declared only here, never on
    :class:`SessionFileRead`. The inherited ``created_by`` records who uploaded
    the file, or the user whose run the agent wrote it in.
    """

    __tablename__ = "session_files"
    __table_args__ = (
        UniqueConstraint(
            "workflow_execution_id",
            "name",
            name="uq_session_files_execution_name",
        ),
        Index("ix_session_files_workflow_execution_id", "workflow_execution_id"),
        ForeignKeyConstraint(
            ["workflow_execution_id"],
            ["workflow_executions.id"],
            ondelete="CASCADE",
            name="fk_session_files_workflow_execution_id",
        ),
    )

    data: bytes = Field(sa_type=LargeBinary)
