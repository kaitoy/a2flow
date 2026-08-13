"""Request-scoped FastAPI dependencies and the application name constant.

Holds the lightweight, per-request dependencies: the response metadata block,
pagination/sort/filter query parameters, and the current user id resolved from
the authenticated session (via :func:`dependencies.auth.get_current_user`).
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Query, Request

from models.response import ApiMeta
from repositories.exceptions import QueryValidationError
from repositories.query import FILTER_OPERATORS, FilterSpec, SortSpec

APP_NAME = "A2Flow"


def build_api_meta(request: Request) -> ApiMeta:
    """Construct the ``ApiMeta`` block for the current request.

    Reads ``request_id`` and ``received_at`` from ``request.state`` (populated
    by ``RequestContextMiddleware``) and stamps ``responded_at`` with the
    current UTC time at the moment the dependency is resolved.
    """
    return ApiMeta(
        request_id=request.state.request_id,
        received_at=request.state.received_at,
        responded_at=datetime.now(UTC),
    )


ApiMetaDep = Annotated[ApiMeta, Depends(build_api_meta)]


@dataclass
class PaginationParams:
    """Query parameters for paginated list endpoints."""

    limit: int = Query(default=20, ge=1, le=1000)
    offset: int = Query(default=0, ge=0)


PaginationDep = Annotated[PaginationParams, Depends(PaginationParams)]


#: Default span, in days, of a metrics window when the caller names no bounds.
_DEFAULT_METRICS_WINDOW_DAYS = 30

#: Longest span, in days, a metrics window may cover. The aggregate endpoints
#: read every row in the window and fold it in Python, so an unbounded span is
#: an unbounded query; a year is far beyond what an operations dashboard plots.
_MAX_METRICS_WINDOW_DAYS = 366


@dataclass
class MetricsWindowParams:
    """Resolved ``[since, until)`` bounds for an aggregate metrics endpoint.

    Both bounds are optional on the wire: ``until`` defaults to now and
    ``since`` to 30 days before it, so the common case needs no query string at
    all.
    """

    since: datetime
    until: datetime


def _as_utc(value: datetime | None) -> datetime | None:
    """Attach UTC to a naive datetime, passing through aware values and ``None``.

    Args:
        value: A bound parsed from the query string, or ``None`` when absent.

    Returns:
        The timezone-aware equivalent, or ``None``.
    """
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def parse_metrics_window(
    since: Annotated[
        datetime | None,
        Query(
            description=(
                "Inclusive start of the window (ISO-8601). Defaults to 30 days "
                "before 'until'."
            ),
        ),
    ] = None,
    until: Annotated[
        datetime | None,
        Query(
            description=(
                "Exclusive end of the window (ISO-8601). Defaults to the current time."
            ),
        ),
    ] = None,
) -> MetricsWindowParams:
    """Resolve the ``since``/``until`` query parameters into a concrete window.

    Naive datetimes are read as UTC, matching how the API serializes every other
    timestamp.

    Raises:
        QueryValidationError: If ``since`` is not before ``until``, or the span
            exceeds :data:`_MAX_METRICS_WINDOW_DAYS`.
    """
    end = _as_utc(until) or datetime.now(UTC)
    start = _as_utc(since) or end - timedelta(days=_DEFAULT_METRICS_WINDOW_DAYS)
    if start >= end:
        raise QueryValidationError("'since' must be earlier than 'until'")
    if end - start > timedelta(days=_MAX_METRICS_WINDOW_DAYS):
        raise QueryValidationError(
            f"window must not exceed {_MAX_METRICS_WINDOW_DAYS} days"
        )
    return MetricsWindowParams(since=start, until=end)


MetricsWindowDep = Annotated[MetricsWindowParams, Depends(parse_metrics_window)]

#: Default waiting time, in hours, past which a pending approval counts as
#: stalled. 24 hours is the figure the operations view highlights.
_DEFAULT_BACKLOG_THRESHOLD_HOURS = 24.0


@dataclass
class BacklogThresholdParams:
    """The stalled-approval threshold for an approval-backlog endpoint."""

    threshold_hours: float = Query(
        default=_DEFAULT_BACKLOG_THRESHOLD_HOURS,
        alias="thresholdHours",
        gt=0,
        le=8760,
        description=(
            "Hours a pending approval must have been waiting to count toward "
            "'overThreshold'."
        ),
    )


BacklogThresholdDep = Annotated[BacklogThresholdParams, Depends(BacklogThresholdParams)]


@dataclass
class SortParams:
    """Parsed sort instructions for a list endpoint.

    Carries the ordered :class:`SortSpec` list extracted from the ``s`` query
    parameter; field names are validated against the model in the repository.
    """

    sort: list[SortSpec] = field(default_factory=list)


def parse_sort(
    s: Annotated[
        str | None,
        Query(
            description=(
                "Comma-separated sort fields (camelCase); prefix a field with "
                "'-' for descending order, e.g. '-createdAt,name'."
            ),
        ),
    ] = None,
) -> SortParams:
    """Parse the ``s`` query parameter into a :class:`SortParams`.

    Each comma-separated token is one field; a leading ``-`` marks descending
    order. Field-name validation is deferred to the repository, which knows the
    target model.
    """
    if not s:
        return SortParams()
    specs: list[SortSpec] = []
    for token in s.split(","):
        name = token.strip()
        if not name:
            continue
        descending = name.startswith("-")
        specs.append(SortSpec(field=name.lstrip("-"), descending=descending))
    return SortParams(sort=specs)


SortDep = Annotated[SortParams, Depends(parse_sort)]


@dataclass
class FilterParams:
    """Parsed filter instructions for a list endpoint.

    Carries the :class:`FilterSpec` list extracted from the repeatable ``q``
    query parameter; field names and value types are validated against the model
    in the repository.
    """

    filters: list[FilterSpec] = field(default_factory=list)


def parse_filters(
    q: Annotated[
        list[str] | None,
        Query(
            description=(
                "Filter as 'field:op:value' (field in camelCase). Repeatable. "
                "Operators: eq, ne, lt, lte, gt, gte, like, in. "
                "Example: 'name:like:foo'."
            ),
        ),
    ] = None,
) -> FilterParams:
    """Parse the repeatable ``q`` query parameter into a :class:`FilterParams`.

    Validates the ``field:op:value`` shape and the operator name here (both
    model-independent); field-name resolution and value coercion happen in the
    repository.

    Raises:
        QueryValidationError: If a term is not exactly ``field:op:value`` or its
            operator is not recognized.
    """
    if not q:
        return FilterParams()
    specs: list[FilterSpec] = []
    for term in q:
        parts = term.split(":", 2)
        if len(parts) != 3:
            raise QueryValidationError(
                f"Invalid filter {term!r}; expected 'field:op:value'"
            )
        name, op, value = parts
        if op not in FILTER_OPERATORS:
            raise QueryValidationError(f"Unknown operator {op!r} in filter {term!r}")
        specs.append(FilterSpec(field=name, op=op, value=value))
    return FilterParams(filters=specs)


FilterDep = Annotated[FilterParams, Depends(parse_filters)]
