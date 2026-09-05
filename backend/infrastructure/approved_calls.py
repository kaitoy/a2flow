"""The constraint language an approval's declaration is written in, and its matcher.

An approval records the MCP calls it authorizes as a list of
:class:`models.approval.ApprovedCall`. This module is the single definition of
what such a declaration *means*: :func:`validate_declaration` decides whether one
is well formed, on the write path, and :func:`match_call` decides whether a call
conforms to one, at the gate. Both share this module on purpose -- a declaration
accepted at request time and then read differently at call time would gate
nothing reliably.

Pure by design, like :mod:`infrastructure.approval_scope` and
:mod:`infrastructure.mcp_certificate`: no session, no ORM query, nothing from
:mod:`repositories`. That is what lets the request path call it inside an agent
tool and the policy call it mid-authorization, and what lets it be tested on its
own.

**The vocabulary.** A constraint is an object carrying exactly one operator:

``eq``
    The argument must equal this value exactly, whatever its type.
``in``
    The argument must be one of the listed values.
``lte`` / ``gte``
    The argument must be a number within this bound.
``matches``
    The argument must be a string matching this regular expression.

plus the optional ``optional`` modifier, which permits the argument to be absent
altogether. An operator is always written out rather than a bare literal standing
in for ``eq``, so an argument whose own value is an object or a list is never
mistaken for a constraint: ``{"eq": {"env": "dev"}}`` is unambiguous where a bare
``{"env": "dev"}`` would not be.

**The one entry that constrains nothing.** An entry carrying
``unconstrained_arguments`` permits the tool with any arguments at all. It stands
for a tool the workflow's design marked as not requiring input approval
(:class:`models.workflow_task.ToolBinding`) -- a tool that only reads, whose
arguments an exploring agent cannot know when the request is made. Only
:func:`infrastructure.approval_tools.request_approval` writes such an entry, and
it writes one for every exempt tool the approval covers, so the declaration stays
the complete list of what the decision authorizes rather than falling silent
about part of it. Naming an argument constraint alongside it is contradictory and
:func:`validate_declaration` refuses it.

**Why matching is strict.** An argument the declaration does not mention is
refused rather than ignored. The declaration is what the approver read, so a key
absent from it is one nobody agreed to -- and the arguments that decide what a
call actually does are exactly the ones worth smuggling in.

**Why a denial never quotes the value it refused.** A policy's message is stored
verbatim in ``mcp_tool_invocations.denial_reason``
(:meth:`infrastructure.mcp_audit.SqlMcpAuditSink._record`), on the same row whose
``arguments_digest`` exists precisely so the arguments themselves are not kept.
The manual states that guarantee outright -- "the raw values are never stored".
So a denial names the argument **key** and the **approved constraint**, which the
approver authored and the approval already shows, and never the value the run
passed. That is enough for the agent to correct itself: it knows what it sent.
"""

import re
from collections.abc import Sequence
from typing import Any

from models.approval import ApprovedCall

#: The operators a constraint may carry, in the order they are reported.
OPERATORS: tuple[str, ...] = ("eq", "in", "lte", "gte", "matches")

#: Keys accepted alongside an operator. ``optional`` is a modifier, not an
#: operator: it says the argument may be absent, not what it must equal, so it
#: does not count towards the exactly-one-operator rule.
_MODIFIERS: frozenset[str] = frozenset({"optional"})

#: Longest ``matches`` pattern a declaration may carry. ``re`` has no timeout, so
#: a pathological pattern would burn the request's thread. The patterns come from
#: the run's own agent and are read by a human approver rather than supplied by
#: an anonymous caller, so a bound this generous only rules out the absurd.
_MAX_PATTERN_LENGTH = 512

#: How much of an argument a ``matches`` constraint examines. Bounds the other
#: half of the same worry: a long subject string against a backtracking pattern.
_MAX_MATCHED_LENGTH = 4096


def _is_number(value: Any) -> bool:
    """Return whether a value is a number a bound can be compared against.

    ``bool`` is excluded although Python makes it an ``int``: a declaration
    bounding an argument by ``lte`` means a quantity, and letting ``True`` slip
    through as ``1`` would compare something the approver never had in mind.

    Args:
        value: The value to test.

    Returns:
        ``True`` for an ``int`` or ``float`` that is not a ``bool``.
    """
    return not isinstance(value, bool) and isinstance(value, int | float)


def _describe(constraint: dict[str, Any]) -> str:
    """Render a constraint the way a denial message should name it.

    Args:
        constraint: The constraint object, assumed well formed.

    Returns:
        A short human-readable rendering, e.g. ``in ['a', 'b']``.
    """
    for operator in OPERATORS:
        if operator in constraint:
            return f"{operator} {constraint[operator]!r}"
    return "<no operator>"


def validate_declaration(calls: Sequence[ApprovedCall]) -> list[str]:
    """Return every structural problem with a declaration, empty when it is sound.

    Every problem is collected rather than the first one raised, so a requesting
    agent can fix a malformed declaration in one further attempt instead of
    discovering the faults one at a time.

    Args:
        calls: The declared calls to check.

    Returns:
        Human-readable problem descriptions, each naming the tool and argument
        at fault. Empty when the declaration is well formed.
    """
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()
    for call in calls:
        where = f"{call.tool_name!r} on server {call.mcp_server_id!r}"
        key = (call.mcp_server_id, call.tool_name)
        if key in seen:
            problems.append(f"{where} is declared more than once")
        seen.add(key)
        if call.unconstrained_arguments:
            if call.arguments:
                problems.append(
                    f"{where} permits any arguments, so it cannot also constrain "
                    f"{sorted(call.arguments)}"
                )
            continue
        for name, constraint in call.arguments.items():
            problems.extend(_validate_constraint(where, name, constraint))
    return problems


