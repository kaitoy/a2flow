"""Applies pending Alembic migrations at application startup.

This is the app's "migrate-on-deploy" mechanism: running migrations from the
FastAPI lifespan hook on every startup means redeploying the app is exactly the
event that triggers schema catch-up, and Alembic's ``alembic_version`` tracking
makes repeated runs against an already-current database a no-op.

Several replicas rolling out together all reach this hook at once, and
concurrent runs of the same DDL fail or contend on table locks. ``main.py``'s
lifespan therefore calls this under its startup advisory lock, together with
the seeding that follows, so one replica at a time migrates and seeds.
"""

import asyncio
from pathlib import Path

from alembic.config import Config

from alembic import command

BACKEND_DIR = Path(__file__).resolve().parent.parent


async def run_migrations() -> None:
    """Apply any pending Alembic migrations, run in a worker thread.

    Not safe to run from two processes at once; callers serialize it (see the
    module docstring).

    Alembic's async-template ``env.py`` calls ``asyncio.run(...)``
    internally, which raises if invoked directly from a running event loop
    (as FastAPI's lifespan is). Running the upgrade in a worker thread gives
    it a thread with no running loop, sidestepping that conflict.
    """
    await asyncio.to_thread(_upgrade_to_head)


def _upgrade_to_head() -> None:
    """Run ``alembic upgrade head`` synchronously against ``alembic.ini``.

    ``configure_logger`` tells ``alembic/env.py`` to leave logging alone. The
    app configured it at import (``logging_context.setup_logging``), and
    ``env.py``'s default ``fileConfig()`` call would disable every existing
    logger and replace root's handler with ``alembic.ini``'s, so the app would
    log nothing for the rest of the process. The Alembic CLI passes no
    attributes, so a standalone ``alembic upgrade head`` still configures
    logging from the ini as usual.
    """
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
