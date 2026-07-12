"""Unit tests for SkillManager's revision publishing, resolution, and pruning."""

import http.server
import os
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from dulwich import porcelain
from dulwich.errors import GitProtocolError

from infrastructure.skill_manager import SkillManager, _build_no_redirect_pool_manager
from models.agent_skill import AgentSkill
from repositories.exceptions import SkillCloneError

_SHA_A = "a" * 40
_SHA_B = "b" * 40


def _make_skill(
    repo_path: str = "", repo_url: str = "https://github.com/example/repo"
) -> AgentSkill:
    return AgentSkill(
        name="test-skill",
        repo_url=repo_url,
        repo_path=repo_path,
        created_by="system",
        updated_by="system",
    )


def _manager(root: Path, prune_grace_seconds: int = 3600) -> SkillManager:
    return SkillManager(root=root, prune_grace_seconds=prune_grace_seconds)


def _fake_porcelain_clone(
    monkeypatch: pytest.MonkeyPatch,
    *,
    commit_sha: str = _SHA_A,
    tree: tuple[str, ...] = (),
) -> MagicMock:
    """Stub ``porcelain.clone`` so it materializes a tree and reports ``commit_sha``.

    Args:
        monkeypatch: The pytest monkeypatch fixture.
        commit_sha: The sha the returned repo's ``head()`` reports.
        tree: Directories (relative to the clone target) the fake clone creates,
            standing in for the repository's contents.

    Returns:
        The MagicMock installed in place of ``porcelain.clone``, so callers can
        assert on the arguments dulwich would have received.
    """

    def _clone(_url: str, target: str, **_kwargs: Any) -> MagicMock:
        for entry in tree:
            (Path(target) / entry).mkdir(parents=True, exist_ok=True)
        Path(target).mkdir(parents=True, exist_ok=True)
        repo = MagicMock()
        repo.head.return_value = commit_sha.encode()
        return repo

    fake = MagicMock(side_effect=_clone)
    monkeypatch.setattr("infrastructure.skill_manager.porcelain.clone", fake)
    return fake


async def test_clone_publishes_revision_directory_named_after_the_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_porcelain_clone(monkeypatch)
    manager = _manager(tmp_path)
    skill = _make_skill()

    commit_sha = await manager.clone(skill)

    assert commit_sha == _SHA_A
    assert (tmp_path / skill.id / _SHA_A).is_dir()


async def test_clone_leaves_no_staging_directory_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The staging dir is what makes the publish atomic; it must not survive it."""
    _fake_porcelain_clone(monkeypatch)
    manager = _manager(tmp_path)
    skill = _make_skill()

    await manager.clone(skill)

    assert [p.name for p in (tmp_path / skill.id).iterdir()] == [_SHA_A]


async def test_clone_of_an_already_published_revision_leaves_it_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pull that finds no new commits must not rewrite the revision in place.

    Published revisions are immutable — that is what lets a running session keep
    loading the code it started with while a pull happens underneath it.
    """
    _fake_porcelain_clone(monkeypatch)
    manager = _manager(tmp_path)
    skill = _make_skill()
    await manager.clone(skill)
    marker = tmp_path / skill.id / _SHA_A / "marker.txt"
    marker.write_text("original")

    commit_sha = await manager.clone(skill)

    assert commit_sha == _SHA_A
    assert marker.read_text() == "original"
    assert [p.name for p in (tmp_path / skill.id).iterdir()] == [_SHA_A]


async def test_clone_of_a_new_commit_adds_a_sibling_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_porcelain_clone(monkeypatch, commit_sha=_SHA_A)
    manager = _manager(tmp_path)
    skill = _make_skill()
    await manager.clone(skill)

    _fake_porcelain_clone(monkeypatch, commit_sha=_SHA_B)
    assert await manager.clone(skill) == _SHA_B

    assert sorted(p.name for p in (tmp_path / skill.id).iterdir()) == [_SHA_A, _SHA_B]


async def test_clone_rejects_a_repo_path_missing_from_the_cloned_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wrong repo_path fails the clone rather than publishing an unloadable revision."""
    _fake_porcelain_clone(monkeypatch)
    manager = _manager(tmp_path)
    skill = _make_skill("skills/nope")

    with pytest.raises(SkillCloneError, match="not found in the cloned repository"):
        await manager.clone(skill)

    assert not (tmp_path / skill.id / _SHA_A).exists()


async def test_clone_rejects_repo_path_escaping_the_revision_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repo_path of '..' would otherwise resolve outside the revision directory.

    Only reachable by constructing an AgentSkill directly, since
    `models.constraints.RepoPath` rejects this at the API boundary — but
    `table=True` SQLModel classes skip Pydantic validation, so a row inserted
    before that check existed could still carry this value.
    """
    _fake_porcelain_clone(monkeypatch)
    manager = _manager(tmp_path)
    skill = _make_skill("..")

    with pytest.raises(SkillCloneError, match="escapes the revision directory"):
        await manager.clone(skill)


async def test_clone_rejects_loopback_repo_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A loopback repo_url is rejected before dulwich ever runs (SSRF guard)."""
    fake_clone = _fake_porcelain_clone(monkeypatch)
    manager = _manager(tmp_path)

    with pytest.raises(SkillCloneError):
        await manager.clone(_make_skill(repo_url="http://127.0.0.1/x"))

    fake_clone.assert_not_called()


async def test_clone_rejects_repo_url_resolving_to_private_ip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repo_url whose host resolves to a private IP is rejected (SSRF guard)."""
    fake_clone = _fake_porcelain_clone(monkeypatch)
    monkeypatch.setattr(
        "infrastructure.url_safety.resolve_host", lambda host: ["10.1.2.3"]
    )
    manager = _manager(tmp_path)

    with pytest.raises(SkillCloneError):
        await manager.clone(_make_skill(repo_url="http://internal.example.com/x"))

    fake_clone.assert_not_called()


