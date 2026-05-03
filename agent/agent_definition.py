# agent/agent_definition.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

PermissionMode = Literal["auto", "readonly"]


@dataclass
class RuntimeInfo:
    working_dir: str
    platform: str
    shell: str
    skill_summary: str | None = None


@dataclass
class AgentDefinition:
    name: str
    description: str
    disallowed_tools: list[str] = field(default_factory=list)
    model: str | None = None
    get_system_prompt: Callable[[RuntimeInfo], str] | None = None
    omit_claude_md: bool = False
    max_steps: int = 50
    permission_mode: PermissionMode = "auto"


BUILTIN_AGENTS: dict[str, AgentDefinition] = {
    "general-purpose": AgentDefinition(
        name="general-purpose",
        description="General-purpose agent for complex, multi-step tasks that may require searching code, reading files, and writing changes.",
        disallowed_tools=[],
        permission_mode="auto",
    ),
    "explore": AgentDefinition(
        name="explore",
        description="Fast agent specialized for exploring codebases. Use to quickly find files by patterns, search code for keywords, or answer questions about the codebase.",
        disallowed_tools=["write_file", "edit_file", "spawn"],
        omit_claude_md=True,
        max_steps=50,
        permission_mode="readonly",
    ),
    "plan": AgentDefinition(
        name="plan",
        description="Software architect agent for designing implementation plans. Use to plan implementation strategy for a task. Returns step-by-step plans, identifies critical files, and considers architectural trade-offs.",
        disallowed_tools=["write_file", "edit_file", "spawn"],
        omit_claude_md=True,
        max_steps=50,
        permission_mode="readonly",
    ),
}
