"""Shared helpers that apply sort and filter specs to SQLModel statements.

The HTTP layer parses the raw ``s`` (sort) and ``q`` (filter) query parameters
into :class:`SortSpec` / :class:`FilterSpec` value objects. Those carry
camelCase field names exactly as the client sent them; this module is the only
place that knows the concrete SQLModel entity, so field-name resolution and
value coercion against the model's columns happen here. Anything malformed
raises :class:`~repositories.exceptions.QueryValidationError`, which the API maps
to HTTP 400.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import TypeAdapter, ValidationError
from pydantic.alias_generators import to_camel
from sqlmodel import SQLModel, col
from sqlmodel.sql.expression import SelectOfScalar

from repositories.exceptions import QueryValidationError

#: Filter operators accepted in the ``field:op:value`` query syntax.
FILTER_OPERATORS: frozenset[str] = frozenset(
    {"eq", "ne", "lt", "lte", "gt", "gte", "like", "in"}
)


@dataclass(frozen=True)
class SortSpec:
    """A single sort instruction: a camelCase field name and its direction."""

    field: str
    descending: bool


@dataclass(frozen=True)
class FilterSpec:
    """A single filter instruction parsed from ``field:op:value``."""

    field: str
    op: str
    value: str


def _resolve_column(model: type[SQLModel], camel_field: str) -> str:
    """Resolve a camelCase query field name to the model's Python attribute name.

    Accepts either the camelCase alias (e.g. ``createdAt``) or the raw snake_case
    attribute name (e.g. ``created_at``).

    Args:
        model: The SQLModel entity the query targets.
        camel_field: The field name as supplied by the client.

    Returns:
        The Python attribute name of the matching column.

    Raises:
        QueryValidationError: If no column matches the given name.
    """
    for name in model.model_fields:
        if camel_field in (to_camel(name), name):
            return name
    raise QueryValidationError(f"Unknown field {camel_field!r}")


def _coerce(model: type[SQLModel], py_field: str, raw: str) -> Any:
    """Coerce a raw string value to the Python type of the model's field.

    Args:
        model: The SQLModel entity the query targets.
        py_field: The resolved Python attribute name of the column.
        raw: The raw string value from the query.

    Returns:
        The value converted to the field's declared type.

    Raises:
        QueryValidationError: If the value cannot be coerced to the field type.
    """
    annotation = model.model_fields[py_field].annotation
    try:
        return TypeAdapter(annotation).validate_python(raw)
    except ValidationError as exc:
        raise QueryValidationError(
            f"Invalid value {raw!r} for field {to_camel(py_field)!r}"
        ) from exc


def apply_sort(
    stmt: SelectOfScalar[Any],
    model: type[SQLModel],
    specs: Sequence[SortSpec],
    *,
    default: Sequence[Any],
) -> SelectOfScalar[Any]:
    """Apply sort specs to a select statement, falling back to a default order.

    Args:
        stmt: The select statement to order.
        model: The SQLModel entity being queried.
        specs: The requested sort instructions; empty means use ``default``.
        default: The order-by expressions to apply when ``specs`` is empty
            (e.g. ``col(Workflow.created_at).desc()``).

    Returns:
        The statement with an ``ORDER BY`` clause applied.

    Raises:
        QueryValidationError: If a spec references an unknown field.
    """
    if not specs:
        return stmt.order_by(*default)
    order_by = []
    for spec in specs:
        column = col(getattr(model, _resolve_column(model, spec.field)))
        order_by.append(column.desc() if spec.descending else column.asc())
    return stmt.order_by(*order_by)


def apply_filters(
    stmt: SelectOfScalar[Any],
    model: type[SQLModel],
    specs: Sequence[FilterSpec],
) -> SelectOfScalar[Any]:
    """Apply filter specs to a select statement as ``WHERE`` clauses.

    Args:
        stmt: The select statement to filter.
        model: The SQLModel entity being queried.
        specs: The requested filter instructions.

    Returns:
        The statement with the filter conditions applied.

    Raises:
        QueryValidationError: If a spec references an unknown field, uses an
            unknown operator, or carries an uncoercible value.
    """
    for spec in specs:
        if spec.op not in FILTER_OPERATORS:
            raise QueryValidationError(f"Unknown operator {spec.op!r}")
        py_field = _resolve_column(model, spec.field)
        column = col(getattr(model, py_field))
        if spec.op == "like":
            stmt = stmt.where(column.ilike(f"%{spec.value}%"))
        elif spec.op == "in":
            values = [_coerce(model, py_field, v) for v in spec.value.split(",")]
            stmt = stmt.where(column.in_(values))
        else:
            value = _coerce(model, py_field, spec.value)
            stmt = stmt.where(_COMPARATORS[spec.op](column, value))
    return stmt


#: Maps comparison operators to the corresponding SQLAlchemy column expression.
_COMPARATORS = {
    "eq": lambda c, v: c == v,
    "ne": lambda c, v: c != v,
    "lt": lambda c, v: c < v,
    "lte": lambda c, v: c <= v,
    "gt": lambda c, v: c > v,
    "gte": lambda c, v: c >= v,
}