async def test_clone_passes_basic_auth_credentials_to_dulwich(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An auth pair is forwarded to porcelain.clone as username/password kwargs."""
    fake_clone = _fake_porcelain_clone(monkeypatch)
    manager = _manager(tmp_path)

    await manager.clone(_make_skill(), auth=("x-access-token", "tok-123"))

    kwargs = fake_clone.call_args.kwargs
    assert kwargs["username"] == "x-access-token"
    assert kwargs["password"] == "tok-123"


async def test_clone_without_auth_omits_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without an auth pair, no username/password kwargs reach porcelain.clone."""
    fake_clone = _fake_porcelain_clone(monkeypatch)
    manager = _manager(tmp_path)

    await manager.clone(_make_skill())

    kwargs = fake_clone.call_args.kwargs
    assert "username" not in kwargs
    assert "password" not in kwargs


def test_skill_dir_resolves_a_nested_repo_path(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    skill = _make_skill("skills/my-skill")

    skill_dir = manager.skill_dir(skill, _SHA_A)

    assert skill_dir == (tmp_path / skill.id / _SHA_A / "skills" / "my-skill").resolve()


def test_skill_dir_is_the_revision_dir_for_an_empty_repo_path(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    skill = _make_skill("")

    assert manager.skill_dir(skill, _SHA_A) == (tmp_path / skill.id / _SHA_A).resolve()


def test_skill_dir_rejects_repo_path_escaping_the_revision_dir(tmp_path: Path) -> None:
    manager = _manager(tmp_path)

    with pytest.raises(SkillCloneError, match="escapes the revision directory"):
        manager.skill_dir(_make_skill(".."), _SHA_A)


def _stale_revision(root: Path, skill_id: str, sha: str, *, age_seconds: int) -> Path:
    """Create a revision directory whose mtime is ``age_seconds`` in the past."""
    path = root / skill_id / sha
    path.mkdir(parents=True)
    past = time.time() - age_seconds
    os.utime(path, (past, past))
    return path


async def test_prune_removes_only_stale_unreferenced_revisions(tmp_path: Path) -> None:
    manager = _manager(tmp_path, prune_grace_seconds=3600)
    skill_id = "skill-1"
    kept_by_keep = _stale_revision(tmp_path, skill_id, _SHA_A, age_seconds=7200)
    dropped = _stale_revision(tmp_path, skill_id, _SHA_B, age_seconds=7200)

    await manager.prune(skill_id, {_SHA_A})

    assert kept_by_keep.is_dir()
    assert not dropped.exists()


async def test_prune_keeps_revisions_inside_the_grace_window(tmp_path: Path) -> None:
    """A revision a run has just picked but not yet recorded must survive a pull.

    ``execute`` reads the skill's current revision and inserts the session row
    naming it a moment later; a prune landing in that gap would otherwise delete
    the code the run is about to depend on.
    """
    manager = _manager(tmp_path, prune_grace_seconds=3600)
    skill_id = "skill-1"
    fresh = _stale_revision(tmp_path, skill_id, _SHA_B, age_seconds=60)

    await manager.prune(skill_id, set())

    assert fresh.is_dir()


async def test_prune_is_a_noop_for_a_skill_with_no_store_directory(
    tmp_path: Path,
) -> None:
    await _manager(tmp_path).prune("never-cloned", set())


class _RedirectToInternalHandler(http.server.BaseHTTPRequestHandler):
    """Responds to every request with a 302 redirect to a closed internal port."""

    def do_GET(self) -> None:  # noqa: N802 — required BaseHTTPRequestHandler name
        self.send_response(302)
        self.send_header("Location", "http://127.0.0.1:1/internal")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


@pytest.fixture()
def redirecting_server() -> Iterator[str]:
    """Run a local HTTP server that 302-redirects every request, yield its base URL."""
    server = http.server.HTTPServer(("127.0.0.1", 0), _RedirectToInternalHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/repo.git"
    finally:
        server.shutdown()
        thread.join()


def test_no_redirect_pool_manager_does_not_follow_redirect_to_internal_target(
    tmp_path: Path, redirecting_server: str
) -> None:
    """dulwich must surface the redirect as a failure, not silently follow it.

    Regression test for the pool manager built by
    ``_build_no_redirect_pool_manager``: without ``retries=Retry(redirect=0,
    ...)``, dulwich's default urllib3 manager follows the 302 and attempts to
    connect to the (closed) internal target instead of failing fast.
    """
    pool_manager = _build_no_redirect_pool_manager(redirecting_server)

    with pytest.raises(GitProtocolError):
        porcelain.clone(
            redirecting_server,
            str(tmp_path / "out"),
            depth=1,
            pool_manager=pool_manager,  # type: ignore[arg-type]
        )


async def test_clone_wraps_an_unenumerated_client_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every clone failure must surface as SkillCloneError, whatever its type.

    dulwich raises a bare ``Exception`` subclass (``HTTPUnauthorized``) for the
    HTTP 401 GitHub answers for a repository that does not exist or that the
    caller cannot see. Callers record a failure by catching SkillCloneError, so
    anything that escapes un-wrapped strands the skill mid-clone.
    """

    class _HTTPUnauthorized(Exception):
        """Stand-in for ``dulwich.client.HTTPUnauthorized``, which subclasses Exception."""

    monkeypatch.setattr(
        "infrastructure.skill_manager.porcelain.clone",
        MagicMock(side_effect=_HTTPUnauthorized("401 Unauthorized")),
    )
    manager = _manager(tmp_path)

    with pytest.raises(SkillCloneError, match="401 Unauthorized"):
        await manager.clone(_make_skill())
