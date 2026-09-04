"""Tests for the nearest-approval rule in :mod:`infrastructure.approval_scope`.

The module is pure, so these build task graphs and approval rows in memory and
never touch a database. What they pin down is the rule the gate and the grant
both read: an approval covers the task it names and everything downstream of it
up to the next approval, a merge collects every branch's gate, and a task with
several approval rows of its own is gated by exactly one of them.
"""

from datetime import UTC, datetime, timedelta

from infrastructure.approval_scope import (
    active_approval_by_task,
    covered_task_ids,
    governing_approvals,
)
from models.approval import Approval, ApprovalStatus
from models.workflow_task import WorkflowTaskRead

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def _task(task_id: str, *depends_on: str) -> WorkflowTaskRead:
    """Build a task node with the given dependency edges."""
    return WorkflowTaskRead(
        id=task_id,
        workflow_execution_id="run-1",
        title=task_id,
        depends_on_ids=list(depends_on),
        created_by="owner",
        updated_by="owner",
    )


def _approval(
    approval_id: str,
    task_id: str | None,
    *,
    status: ApprovalStatus = ApprovalStatus.pending,
    age: int = 0,
) -> Approval:
    """Build an approval row, ``age`` minutes after the epoch."""
    return Approval(
        id=approval_id,
        workflow_execution_id="run-1",
        workflow_task_id=task_id,
        title=approval_id,
        status=status,
        tenant_id="tenant-1",
        created_at=_EPOCH + timedelta(minutes=age),
        created_by="owner",
        updated_by="owner",
    )


# ---------------------------------------------------------------------------
# Which approval gates a task
# ---------------------------------------------------------------------------


def test_a_task_with_no_approval_is_gated_by_nobody() -> None:
    assert active_approval_by_task([]) == {}


def test_an_unresolved_request_outranks_a_decided_one() -> None:
    """A task re-asked after a rejection is gated by the fresh request.

    Otherwise the rejection would wedge the task forever, since a decision is
    final and can never become ``approved``.
    """
    rejected = _approval("a1", "t1", status=ApprovalStatus.rejected, age=0)
    pending = _approval("a2", "t1", status=ApprovalStatus.pending, age=1)

    assert active_approval_by_task([rejected, pending]) == {"t1": "a2"}


def test_the_newest_decided_request_gates_when_none_is_unresolved() -> None:
    older = _approval("a1", "t1", status=ApprovalStatus.rejected, age=0)
    newer = _approval("a2", "t1", status=ApprovalStatus.approved, age=1)

    assert active_approval_by_task([newer, older]) == {"t1": "a2"}


def test_an_approval_linked_to_no_task_gates_nothing() -> None:
    assert active_approval_by_task([_approval("a1", None)]) == {}


# ---------------------------------------------------------------------------
# Which approval governs a task
# ---------------------------------------------------------------------------


def test_an_approval_reaches_every_task_after_it() -> None:
    """The whole point: the gate step's decision covers the steps that follow."""
    tasks = [_task("ask"), _task("launch", "ask"), _task("tag", "launch")]

    governing = governing_approvals(tasks, {"ask": "a1"})

    assert governing == {
        "ask": frozenset({"a1"}),
        "launch": frozenset({"a1"}),
        "tag": frozenset({"a1"}),
    }


def test_an_approval_does_not_reach_backwards() -> None:
    """A task the approval descends from ran before it was ever asked for."""
    tasks = [_task("gather"), _task("ask", "gather"), _task("launch", "ask")]

    governing = governing_approvals(tasks, {"ask": "a1"})

    assert governing["gather"] == frozenset()
    assert governing["launch"] == frozenset({"a1"})


def test_a_nearer_approval_displaces_the_outer_one() -> None:
    """ "Up to the next approval": the second gate takes its subtree over."""
    tasks = [
        _task("ask1"),
        _task("middle", "ask1"),
        _task("ask2", "middle"),
        _task("delete", "ask2"),
    ]

    governing = governing_approvals(tasks, {"ask1": "a1", "ask2": "a2"})

    assert governing["middle"] == frozenset({"a1"})
    assert governing["ask2"] == frozenset({"a2"})
    assert governing["delete"] == frozenset({"a2"})


def test_a_merge_collects_every_branch_gate() -> None:
    tasks = [
        _task("ask_left"),
        _task("ask_right"),
        _task("left", "ask_left"),
        _task("right", "ask_right"),
        _task("publish", "left", "right"),
    ]

    governing = governing_approvals(tasks, {"ask_left": "a1", "ask_right": "a2"})

    assert governing["publish"] == frozenset({"a1", "a2"})


def test_an_ungated_branch_contributes_nothing_to_a_merge() -> None:
    """A merge is governed by the gates that actually sit above it, no more."""
    tasks = [
        _task("ask"),
        _task("gated", "ask"),
        _task("free"),
        _task("publish", "gated", "free"),
    ]

    governing = governing_approvals(tasks, {"ask": "a1"})

    assert governing["free"] == frozenset()
    assert governing["publish"] == frozenset({"a1"})


def test_a_task_outside_the_run_is_not_followed() -> None:
    """A dependency on a task that is not in the list is ignored, not resolved."""
    tasks = [_task("only", "elsewhere")]

    assert governing_approvals(tasks, {"elsewhere": "a1"}) == {"only": frozenset()}


def test_a_long_chain_does_not_overflow_the_stack() -> None:
    """A thousand-task run is within the cap the callers apply, so it must work."""
    tasks = [_task("t0")] + [_task(f"t{i}", f"t{i - 1}") for i in range(1, 1000)]

    governing = governing_approvals(tasks, {"t0": "a1"})

    assert governing["t999"] == frozenset({"a1"})


# ---------------------------------------------------------------------------
# The inverse: which tasks an approval covers
# ---------------------------------------------------------------------------


def test_covered_task_ids_returns_the_gate_and_its_descendants() -> None:
    tasks = [_task("ask"), _task("launch", "ask"), _task("ask2", "launch")]

    covered = covered_task_ids(tasks, {"ask": "a1", "ask2": "a2"}, "a1")

    assert covered == frozenset({"ask", "launch"})


def test_covered_task_ids_is_empty_for_a_superseded_approval() -> None:
    """An approval no longer gating its own task covers nothing at all."""
    approvals = [
        _approval("a1", "ask", status=ApprovalStatus.rejected, age=0),
        _approval("a2", "ask", age=1),
    ]
    tasks = [_task("ask"), _task("launch", "ask")]

    active = active_approval_by_task(approvals)

    assert covered_task_ids(tasks, active, "a1") == frozenset()
    assert covered_task_ids(tasks, active, "a2") == frozenset({"ask", "launch"})