def declared_tools(calls: Sequence[ApprovedCall]) -> frozenset[tuple[str, str]]:
    """Return the ``(mcp_server_id, tool_name)`` pairs a declaration names.

    Args:
        calls: The declared calls.

    Returns:
        The pairs, for comparison against what the covered tasks bind.
    """
    return frozenset((call.mcp_server_id, call.tool_name) for call in calls)


def _validate_constraint(
    where: str, name: str, constraint: dict[str, Any]
) -> list[str]:
    """Return the problems with one argument's constraint.

    Args:
        where: The tool and server the constraint belongs to, for the message.
        name: The argument name.
        constraint: The constraint object to check.

    Returns:
        Human-readable problem descriptions, empty when the constraint is sound.
    """
    at = f"argument {name!r} of {where}"
    if not isinstance(constraint, dict):
        return [
            f"{at}: a constraint must be an object, not {type(constraint).__name__}"
        ]

    operators = [key for key in constraint if key in OPERATORS]
    unknown = [
        key for key in constraint if key not in OPERATORS and key not in _MODIFIERS
    ]
    problems: list[str] = []
    if unknown:
        problems.append(
            f"{at}: unknown constraint key {unknown[0]!r}; use exactly one of "
            f"{list(OPERATORS)}, optionally with 'optional'"
        )
    if len(operators) != 1:
        problems.append(
            f"{at}: a constraint needs exactly one of {list(OPERATORS)}, "
            f"but carries {len(operators)}"
        )
        return problems

    operator = operators[0]
    value = constraint[operator]
    if operator == "in":
        if not isinstance(value, list) or not value:
            problems.append(f"{at}: 'in' needs a non-empty list of allowed values")
    elif operator in ("lte", "gte") and not _is_number(value):
        problems.append(f"{at}: {operator!r} needs a number")
    elif operator == "matches":
        if not isinstance(value, str):
            problems.append(f"{at}: 'matches' needs a regular expression string")
        elif len(value) > _MAX_PATTERN_LENGTH:
            problems.append(
                f"{at}: 'matches' is longer than {_MAX_PATTERN_LENGTH} characters"
            )
        else:
            try:
                re.compile(value)
            except re.error as exc:
                problems.append(
                    f"{at}: 'matches' is not a valid regular expression: {exc}"
                )

    if not isinstance(constraint.get("optional", False), bool):
        problems.append(f"{at}: 'optional' must be true or false")
    return problems


def match_call(
    calls: Sequence[ApprovedCall],
    *,
    server_id: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> str | None:
    """Return why a call deviates from a declaration, or ``None`` when it conforms.

    The checks run in the order that produces the most useful message: the tool
    first, then arguments the approver never saw, then ones they saw and
    required, then the values themselves. A tool declared with
    ``unconstrained_arguments`` clears them all after the first: it was exempted
    from input approval at design time, so there is no bound to fall outside of.

    Args:
        calls: The declaration to match against. Assumed well formed --
            :func:`validate_declaration` gates what is written.
        server_id: The MCP server the call targets.
        tool_name: The tool the call targets.
        arguments: The arguments the call carries.

    Returns:
        A denial reason phrased so the caller can correct itself, or ``None``
        when the call is within what was approved.
    """
    declared = next(
        (
            call
            for call in calls
            if call.mcp_server_id == server_id and call.tool_name == tool_name
        ),
        None,
    )
    if declared is None:
        approved = sorted(call.tool_name for call in calls)
        return (
            f"the approval covering this task does not authorize tool "
            f"{tool_name!r} on server {server_id!r}. Approved tools: {approved}"
        )
    if declared.unconstrained_arguments:
        # The workflow's design exempted this tool from input approval, and the
        # approver decided on it knowing that. There is nothing to match against.
        return None

    undeclared = sorted(set(arguments) - set(declared.arguments))
    if undeclared:
        return (
            f"argument {undeclared[0]!r} is not one the approver approved for "
            f"{tool_name!r}. Approved arguments: {sorted(declared.arguments)}"
        )

    for name, constraint in sorted(declared.arguments.items()):
        if name not in arguments:
            if constraint.get("optional", False):
                continue
            return (
                f"the approval for {tool_name!r} requires argument {name!r} "
                f"({_describe(constraint)}), but the call omits it"
            )
        if not _satisfies(constraint, arguments[name]):
            return (
                f"argument {name!r} is outside what the approver approved for "
                f"{tool_name!r}: it must satisfy {_describe(constraint)}"
            )
    return None


def _satisfies(constraint: dict[str, Any], value: Any) -> bool:
    """Return whether one argument's value satisfies its constraint.

    Answers only yes or no. The message a denial carries is built by the caller
    from the *constraint*, never from ``value`` -- see the module docstring on
    why a refused value is not quoted.

    Args:
        constraint: The constraint the value must satisfy, assumed well formed.
        value: The value the call carries.

    Returns:
        ``True`` when the value is within what the constraint allows.
    """
    if "eq" in constraint:
        return bool(value == constraint["eq"])
    if "in" in constraint:
        return value in constraint["in"]
    if "lte" in constraint:
        return _is_number(value) and value <= constraint["lte"]
    if "gte" in constraint:
        return _is_number(value) and value >= constraint["gte"]
    if "matches" in constraint:
        return (
            isinstance(value, str)
            and re.search(constraint["matches"], value[:_MAX_MATCHED_LENGTH])
            is not None
        )
    return False
