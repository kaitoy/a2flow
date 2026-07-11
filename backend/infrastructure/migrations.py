"""Applies pending Alembic migrations at application startup.

This is the app's "migrate-on-deploy" mechanism: since a deploy of this
project is a single-container restart (no rolling multi-replica rollout),
running migrations from the FastAPI lifespan hook on every startup is both
sufficient and simple — redeploying the app is exactly the event that
should trigger schema catch-up, and Alembic's ``alembic_version`` tracking
makes repeated runs against an already-current database a no-op.
"""

import asyncio
from pathlib import Path

from alembic.config import Config

from alembic import command

BACKEND_DIR = Path(__file__).resolve().parent.parent


async def run_migrations() -> None:
    """Apply any pending Alembic migrations, run in a worker thread.

    Alembic's async-template ``env.py`` calls ``asyncio.run(...)``
    internally, which raises if invoked directly from a running event loop
    (as FastAPI's lifespan is). Running the upgrade in a worker thread gives
    it a thread with no running loop, sidestepping that conflict.
    """
    await asyncio.to_thread(_upgrade_to_head)


def _upgrade_to_head() -> None:
    """Run ``alembic upgrade head`` synchronously against ``alembic.ini``."""
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    command.upgrade(cfg, "head")
