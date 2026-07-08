import asyncio
from pathlib import Path

import urllib3
from dulwich import porcelain
from dulwich.client import AuthCallbackPoolManager, default_urllib3_manager
from dulwich.errors import GitProtocolError, NotGitRepository

from infrastructure.url_safety import UnsafeUrlError, assert_public_http_url
from models.agent_skill import AgentSkill
from repositories.exceptions import SkillCloneError


def _build_no_redirect_pool_manager(
    base_url: str,
) -> urllib3.PoolManager | urllib3.ProxyManager | AuthCallbackPoolManager:
    """Build the urllib3 pool manager dulwich uses for one clone, redirects disabled.

    Mirrors dulwich's own default construction (``default_urllib3_manager``,
    which honours proxy environment variables and TLS verification) but
    replaces its retry policy so a 3xx response is returned as-is instead of
    being followed. ``AbstractHttpGitClient`` treats any non-200 response as a
    ``GitProtocolError``, so a redirect to an internal address surfaces as a
    clone failure instead of being silently fetched.

    Args:
        base_url: The repository URL being cloned (used for proxy-bypass detection).

    Returns:
        A urllib3 pool/proxy manager with redirect-following disabled.
    """
    manager = default_urllib3_manager(config=None, base_url=base_url)
    manager.connection_pool_kw["retries"] = urllib3.util.Retry(
        redirect=0, raise_on_redirect=False
    )
    return manager


class SkillManager:
    """Shallow-clones AgentSkill repositories into a local cache for ADK Skill loading."""

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()

    async def ensure_cloned(
        self, skill: AgentSkill, auth: tuple[str, str] | None = None
    ) -> Path:
        """Ensure the skill's repository exists locally and return the skill directory.

        Returns the path containing SKILL.md: `cache_dir/<skill_id>/<repo_path>`.
        Re-clone is skipped when the target directory already exists.

        Args:
            skill: The AgentSkill whose repository to clone.
            auth: Optional ``(username, password)`` pair sent as HTTP basic
                auth with the clone, for private repositories. Ignored when
                the repository is already cached.

        Raises:
            SkillCloneError: If cloning fails, the resolved skill directory
                does not exist, or `skill.repo_path` resolves outside the
                per-skill cache directory. The last case is a defense-in-depth
                check: `models.constraints.RepoPath` already rejects `..`
                segments and absolute paths at the API boundary, but
                `table=True` SQLModel classes skip Pydantic validation, so a
                row inserted before that check existed (or constructed
                directly rather than through the API) could otherwise still
                reach here.
        """
        skill_lock = await self._get_lock(skill.id)
        async with skill_lock:
            target = self._cache_dir / skill.id
            if not target.exists():
                await self._clone(skill.repo_url, target, auth)
        resolved_target = target.resolve()
        skill_dir = (
            (target / skill.repo_path).resolve() if skill.repo_path else resolved_target
        )
        if not skill_dir.is_relative_to(resolved_target):
            raise SkillCloneError(
                skill.id,
                f"repo_path {skill.repo_path!r} escapes the cache directory",
            )
        if not skill_dir.exists():
            raise SkillCloneError(
                skill.id, f"skill directory {skill_dir} not found after cloning"
            )
        return skill_dir

    async def _get_lock(self, skill_id: str) -> asyncio.Lock:
        async with self._locks_guard:
            if skill_id not in self._locks:
                self._locks[skill_id] = asyncio.Lock()
            return self._locks[skill_id]

    async def _clone(
        self, repo_url: str, target: Path, auth: tuple[str, str] | None = None
    ) -> None:
        """Shallow-clone the repository, optionally with HTTP basic-auth credentials.

        Args:
            repo_url: The repository URL to clone.
            target: The directory to clone into.
            auth: Optional ``(username, password)`` pair forwarded to
                ``porcelain.clone`` for private repositories.

        Raises:
            SkillCloneError: If the URL is unsafe or the clone fails.
        """
        target.parent.mkdir(parents=True, exist_ok=True)

        def _do_clone() -> None:
            pool_manager = _build_no_redirect_pool_manager(repo_url)
            if auth is None:
                porcelain.clone(
                    repo_url,
                    str(target),
                    depth=1,
                    pool_manager=pool_manager,  # type: ignore[arg-type]
                )
            else:
                porcelain.clone(
                    repo_url,
                    str(target),
                    depth=1,
                    pool_manager=pool_manager,  # type: ignore[arg-type]
                    username=auth[0],
                    password=auth[1],
                )

        try:
            await asyncio.to_thread(assert_public_http_url, repo_url)
            # porcelain.clone is synchronous; run in a worker thread so the
            # event loop is not blocked while pack data is fetched.
            await asyncio.to_thread(_do_clone)
        except (GitProtocolError, NotGitRepository, OSError, UnsafeUrlError) as exc:
            raise SkillCloneError(
                target.name, f"clone of {repo_url} failed: {exc}"
            ) from exc
