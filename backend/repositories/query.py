"""Shared helpers that apply sort and filter specs to SQLModel statements.

The HTTP layer parses the raw ``s`` (sort) and ``q`` (filter) query parameters
into :class:`SortSpec` / :class:`FilterSpec` value objects. Those carry
camelCase field names exactly as the client sent them; this module is the only
place that knows the concrete SQLModel entity, so field-name resolution and
value coercion against the model's columns happen here. Anything malformed
raises :class:`~repositories.exceptions.QueryValidationError`, which the API maps
to HTTP 400.

Every call site must also declare ``readable``, the schema it will actually
serialize results as. :func:`_resolve_column` only resolves a field present on
both the table model and ``readable``, so a column intentionally excluded from
the response (e.g. ``User.password``, a bcrypt hash; ``Secret.entries``,
Fernet ciphertext) can never become filterable, sortable, or a boolean-oracle
side channel -- even though its value is never returned directly. A hidden
field is reported as unknown, identically to a field that does not exist at
all, so a client cannot distinguish "hidden" from "nonexistent".

A call site whose response does not come straight off the model's own columns
passes ``columns``, a map of :class:`ColumnOverride` keyed by resolved attribute
name, so that filtering and sorting evaluate the same value the caller will see.
Two use it today, both in the workflow read path: a non-``developer`` sees a
``modified`` workflow's published snapshot rather than its live row, and the
snapshot's task templates live inside a JSON column rather than in table rows.
Filtering must never fall back to doing the work in Python -- that would break
pagination and let the two implementations drift apart.
"""

from collections.abc import Mapping, Sequence
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


@dataclass(frozen=True)
class ColumnOverride:
    """A SQL expression to evaluate a field with, in place of the model's column.

    Attributes:
        expression: The expression to filter and sort on. It must yield the
            value the caller will serialize for that field, or the page a
            client sees will not match what it searched for.
        json_text: Whether ``expression`` reads out of a JSON column, and so
            yields the value as the text pydantic wrote there. When set, the
            filter value is put through the same JSON serialization before it
            is compared, which makes the comparison textual on every dialect:
            a ``datetime`` becomes the same fixed-width ISO-8601 UTC string it
            was stored as, whose lexicographic order is chronological order. No
            cast and no dialect-specific date function is needed -- mirroring
            the rule ``repositories.metrics`` states for its own queries.
    """

    expression: Any
    json_text: bool = False


def _resolve_column(
    model: type[SQLModel], camel_field: str, *, readable: type[SQLModel]
) -> str:
    """Resolve a camelCase query field name to the model's Python attribute name.

    Accepts either the camelCase alias (e.g. ``createdAt``) or the raw snake_case
    attribute name (e.g. ``created_at``). Only a field present on **both**
    ``model`` and ``readable`` can resolve: ``readable`` is the schema the
    caller will actually serialize results as, and a field the table model
    carries but ``readable`` omits must never be filterable or sortable --
    doing so would let a client reconstruct the value by observing which rows
    match or how they sort, without the value ever being returned directly (a
    blind boolean-oracle side channel). Such a field is reported as unknown,
    identically to a field that does not exist at all.

    Args:
        model: The SQLModel entity the query targets.
        camel_field: The field name as supplied by the client.
        readable: The schema the caller will serialize results as. Pass
            ``model`` itself when the table class doubles as the response
            model.

    Returns:
        The Python attribute name of the matching column.

    Raises:
        QueryValidationError: If no column matches the given name on both
            ``model`` and ``readable``.
    """
    for name in model.model_fields:
        if name not in readable.model_fields:
            continue
        if camel_field in (to_camel(name), name):
            return name
    raise QueryValidationError(f"Unknown field {camel_field!r}")


def _expression_for(
    model: type[SQLModel],
    py_field: str,
    columns: Mapping[str, ColumnOverride] | None,
) -> Any:
    """Return the expression a resolved field should be evaluated with.

    Args:
        model: The SQLModel entity the query targets.
        py_field: The resolved Python attribute name of the column.
        columns: Per-field overrides, or ``None`` to use the model's columns.

    Returns:
        The override's expression when one is declared, else the model column.
    """
    override = columns.get(py_field) if columns is not None else None
    if override is not None:
        return override.expression
    return col(getattr(model, py_field))


