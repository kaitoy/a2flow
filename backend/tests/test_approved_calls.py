"""Tests for the constraint language in :mod:`infrastructure.approved_calls`.

The module is pure, so these build declarations in memory and never touch a
database. What they pin down is the meaning both sides of the gate depend on:
which declarations are well formed, and which calls one admits.

The last test in the file is the one worth not deleting: a denial message is
stored verbatim in the audit row that deliberately keeps arguments only as a
digest, so a message quoting the value it refused would write back what the row
exists to withhold.
"""

from infrastructure.approved_calls import (
    declared_tools,
    match_call,
    validate_declaration,
)
from models.approval import ApprovedCall

SERVER = "srv-1"
TOOL = "run_instances"


def _call(**arguments: dict[str, object]) -> ApprovedCall:
    """Build a one-tool declaration entry over the given argument constraints.

    Args:
        **arguments: Argument name to its constraint object.

    Returns:
        The declared call.
    """
    return ApprovedCall(mcp_server_id=SERVER, tool_name=TOOL, arguments=arguments)


def _unconstrained() -> ApprovedCall:
    """Build the entry the request path writes for an input-approval exemption.

    Returns:
        A declared call permitting the shared server/tool with any arguments.
    """
    return ApprovedCall(
        mcp_server_id=SERVER, tool_name=TOOL, unconstrained_arguments=True
    )


def _match(declaration: list[ApprovedCall], **arguments: object) -> str | None:
    """Match a call against a declaration, defaulting the server and tool.

    Args:
        declaration: The declaration to match against.
        **arguments: The arguments the call carries.

    Returns:
        The denial reason, or ``None`` when the call conforms.
    """
    return match_call(
        declaration, server_id=SERVER, tool_name=TOOL, arguments=dict(arguments)
    )


# --- validate_declaration ---------------------------------------------------


def test_a_declaration_using_each_operator_is_well_formed() -> None:
    assert (
        validate_declaration(
            [
                _call(
                    region={"eq": "ap-northeast-1"},
                    size={"in": ["t3.micro", "t3.small"]},
                    count={"lte": 2},
                    disk={"gte": 8},
                    name={"matches": "^dev-"},
                )
            ]
        )
        == []
    )


def test_a_constraint_needs_an_operator() -> None:
    problems = validate_declaration([_call(region={})])
    assert len(problems) == 1
    assert "exactly one" in problems[0]


def test_a_constraint_may_not_carry_two_operators() -> None:
    problems = validate_declaration([_call(region={"eq": "a", "in": ["a"]})])
    assert len(problems) == 1
    assert "exactly one" in problems[0]


def test_an_unknown_constraint_key_is_rejected() -> None:
    problems = validate_declaration([_call(region={"eq": "a", "startswith": "b"})])
    assert any("startswith" in problem for problem in problems)


def test_optional_is_a_modifier_not_an_operator() -> None:
    assert validate_declaration([_call(region={"eq": "a", "optional": True})]) == []


def test_optional_must_be_a_boolean() -> None:
    problems = validate_declaration([_call(region={"eq": "a", "optional": "yes"})])
    assert any("'optional'" in problem for problem in problems)


def test_in_needs_a_non_empty_list() -> None:
    assert validate_declaration([_call(region={"in": []})]) != []
    assert validate_declaration([_call(region={"in": "a"})]) != []


def test_a_bound_needs_a_number() -> None:
    assert validate_declaration([_call(count={"lte": "2"})]) != []
    # bool is an int in Python, but a quantity bound never means a flag.
    assert validate_declaration([_call(count={"gte": True})]) != []


def test_matches_needs_a_valid_regular_expression() -> None:
    assert validate_declaration([_call(name={"matches": "^dev-["})]) != []
    assert validate_declaration([_call(name={"matches": 5})]) != []


def test_an_over_long_pattern_is_rejected() -> None:
    problems = validate_declaration([_call(name={"matches": "a" * 600})])
    assert any("longer than" in problem for problem in problems)


def test_the_same_tool_may_not_be_declared_twice() -> None:
    problems = validate_declaration([_call(region={"eq": "a"}), _call()])
    assert any("more than once" in problem for problem in problems)


def test_every_problem_is_reported_at_once() -> None:
    """One round trip should be enough for the agent to fix the whole thing."""
    problems = validate_declaration([_call(region={}, count={"lte": "x"})])
    assert len(problems) == 2


def test_an_unconstrained_entry_is_well_formed() -> None:
    assert validate_declaration([_unconstrained()]) == []


def test_an_unconstrained_entry_may_not_also_constrain_an_argument() -> None:
    """The two say opposite things, so a declaration setting both means nothing."""
    contradictory = ApprovedCall(
        mcp_server_id=SERVER,
        tool_name=TOOL,
        arguments={"region": {"eq": "ap-northeast-1"}},
        unconstrained_arguments=True,
    )
    problems = validate_declaration([contradictory])
    assert any("cannot also constrain" in problem for problem in problems)


def test_declared_tools_lists_the_pairs() -> None:
    assert declared_tools([_call()]) == frozenset({(SERVER, TOOL)})


# --- match_call -------------------------------------------------------------


