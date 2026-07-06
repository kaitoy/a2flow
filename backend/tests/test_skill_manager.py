"""Unit tests for SkillManager's clone-and-resolve behavior."""

import http.server
import threading
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from dulwich import porcelain
from dulwich.errors import GitProtocolError

from infrastructure.skill_manager import SkillManager, _build_no_redirect_pool_manager
from models.agent_skill import AgentSkill
from repositories.exceptions import SkillCloneError


def _make_skill(
    repo_path: str, repo_url: str = "https://github.com/example/repo"
) -> AgentSkill:
    return AgentSkill(
        name="test-skill",
        repo_url=repo_url,
        repo_path=repo_path,
        created_by="system",
        updated_by="system",
    )


async def test_ensure_cloned_returns_target_dir_for_empty_repo_path(
    tmp_path: Path,
) -> None:
    manager = SkillManager(cache_dir=tmp_path)
    skill = _make_skill("")
    manager._clone = AsyncMock(  # type: ignore[method-assign]
        side_effect=lambda _url, target: target.mkdir(parents=True)
    )

    skill_dir = await manager.ensure_cloned(skill)

    assert skill_dir == (tmp_path / skill.id).resolve()


async def test_ensure_cloned_returns_nested_subdir(tmp_path: Path) -> None:
    manager = SkillManager(cache_dir=tmp_path)
    skill = _make_skill("skills/my-skill")

    async def _fake_clone(_url: str, target: Path) -> None:
        (target / "skills" / "my-skill").mkdir(parents=True)

    manager._clone = AsyncMock(side_effect=_fake_clone)  # type: ignore[method-assign]

    skill_dir = await manager.ensure_cloned(skill)

    assert skill_dir == (tmp_path / skill.id / "skills" / "my-skill").resolve()


async def test_ensure_cloned_rejects_repo_path_escaping_cache_dir(
    tmp_path: Path,
) -> None:
    """A repo_path of '..' would otherwise resolve to the cache dir's parent.

    This can only be reached by constructing an AgentSkill directly, since
    `models.constraints.RepoPath` rejects this at the API boundary — but
    `table=True` SQLModel classes skip Pydantic validation, so a row
    inserted before that check existed could still carry this value.
    """
    manager = SkillManager(cache_dir=tmp_path)
    skill = _make_skill("..")
    manager._clone = AsyncMock(  # type: ignore[method-assign]
        side_effect=lambda _url, target: target.mkdir(parents=True)
    )

    with pytest.raises(SkillCloneError, match="escapes the cache directory"):
        await manager.ensure_cloned(skill)


async def test_clone_rejects_loopback_repo_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A loopback repo_url is rejected before dulwich ever runs (SSRF guard)."""
    manager = SkillManager(cache_dir=tmp_path)
    fake_clone = MagicMock()
    monkeypatch.setattr("infrastructure.skill_manager.porcelain.clone", fake_clone)

    with pytest.raises(SkillCloneError):
        await manager._clone("http://127.0.0.1/x", tmp_path / "out")

    fake_clone.assert_not_called()


async def test_clone_rejects_repo_url_resolving_to_private_ip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repo_url whose host resolves to a private IP is rejected (SSRF guard)."""
    manager = SkillManager(cache_dir=tmp_path)
    fake_clone = MagicMock()
    monkeypatch.setattr("infrastructure.skill_manager.porcelain.clone", fake_clone)
    monkeypatch.setattr(
        "infrastructure.url_safety.resolve_host", lambda host: ["10.1.2.3"]
    )

    with pytest.raises(SkillCloneError):
        await manager._clone("http://internal.example.com/x", tmp_path / "out")

    fake_clone.assert_not_called()


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