def _coerce(
    model: type[SQLModel], py_field: str, raw: str, *, json_text: bool = False
) -> Any:
    """Coerce a raw string value to the Python type of the model's field.

    Args:
        model: The SQLModel entity the query targets.
        py_field: The resolved Python attribute name of the column.
        raw: The raw string value from the query.
        json_text: Whether to return the value as pydantic's JSON serialization
            of it, rather than the Python object -- see
            :attr:`ColumnOverride.json_text`.

    Returns:
        The value converted to the field's declared type, or to the JSON text
        that type is stored as.

    Raises:
        QueryValidationError: If the value cannot be coerced to the field type.
    """
    adapter: TypeAdapter[Any] = TypeAdapter(model.model_fields[py_field].annotation)
    try:
        value = adapter.validate_python(raw)
    except ValidationError as exc:
        raise QueryValidationError(
            f"Invalid value {raw!r} for field {to_camel(py_field)!r}"
        ) from exc
    if json_text:
        return adapter.dump_python(value, mode="json")
    return value


def apply_sort(
    stmt: SelectOfScalar[Any],
    model: type[SQLModel],
    specs: Sequence[SortSpec],
    *,
    default: Sequence[Any],
    readable: type[SQLModel],
    columns: Mapping[str, ColumnOverride] | None = None,
) -> SelectOfScalar[Any]:
    """Apply sort specs to a select statement, falling back to a default order.

    Args:
        stmt: The select statement to order.
        model: The SQLModel entity being queried.
        specs: The requested sort instructions; empty means use ``default``.
        default: The order-by expressions to apply when ``specs`` is empty
            (e.g. ``col(Workflow.created_at).desc()``).
        readable: The schema the caller serializes results as; a sort field
            must also be present here (see :func:`_resolve_column`).
        columns: Expressions to sort by instead of the model's own columns,
            keyed by resolved attribute name (see :class:`ColumnOverride`).

    Returns:
        The statement with an ``ORDER BY`` clause applied.

    Raises:
        QueryValidationError: If a spec references a field unknown to
            ``model`` or absent from ``readable``.
    """
    if not specs:
        return stmt.order_by(*default)
    order_by = []
    for spec in specs:
        py_field = _resolve_column(model, spec.field, readable=readable)
        column = _expression_for(model, py_field, columns)
        order_by.append(column.desc() if spec.descending else column.asc())
    return stmt.order_by(*order_by)


def apply_filters(
    stmt: SelectOfScalar[Any],
    model: type[SQLModel],
    specs: Sequence[FilterSpec],
    *,
    readable: type[SQLModel],
    columns: Mapping[str, ColumnOverride] | None = None,
) -> SelectOfScalar[Any]:
    """Apply filter specs to a select statement as ``WHERE`` clauses.

    Args:
        stmt: The select statement to filter.
        model: The SQLModel entity being queried.
        specs: The requested filter instructions.
        readable: The schema the caller serializes results as; a filter field
            must also be present here (see :func:`_resolve_column`).
        columns: Expressions to filter on instead of the model's own columns,
            keyed by resolved attribute name (see :class:`ColumnOverride`).

    Returns:
        The statement with the filter conditions applied.

    Raises:
        QueryValidationError: If a spec references a field unknown to
            ``model`` or absent from ``readable``, uses an unknown operator,
            or carries an uncoercible value.
    """
    for spec in specs:
        if spec.op not in FILTER_OPERATORS:
            raise QueryValidationError(f"Unknown operator {spec.op!r}")
        py_field = _resolve_column(model, spec.field, readable=readable)
        override = columns.get(py_field) if columns is not None else None
        json_text = override.json_text if override is not None else False
        column = _expression_for(model, py_field, columns)
        if spec.op == "like":
            stmt = stmt.where(column.ilike(f"%{spec.value}%"))
        elif spec.op == "in":
            values = [
                _coerce(model, py_field, v, json_text=json_text)
                for v in spec.value.split(",")
            ]
            stmt = stmt.where(column.in_(values))
        else:
            value = _coerce(model, py_field, spec.value, json_text=json_text)
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
