import asyncio
from pathlib import Path

from dulwich import porcelain
from dulwich.errors import GitProtocolError, NotGitRepository

from models.agent_skill import AgentSkill


class SkillCloneError(Exception):
    """Raised when an AgentSkill repository cannot be cloned."""


class SkillManager:
    """Shallow-clones AgentSkill repositories into a local cache for ADK Skill loading."""

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()

    async def ensure_cloned(self, skill: AgentSkill) -> Path:
        """Ensure the skill's repository exists locally and return the skill directory.

        Returns the path containing SKILL.md: `cache_dir/<skill_id>/<repo_path>`.
        Re-clone is skipped when the target directory already exists.

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
                await self._clone(skill.repo_url, target)
        resolved_target = target.resolve()
        skill_dir = (
            (target / skill.repo_path).resolve() if skill.repo_path else resolved_target
        )
        if not skill_dir.is_relative_to(resolved_target):
            raise SkillCloneError(
                f"repo_path {skill.repo_path!r} escapes the cache directory "
                f"for skill {skill.id}"
            )
        if not skill_dir.exists():
            raise SkillCloneError(
                f"Skill directory {skill_dir} not found after cloning {skill.repo_url}"
            )
        return skill_dir

    async def _get_lock(self, skill_id: str) -> asyncio.Lock:
        async with self._locks_guard:
            if skill_id not in self._locks:
                self._locks[skill_id] = asyncio.Lock()
            return self._locks[skill_id]

    async def _clone(self, repo_url: str, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            # porcelain.clone is synchronous; run in a worker thread so the
            # event loop is not blocked while pack data is fetched.
            await asyncio.to_thread(
                porcelain.clone,
                repo_url,
                str(target),
                depth=1,
            )
        except (GitProtocolError, NotGitRepository, OSError) as exc:
            raise SkillCloneError(f"dulwich clone of {repo_url} failed: {exc}") from exc
