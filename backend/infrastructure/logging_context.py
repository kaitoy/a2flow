"""Logging configuration and per-request context variables."""

import logging
from contextvars import ContextVar
from datetime import datetime

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class RequestIdFilter(logging.Filter):
    """Inject the current request ID into every log record as ``request_id``."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        return True


class IsoTimeFormatter(logging.Formatter):
    """Format the record time as a timezone-aware ISO-8601 string.

    Renders ``%(asctime)s`` as the local-time, millisecond-precision ISO-8601
    representation including the UTC offset, e.g. ``2026-06-15T14:23:45.123+09:00``.
    """

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created).astimezone()
        return dt.isoformat(timespec="milliseconds")


def setup_logging() -> None:
    """Configure logging so every line carries a timezone-aware timestamp and request ID.

    The root logger is given a single stream handler whose formatter prefixes each
    record with a timezone-aware, millisecond-precision ISO-8601 timestamp and the
    active request ID. uvicorn's own loggers (``uvicorn``, ``uvicorn.error``,
    ``uvicorn.access``) are redirected to propagate through this root handler instead
    of their default, timestamp-less handlers, so uvicorn's startup and access logs
    share the same format. This runs after uvicorn installs its default logging config
    (the app is imported after uvicorn starts), so it reliably overrides it.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(
        IsoTimeFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s [req=%(request_id)s]: %(message)s",
        )
    )
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # Drop uvicorn's own timestamp-less handlers and route its records through root.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
