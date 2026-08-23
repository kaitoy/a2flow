"""Entry point for the dedicated outgoing-email worker process.

Runs the same :func:`services.email_queue_worker.run_email_queue_worker` the API
can host in-process, just with nothing else in the way. A deployment that wants
mail delivery off the request path runs this alongside the API and sets
``EMAIL_WORKER_IN_PROCESS=false`` on the API (see ``compose.yml``).

**This process does not migrate the database.** ``main.py``'s lifespan owns
that, and two processes racing ``alembic upgrade head`` on a fresh database is
not worth the trouble to make safe — so the worker is started only after the API
reports healthy. It also seeds nothing: it reads the settings row the API wrote
and writes only to ``outbound_emails``.

Run it with::

    uv run --no-sync python -m worker
"""

import asyncio
import logging
import signal
from contextlib import suppress

from dotenv import load_dotenv

from infrastructure.logging_context import setup_logging
from services.email_queue_worker import run_email_queue_worker

logger = logging.getLogger(__name__)


def _request_shutdown(task: asyncio.Task[None]) -> None:
    """Ask the worker to stop, so an in-flight batch is not cut off mid-message."""
    logger.info("shutdown requested; stopping the email queue worker")
    task.cancel()


def _install_shutdown_handlers(task: asyncio.Task[None]) -> None:
    """Wire SIGINT/SIGTERM to cancel the worker where the platform allows it.

    ``add_signal_handler`` is POSIX-only; on Windows the same job is done by the
    :class:`KeyboardInterrupt` that reaches :func:`main`.

    Args:
        task: The running worker task to cancel on a signal.
    """
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError, AttributeError, ValueError):
            loop.add_signal_handler(sig, _request_shutdown, task)


async def _run() -> None:
    """Run the worker until a shutdown signal cancels it."""
    task = asyncio.create_task(run_email_queue_worker())
    _install_shutdown_handlers(task)
    with suppress(asyncio.CancelledError):
        await task


def main() -> None:
    """Configure the process and run the worker until it is asked to stop."""
    # Same as main.py: vendor SDKs read some settings straight out of the
    # environment, so .env has to be loaded into os.environ, not only into
    # config.Settings.
    load_dotenv()
    setup_logging()
    logger.info("starting the email queue worker process")
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("email queue worker interrupted; shutting down")
    logger.info("email queue worker process stopped")


if __name__ == "__main__":
    main()
