"""Guards that the sample Agent Skills stay free of A2Flow-specific mechanics.

A skill carries domain knowledge and is expected to work under any agent
runtime; the A2Flow half -- how an approval is requested, how an external
operation reaches an MCP server, how a task DAG is registered -- lives in the
agent instructions in :mod:`infrastructure.agent` instead. Naming an A2Flow
agent tool in a ``SKILL.md`` breaks that split and duplicates a rule that the
instruction already owns, so this test fails as soon as one reappears.
"""

import re
from pathlib import Path

import pytest

from infrastructure.agent import _KIND_TOOLS

#: Repository-root directory holding the sample skills shipped with A2Flow.
SAMPLE_SKILLS_DIR = Path(__file__).parents[2] / "sample_skills"

#: Client-side tools an agent reaches through the AG-UI toolset rather than
#: through :data:`infrastructure.agent._KIND_TOOLS`, so they are not derivable
#: from it. They are A2Flow-specific for the same reason the others are.
_FRONTEND_TOOL_NAMES = frozenset({"render_a2ui", "render_approval"})


def _a2flow_tool_names() -> frozenset[str]:
    """Return every tool name that only exists inside an A2Flow agent.

    Derived from the real per-kind toolsets so a newly added tool is covered
    without touching this test.

    Returns:
        The tool names, including the frontend-injected ones.
    """
    names = {
        tool.__name__
        for tools in _KIND_TOOLS.values()
        for tool in tools
        if callable(tool)
    }
    return frozenset(names | _FRONTEND_TOOL_NAMES)


def _skill_files() -> list[Path]:
    """Return every ``SKILL.md`` under :data:`SAMPLE_SKILLS_DIR`."""
    return sorted(SAMPLE_SKILLS_DIR.glob("*/SKILL.md"))


def test_sample_skills_directory_is_found() -> None:
    """The glob below is only meaningful if it actually resolves to skills."""
    assert _skill_files(), f"no SKILL.md found under {SAMPLE_SKILLS_DIR}"


@pytest.mark.parametrize("skill_file", _skill_files(), ids=lambda p: p.parent.name)
def test_sample_skill_names_no_a2flow_tool(skill_file: Path) -> None:
    """A sample skill must not name any A2Flow agent tool."""
    text = skill_file.read_text(encoding="utf-8")
    found = sorted(
        name
        for name in _a2flow_tool_names()
        if re.search(rf"\b{re.escape(name)}\b", text)
    )
    assert not found, (
        f"{skill_file.parent.name}/SKILL.md names A2Flow agent tools {found}; "
        "such mechanics belong in the agent instruction, not in a skill"
    )
