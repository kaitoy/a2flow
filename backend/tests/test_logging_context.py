import logging

from infrastructure.logging_context import HEALTH_CHECK_PATH, HealthCheckAccessFilter


def _access_record(full_path: str) -> logging.LogRecord:
    """Build a record shaped like uvicorn's access log call: ``'%s - "%s %s HTTP/%s" %d'``."""
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:1234", "GET", full_path, "1.1", 200),
        exc_info=None,
    )


def test_health_check_access_is_dropped() -> None:
    assert HealthCheckAccessFilter().filter(_access_record(HEALTH_CHECK_PATH)) is False


def test_health_check_access_with_query_string_is_dropped() -> None:
    record = _access_record(f"{HEALTH_CHECK_PATH}?foo=bar")
    assert HealthCheckAccessFilter().filter(record) is False


def test_other_route_access_is_kept() -> None:
    assert HealthCheckAccessFilter().filter(_access_record("/api/v1/sessions")) is True


def test_record_without_access_log_args_is_kept() -> None:
    record = logging.LogRecord(
        name="uvicorn.error",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg="Application startup complete.",
        args=(),
        exc_info=None,
    )
    assert HealthCheckAccessFilter().filter(record) is True
