from pathlib import Path

import pytest

from agent_common.models import RunContext
from agent_common.tools import ToolRegistry
from agent_integrations.sandbox import SandboxManager, SandboxMode, SandboxTarget
from agent_integrations.skills import SkillLoader


@pytest.mark.asyncio
async def test_skill_loader_registers_python_and_command_skills() -> None:
    registry = ToolRegistry()
    sandbox_manager = SandboxManager(
        mode=SandboxMode.PROCESS,
        targets=[SandboxTarget.COMMAND_SKILL],
        env_allowlist=["PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP"],
    )
    loader = SkillLoader([Path("skills/examples")], [["cmd", "/c", "echo"]], sandbox_manager)

    skills = loader.register(registry)
    result = await registry.call(
        "python_echo",
        {"prompt": "hello"},
        RunContext(run_id="run_1", workdir=Path.cwd(), node_id="node_1"),
    )

    assert {skill.name for skill in skills} == {"python_echo", "command_echo", "official_source_search"}
    assert result["echo"] == "hello"


@pytest.mark.asyncio
async def test_command_skill_requires_whitelist() -> None:
    registry = ToolRegistry()
    sandbox_manager = SandboxManager(
        mode=SandboxMode.PROCESS,
        targets=[SandboxTarget.COMMAND_SKILL],
        env_allowlist=["PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP"],
    )
    loader = SkillLoader([Path("skills/examples")], [], sandbox_manager)
    loader.register(registry)

    with pytest.raises(PermissionError):
        await registry.call(
            "command_echo",
            {"prompt": "blocked"},
            RunContext(run_id="run_1", workdir=Path.cwd(), node_id="node_1"),
        )


