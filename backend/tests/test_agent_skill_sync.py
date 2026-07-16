"""Tests for the background clone/pull job that publishes a skill's repository.

The job is the only writer of an AgentSkill's server-managed sync fields, and
the contract those fields carry is subtle: ``commit_sha`` says whether the skill
can back a run at all, while ``sync_status`` only reports how the last clone
went. Keeping them apart is what lets a failed pull leave a working skill
working.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from infrastructure.locks import LockNotAcquiredError
from models.agent_skill import AgentSkill, SkillSyncStatus
from repositories.exceptions import (
    NotFoundError,
    SecretResolutionError,
    SkillCloneError,
)
from services.agent_skill_sync import AgentSkillSyncService

_SHA = "a" * 40
_OLD_SHA = "b" * 40


def _skill(**overrides: Any) -> AgentSkill:
    return AgentSkill(
        id="skill-1",
        name="test-skill",
        repo_url="https://github.com/example/repo",
        repo_path="",
        created_by="system",
        updated_by="system",
        **overrides,
    )


def _service(
    skill: AgentSkill,
    *,
    clone: AsyncMock | None = None,
    resolve: AsyncMock | None = None,
    pinned: set[str] | None = None,
    planning_pinned: set[str] | None = None,
) -> tuple[AgentSkillSyncService, MagicMock, MagicMock]:
    skills = MagicMock()
    skills.get = AsyncMock(return_value=skill)
    skills.set_sync_state = AsyncMock(return_value=skill)

    sessions = MagicMock()
    sessions.commit_shas_for_skill = AsyncMock(return_value=pinned or set())

    planning_sessions = MagicMock()
    planning_sessions.commit_shas_for_skill = AsyncMock(
        return_value=planning_pinned or set()
    )

    resolver = MagicMock()
    resolver.resolve_value = resolve or AsyncMock(return_value="tok-123")

    store = MagicMock()
    store.clone = clone or AsyncMock(return_value=_SHA)
    store.prune = AsyncMock()

    service = AgentSkillSyncService(
        skills, sessions, planning_sessions, resolver, store
    )
    return service, skills, store


async def test_successful_clone_publishes_the_revision_and_marks_ready() -> None:
    service, skills, store = _service(_skill())

    await service.sync("skill-1", user_id="alice")

    store.clone.assert_awaited_once()
    skills.set_sync_state.assert_awaited_once_with(
        "skill-1",
        status=SkillSyncStatus.ready,
        commit_sha=_SHA,
        user_id="alice",
    )


async def test_successful_clone_prunes_revisions_no_session_still_needs() -> None:
    """Pruning must spare the revisions running sessions are pinned to."""
    service, _skills, store = _service(_skill(), pinned={_OLD_SHA})

    await service.sync("skill-1", user_id="alice")

    store.prune.assert_awaited_once_with("skill-1", {_OLD_SHA, _SHA})


async def test_successful_clone_prunes_spare_planning_session_pins() -> None:
    """Pruning must also spare the revisions planning sessions are pinned to."""
    planning_sha = "c" * 40
    service, _skills, store = _service(
        _skill(), pinned={_OLD_SHA}, planning_pinned={planning_sha}
    )

    await service.sync("skill-1", user_id="alice")

    store.prune.assert_awaited_once_with("skill-1", {_OLD_SHA, planning_sha, _SHA})


async def test_failed_clone_is_recorded_and_leaves_the_published_revision_alone() -> (
    None
):
    """A skill that already worked must keep working when a pull fails.

    ``commit_sha`` is left out of the write entirely, so the previously published
    revision stays current and workflows can still run on it — the failure shows
    up only as the status and the reason.
    """
    clone = AsyncMock(side_effect=SkillCloneError("skill-1", "host unreachable"))
    service, skills, _store = _service(_skill(commit_sha=_OLD_SHA), clone=clone)

    await service.sync("skill-1", user_id="alice")

    skills.set_sync_state.assert_awaited_once()
    kwargs = skills.set_sync_state.await_args.kwargs
    assert kwargs["status"] == SkillSyncStatus.failed
    assert "host unreachable" in kwargs["error"]
    assert "commit_sha" not in kwargs


async def test_an_unforeseen_clone_error_still_settles_the_skill() -> None:
    """``pending`` is the UI's spinner, and only the failure handler clears it.

    Regression test: dulwich raises a bare ``Exception`` subclass
    (``HTTPUnauthorized``) for the HTTP 401 GitHub answers for a repository that
    does not exist or that the caller cannot see — the most common real failure
    there is. When that escaped the handler, the skill span ``pending`` forever
    with nothing to show for it.
    """
    clone = AsyncMock(side_effect=RuntimeError("401 Unauthorized"))
    service, skills, _store = _service(_skill(), clone=clone)

    await service.sync("skill-1", user_id="alice")

    kwargs = skills.set_sync_state.await_args.kwargs
    assert kwargs["status"] == SkillSyncStatus.failed
    assert "401 Unauthorized" in kwargs["error"]


async def test_unresolvable_auth_secret_is_recorded_as_a_failure() -> None:
    """A dangling repo_auth_secret fails the clone rather than escaping the job."""
    resolve = AsyncMock(
        side_effect=SecretResolutionError("git-token", "no such secret")
    )
    service, skills, store = _service(
        _skill(repo_auth_secret="git-token"), resolve=resolve
    )

    await service.sync("skill-1", user_id="alice")

    store.clone.assert_not_awaited()
    assert skills.set_sync_state.await_args.kwargs["status"] == SkillSyncStatus.failed


async def test_auth_secret_is_resolved_into_basic_auth_credentials() -> None:
    service, _skills, store = _service(_skill(repo_auth_secret="git-token"))

    await service.sync("skill-1", user_id="alice")

    assert store.clone.await_args.kwargs["auth"] == ("x-access-token", "tok-123")


async def test_explicit_auth_username_overrides_the_default() -> None:
    service, _skills, store = _service(
        _skill(repo_auth_secret="git-token", repo_auth_username="git")
    )

    await service.sync("skill-1", user_id="alice")

    assert store.clone.await_args.kwargs["auth"] == ("git", "tok-123")


async def test_skill_without_auth_secret_clones_anonymously() -> None:
    service, _skills, store = _service(_skill())

    await service.sync("skill-1", user_id="alice")

    assert store.clone.await_args.kwargs["auth"] is None


async def test_sync_of_a_skill_already_being_synced_elsewhere_is_a_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Losing the lock means another replica is publishing the same revision.

    Doing nothing is the right answer: re-cloning would be duplicate work, and
    writing the status would race the holder's own writes.
    """

    def _contended(_key: str, **_kwargs: Any) -> Any:
        raise LockNotAcquiredError(_key)

    monkeypatch.setattr(
        "services.agent_skill_sync.advisory_lock",
        lambda key, **kwargs: _contended(key),
    )
    service, skills, store = _service(_skill())

    await service.sync("skill-1", user_id="alice")

    store.clone.assert_not_awaited()
    skills.set_sync_state.assert_not_awaited()


async def test_sync_of_an_unknown_skill_raises() -> None:
    service, skills, _store = _service(_skill())
    skills.get = AsyncMock(return_value=None)

    with pytest.raises(NotFoundError):
        await service.sync("nope", user_id="alice")