def test_a_conforming_call_is_admitted() -> None:
    declaration = [_call(region={"eq": "ap-northeast-1"}, count={"lte": 2})]
    assert _match(declaration, region="ap-northeast-1", count=2) is None


def test_a_tool_the_declaration_omits_is_refused() -> None:
    reason = match_call(
        [_call(region={"eq": "a"})],
        server_id=SERVER,
        tool_name="terminate_instances",
        arguments={},
    )
    assert reason is not None
    assert "does not authorize tool" in reason


def test_the_same_tool_on_another_server_is_refused() -> None:
    reason = match_call([_call()], server_id="srv-2", tool_name=TOOL, arguments={})
    assert reason is not None


def test_an_undeclared_argument_is_refused() -> None:
    """The strict allowlist: a key the approver never saw is not a free pass."""
    reason = _match([_call(region={"eq": "a"})], region="a", dry_run=False)
    assert reason is not None
    assert "dry_run" in reason


def test_a_declared_argument_the_call_omits_is_refused() -> None:
    reason = _match([_call(region={"eq": "a"})])
    assert reason is not None
    assert "omits it" in reason


def test_an_optional_argument_may_be_absent() -> None:
    declaration = [_call(region={"eq": "a"}, tag={"eq": "x", "optional": True})]
    assert _match(declaration, region="a") is None


def test_an_optional_argument_is_still_constrained_when_present() -> None:
    declaration = [_call(region={"eq": "a"}, tag={"eq": "x", "optional": True})]
    assert _match(declaration, region="a", tag="other") is not None


def test_eq_compares_the_whole_value() -> None:
    declaration = [_call(tags={"eq": {"env": "dev"}})]
    assert _match(declaration, tags={"env": "dev"}) is None
    assert _match(declaration, tags={"env": "prod"}) is not None


def test_in_checks_membership() -> None:
    declaration = [_call(size={"in": ["t3.micro", "t3.small"]})]
    assert _match(declaration, size="t3.micro") is None
    assert _match(declaration, size="m5.24xlarge") is not None


def test_a_bound_includes_its_endpoint() -> None:
    assert _match([_call(count={"lte": 2})], count=2) is None
    assert _match([_call(count={"lte": 2})], count=3) is not None
    assert _match([_call(count={"gte": 8})], count=8) is None
    assert _match([_call(count={"gte": 8})], count=7) is not None


def test_a_bound_refuses_a_non_numeric_value_instead_of_raising() -> None:
    """A string against ``lte`` must deny, not blow up mid-authorization."""
    assert _match([_call(count={"lte": 2})], count="lots") is not None
    assert _match([_call(count={"lte": 2})], count=None) is not None


def test_a_bound_refuses_a_boolean() -> None:
    assert _match([_call(count={"lte": 2})], count=True) is not None


def test_matches_is_unanchored() -> None:
    declaration = [_call(name={"matches": "^dev-"})]
    assert _match(declaration, name="dev-web") is None
    assert _match(declaration, name="prod-web") is not None
    assert _match([_call(name={"matches": "dev"})], name="my-dev-box") is None


def test_matches_refuses_a_non_string() -> None:
    assert _match([_call(name={"matches": "^dev-"})], name=5) is not None


def test_an_empty_declaration_refuses_everything() -> None:
    assert _match([]) is not None


def test_a_call_with_no_arguments_conforms_to_a_call_declaring_none() -> None:
    assert _match([_call()]) is None


def test_an_unconstrained_entry_admits_any_arguments() -> None:
    """The design exempted this tool, so there is no bound to fall outside of."""
    assert _match([_unconstrained()], region="anywhere", count=9999) is None


def test_an_unconstrained_entry_admits_a_call_carrying_nothing() -> None:
    assert _match([_unconstrained()]) is None


def test_an_unconstrained_entry_still_only_speaks_for_its_own_tool() -> None:
    """Exempting one tool's arguments is not exempting the declaration's tool list."""
    assert (
        match_call(
            [_unconstrained()],
            server_id=SERVER,
            tool_name="terminate_instances",
            arguments={},
        )
        is not None
    )


def test_a_denial_never_quotes_the_value_it_refused() -> None:
    """The audit row keeps arguments only as a digest; the reason is stored raw.

    A message echoing the rejected value would write the argument back into the
    row that exists to withhold it, so every denial names the key and the
    approved constraint instead.
    """
    secret = "sk-live-do-not-log-me"
    declaration = [
        _call(
            token={"eq": "approved-token"},
            size={"in": ["t3.micro"]},
            count={"lte": 2},
            floor={"gte": 8},
            name={"matches": "^dev-"},
        )
    ]
    base: dict[str, object] = {
        "token": "approved-token",
        "size": "t3.micro",
        "count": 2,
        "floor": 8,
        "name": "dev-box",
    }
    for key in base:
        deviating = dict(base) | {key: secret}
        reason = match_call(
            declaration, server_id=SERVER, tool_name=TOOL, arguments=deviating
        )
        assert reason is not None, key
        assert secret not in reason, key
        assert key in reason, key

    undeclared = match_call(
        declaration,
        server_id=SERVER,
        tool_name=TOOL,
        arguments=dict(base) | {"extra": secret},
    )
    assert undeclared is not None
    assert secret not in undeclared
