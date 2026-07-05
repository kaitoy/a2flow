"""Unit tests for SkillManager's clone-and-resolve behavior."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from infrastructure.skill_manager import SkillCloneError, SkillManager
from models.agent_skill import AgentSkill


def _make_skill(repo_path: str) -> AgentSkill:
    return AgentSkill(
        name="test-skill",
        repo_url="https://github.com/example/repo",
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
