# SubAgent Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optimize Bitz's Python subagent system with role-based agent types, fork-mode prompt cache sharing, selective context stripping, permission scoping, and UI enhancements.

**Architecture:** Incremental enhancement on the existing `SubAgent`/`SubAgentSpec` architecture. New `AgentDefinition` data model drives agent type configuration. `ForkMessageBuilder` constructs shared-prefix messages for prompt cache hits. `build_system_prompt()` gains conditional section injection. Spawn tool gains `agent_type` and `mode` parameters (backward-compatible).

**Tech Stack:** Python 3.11+, Anthropic Python SDK, Textual TUI framework

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `agent/agent_definition.py` | CREATE | `AgentDefinition`, `RuntimeInfo` dataclasses + built-in agent definitions |
| `agent/fork_message_builder.py` | CREATE | `ForkMessageBuilder` class for prompt-cache-shared message construction |
| `agent/adapter.py` | MODIFY | Add `cache_control` markers, client instance reuse |
| `agent/subagent.py` | MODIFY | Accept `AgentDefinition`, fork messages, token accumulation |
| `agent/prompt.py` | MODIFY | Conditional section injection via `AgentDefinition` |
| `agent/tools.py` | MODIFY | Add `filter_for_agent` method to `ToolRegistry`, spawn tool schema, `agent_type`/`mode` params, fork integration, `_is_readonly_command` |
| `agent/builtin_tools.py` | MODIFY | Enhanced spawn tool description with prompt writing guide |
| `tui/widgets/chat.py` | MODIFY | SubAgentCard stats, grouping, terminal adaptation |
| `tests/test_agent_definition.py` | CREATE | Tests for AgentDefinition, RuntimeInfo, built-in definitions |
| `tests/test_fork_message_builder.py` | CREATE | Tests for ForkMessageBuilder |
| `tests/test_subagent_integration.py` | CREATE | Integration tests for agent_type/mode spawn params |

---

### Task 1: AgentDefinition Data Model

**Files:**
- Create: `agent/agent_definition.py`
- Test: `tests/test_agent_definition.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_definition.py
import pytest
from agent.agent_definition import AgentDefinition, RuntimeInfo, BUILTIN_AGENTS


class TestRuntimeInfo:
    def test_create_runtime_info(self):
        info = RuntimeInfo(
            working_dir="/tmp",
            platform="darwin",
            shell="/bin/zsh",
            skill_summary="test skills",
        )
        assert info.working_dir == "/tmp"
        assert info.platform == "darwin"
        assert info.shell == "/bin/zsh"
        assert info.skill_summary == "test skills"

    def test_skill_summary_optional(self):
        info = RuntimeInfo(
            working_dir="/tmp", platform="darwin", shell="/bin/zsh"
        )
        assert info.skill_summary is None


class TestAgentDefinition:
    def test_create_minimal_definition(self):
        defn = AgentDefinition(
            name="test-agent",
            description="A test agent",
            disallowed_tools=[],
        )
        assert defn.name == "test-agent"
        assert defn.description == "A test agent"
        assert defn.disallowed_tools == []
        assert defn.model is None
        assert defn.get_system_prompt is None
        assert defn.omit_claude_md is False
        assert defn.max_steps == 10
        assert defn.permission_mode == "auto"

    def test_create_full_definition(self):
        def prompt_fn(info):
            return f"Custom prompt for {info.working_dir}"

        defn = AgentDefinition(
            name="custom",
            description="Custom agent",
            disallowed_tools=["write_file", "edit_file"],
            model="claude-haiku-4-5-20251001",
            get_system_prompt=prompt_fn,
            omit_claude_md=True,
            max_steps=5,
            permission_mode="readonly",
        )
        assert defn.model == "claude-haiku-4-5-20251001"
        assert defn.get_system_prompt is not None
        assert defn.omit_claude_md is True
        assert defn.max_steps == 5
        assert defn.permission_mode == "readonly"

    def test_get_system_prompt_called_with_runtime_info(self):
        def prompt_fn(info):
            return f"Working in {info.working_dir}"

        defn = AgentDefinition(
            name="test", description="test", disallowed_tools=[],
            get_system_prompt=prompt_fn,
        )
        info = RuntimeInfo(
            working_dir="/home", platform="linux", shell="/bin/bash"
        )
        result = defn.get_system_prompt(info)
        assert result == "Working in /home"


class TestBuiltinAgents:
    def test_general_purpose_exists(self):
        assert "general-purpose" in BUILTIN_AGENTS

    def test_explore_exists(self):
        assert "explore" in BUILTIN_AGENTS

    def test_plan_exists(self):
        assert "plan" in BUILTIN_AGENTS

    def test_general_purpose_allows_all_tools(self):
        agent = BUILTIN_AGENTS["general-purpose"]
        assert agent.disallowed_tools == []
        assert agent.permission_mode == "auto"
        assert agent.omit_claude_md is False

    def test_explore_disallows_write_tools(self):
        agent = BUILTIN_AGENTS["explore"]
        assert "write_file" in agent.disallowed_tools
        assert "edit_file" in agent.disallowed_tools
        assert "spawn" in agent.disallowed_tools
        assert agent.permission_mode == "readonly"
        assert agent.omit_claude_md is True

    def test_plan_disallows_write_tools(self):
        agent = BUILTIN_AGENTS["plan"]
        assert "write_file" in agent.disallowed_tools
        assert "edit_file" in agent.disallowed_tools
        assert "spawn" in agent.disallowed_tools
        assert agent.permission_mode == "readonly"
        assert agent.omit_claude_md is True

    def test_all_builtins_have_required_fields(self):
        for name, agent in BUILTIN_AGENTS.items():
            assert agent.name == name
            assert isinstance(agent.description, str)
            assert isinstance(agent.disallowed_tools, list)
            assert agent.permission_mode in ("auto", "readonly")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_agent_definition.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.agent_definition'`

- [ ] **Step 3: Write minimal implementation**

```python
# agent/agent_definition.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


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
    max_steps: int = 10
    permission_mode: str = "auto"  # "auto" | "readonly"


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
        permission_mode="readonly",
    ),
    "plan": AgentDefinition(
        name="plan",
        description="Software architect agent for designing implementation plans. Use to plan implementation strategy for a task. Returns step-by-step plans, identifies critical files, and considers architectural trade-offs.",
        disallowed_tools=["write_file", "edit_file", "spawn"],
        omit_claude_md=True,
        permission_mode="readonly",
    ),
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_agent_definition.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add agent/agent_definition.py tests/test_agent_definition.py
git commit -m "feat: add AgentDefinition data model with built-in agent types"
```

---

### Task 2: Selective Context Stripping in build_system_prompt

**Files:**
- Modify: `agent/prompt.py:1-150`
- Test: `tests/test_agent_definition.py` (add new test class)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_agent_definition.py`:

```python
from agent.prompt import build_system_prompt


class TestBuildSystemPromptStripping:
    def test_default_includes_claude_md(self):
        info = RuntimeInfo(
            working_dir="/tmp", platform="darwin", shell="/bin/zsh"
        )
        result = build_system_prompt(runtime_info=info)
        # Default (no agent_def) should include CLAUDE.md content
        assert result  # non-empty
        # Should contain persona/rules at minimum
        assert "assistant" in result.lower() or "claude" in result.lower()

    def test_explore_agent_omits_claude_md(self):
        info = RuntimeInfo(
            working_dir="/tmp", platform="darwin", shell="/bin/zsh"
        )
        agent_def = BUILTIN_AGENTS["explore"]
        result_with = build_system_prompt(runtime_info=info)
        result_without = build_system_prompt(agent_def=agent_def, runtime_info=info)
        # Explore agent's prompt should be shorter (omits CLAUDE.md)
        assert len(result_without) <= len(result_with)

    def test_general_purpose_includes_claude_md(self):
        info = RuntimeInfo(
            working_dir="/tmp", platform="darwin", shell="/bin/zsh"
        )
        agent_def = BUILTIN_AGENTS["general-purpose"]
        result = build_system_prompt(agent_def=agent_def, runtime_info=info)
        assert result  # non-empty
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_agent_definition.py::TestBuildSystemPromptStripping -v`
Expected: FAIL — `build_system_prompt()` doesn't accept `agent_def`/`runtime_info` params yet

- [ ] **Step 3: Modify build_system_prompt in agent/prompt.py**

The current signature is `build_system_prompt(cwd, skill_registry)`. Change to accept `agent_def` and `runtime_info` while keeping backward compatibility:

```python
# In agent/prompt.py, modify build_system_prompt:

def build_system_prompt(
    agent_def: "AgentDefinition | None" = None,
    runtime_info: "RuntimeInfo | None" = None,
    # Legacy params for backward compat during migration
    cwd: str | None = None,
    skill_registry: "SkillRegistry | None" = None,
) -> str:
    # Resolve working_dir from either new or legacy param
    working_dir = runtime_info.working_dir if runtime_info else (cwd or os.getcwd())
    platform = runtime_info.platform if runtime_info else sys.platform
    shell = runtime_info.shell if runtime_info else os.environ.get("SHELL", "/bin/sh")

    sections = []

    # Persona section — always included
    sections.append(PERSONA_PROMPT)

    # Rules section — always included
    sections.append(RULES_PROMPT)

    # CLAUDE.md rules — conditionally included
    if not agent_def or not agent_def.omit_claude_md:
        claude_md_content = _load_claude_md(working_dir)
        if claude_md_content:
            sections.append(claude_md_content)

    # Environment section — always included
    sections.append(_build_environment_section(working_dir, platform, shell))

    # Skill summary — conditionally included
    if runtime_info and runtime_info.skill_summary:
        sections.append(runtime_info.skill_summary)
    elif skill_registry:
        summary = skill_registry.get_summary()
        if summary:
            sections.append(summary)

    return "\n\n".join(sections)
```

Note: The exact section names (PERSONA_PROMPT, RULES_PROMPT, etc.) and helper functions (_load_claude_md, _build_environment_section) must match the current `prompt.py` structure. The implementer should read the current file and adapt this pattern to match existing section construction. The key change is: `if not agent_def or not agent_def.omit_claude_md:` gate around the CLAUDE.md section.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_agent_definition.py::TestBuildSystemPromptStripping -v`
Expected: All PASS

- [ ] **Step 5: Run existing tests to verify no regression**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/ -v`
Expected: All existing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add agent/prompt.py tests/test_agent_definition.py
git commit -m "feat: add selective context stripping to build_system_prompt"
```

---

### Task 3: Tool Filtering Based on AgentDefinition

**Files:**
- Modify: `agent/tools.py` (add `filter_for_agent` method to `ToolRegistry` class)
- Test: `tests/test_agent_definition.py` (add test class)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_agent_definition.py`:

```python
from agent.tools import ToolRegistry


class TestToolFiltering:
    def _make_registry_with_tools(self):
        """Create a registry with mock tools for testing."""
        registry = ToolRegistry()

        def mock_fn(**kwargs):
            return "mock"

        registry.register(
            name="read_file",
            description="Read a file",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            handler=mock_fn,
        )
        registry.register(
            name="write_file",
            description="Write a file",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}},
            handler=mock_fn,
            dangerous=True,
        )
        registry.register(
            name="edit_file",
            description="Edit a file",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}}},
            handler=mock_fn,
            dangerous=True,
        )
        registry.register(
            name="spawn",
            description="Spawn subagent",
            input_schema={"type": "object", "properties": {"task": {"type": "string"}}},
            handler=mock_fn,
        )
        return registry

    def test_general_purpose_keeps_all_tools(self):
        registry = self._make_registry_with_tools()
        agent_def = BUILTIN_AGENTS["general-purpose"]
        filtered = registry.filter_for_agent(agent_def)
        assert len(filtered.tools) == 4

    def test_explore_removes_write_tools(self):
        registry = self._make_registry_with_tools()
        agent_def = BUILTIN_AGENTS["explore"]
        filtered = registry.filter_for_agent(agent_def)
        tool_names = set(filtered.tools.keys())
        assert "read_file" in tool_names
        assert "write_file" not in tool_names
        assert "edit_file" not in tool_names
        assert "spawn" not in tool_names

    def test_plan_removes_write_tools(self):
        registry = self._make_registry_with_tools()
        agent_def = BUILTIN_AGENTS["plan"]
        filtered = registry.filter_for_agent(agent_def)
        tool_names = set(filtered.tools.keys())
        assert "read_file" in tool_names
        assert "write_file" not in tool_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_agent_definition.py::TestToolFiltering -v`
Expected: FAIL — `ToolRegistry` doesn't have `filter_for_agent` method yet

- [ ] **Step 3: Add filter_for_agent to ToolRegistry**

Read `agent/tool_registry.py` to understand the current `Tool` dataclass and `register()` signature. Then add:

```python
# In agent/tools.py, add method to ToolRegistry class:

def filter_for_agent(self, agent_def: "AgentDefinition") -> "ToolRegistry":
    """Return a new registry with tools filtered by agent definition's disallowed_tools."""
    from agent.agent_definition import AgentDefinition

    filtered = ToolRegistry()
    for name, tool in self.tools.items():
        if name not in agent_def.disallowed_tools:
            filtered.register(
                name=name,
                description=tool.description,
                input_schema=tool.input_schema,
                handler=tool.handler,
                dangerous=tool.dangerous,
                is_readonly=tool.is_readonly,
                is_extra_dangerous=tool.is_extra_dangerous,
            )
    return filtered
```

Note: The `Tool` dataclass in `agent/tools.py` has fields: `name`, `description`, `input_schema`, `handler`, `dangerous`, `is_readonly`, `is_extra_dangerous`. The `register()` method accepts keyword arguments matching these fields. The implementer should verify these by reading `agent/tools.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_agent_definition.py::TestToolFiltering -v`
Expected: All PASS

- [ ] **Step 5: Integrate filter_for_agent into _execute_spawn**

In `agent/tools.py`, modify `_execute_spawn` to filter tools based on `agent_type`. Note: `_execute_spawn` is the handler method on the `SpawnTool` class (or equivalent). The implementer should read the current code to find the exact method name and location.

```python
# In agent/tools.py, inside the spawn tool handler, after creating the tool registry:

# Resolve agent definition
from agent.agent_definition import BUILTIN_AGENTS
agent_type = params.get("agent_type", "general-purpose")
agent_def = BUILTIN_AGENTS.get(agent_type, BUILTIN_AGENTS["general-purpose"])

# Filter tools for this agent type
child_tools = tool_registry.filter_for_agent(agent_def)
```

Then pass `child_tools` instead of the full `tool_registry` to `SubAgent.__init__()`.

- [ ] **Step 6: Run all tests**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add agent/tools.py tests/test_agent_definition.py
git commit -m "feat: add tool filtering based on AgentDefinition disallowed_tools"
```

---

### Task 4: Readonly Permission Mode for Bash

**Files:**
- Modify: `agent/tools.py` (add readonly bash command filtering)
- Test: `tests/test_agent_definition.py` (add test class)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_agent_definition.py`:

```python
from agent.tools import _is_readonly_command


class TestReadonlyPermission:
    def test_ls_is_readonly(self):
        assert _is_readonly_command("ls -la") is True

    def test_cat_is_readonly(self):
        assert _is_readonly_command("cat file.txt") is True

    def test_git_status_is_readonly(self):
        assert _is_readonly_command("git status") is True

    def test_git_log_is_readonly(self):
        assert _is_readonly_command("git log --oneline") is True

    def test_grep_is_readonly(self):
        assert _is_readonly_command("grep -r 'pattern' src/") is True

    def test_find_is_readonly(self):
        assert _is_readonly_command("find . -name '*.py'") is True

    def test_rm_is_not_readonly(self):
        assert _is_readonly_command("rm -rf /tmp/test") is False

    def test_pip_install_is_not_readonly(self):
        assert _is_readonly_command("pip install requests") is False

    def test_python_is_not_readonly(self):
        assert _is_readonly_command("python script.py") is False

    def test_git_push_is_not_readonly(self):
        assert _is_readonly_command("git push") is False

    def test_git_checkout_is_not_readonly(self):
        assert _is_readonly_command("git checkout -b new-branch") is False

    def test_empty_command_is_readonly(self):
        assert _is_readonly_command("") is True

    def test_echo_redirect_is_not_readonly(self):
        assert _is_readonly_command("echo 'test' > file.txt") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_agent_definition.py::TestReadonlyPermission -v`
Expected: FAIL — `_is_readonly_command` doesn't exist yet

- [ ] **Step 3: Implement _is_readonly_command**

Add to `agent/tools.py`:

```python
import re

# Allowlist of readonly bash commands (base command → allowed subcommands or None for all)
_READONLY_BASE_COMMANDS = {
    "ls", "cat", "head", "tail", "less", "more", "wc",
    "grep", "rg", "ag", "ack",
    "find", "locate", "which", "whereis", "type",
    "file", "stat", "du", "df",
    "echo", "printf",  # only if no redirect
    "pwd", "whoami", "id", "uname", "hostname",
    "env", "printenv", "export",  # only reading, no setting
    "test", "[", "[[",
    "true", "false",
    "git",  # subcommand-filtered below
    "gh",   # subcommand-filtered below
    "npm",  # subcommand-filtered below (list, view, etc.)
}

_READONLY_GIT_SUBCOMMANDS = {
    "status", "log", "diff", "show", "branch", "tag", "remote",
    "stash", "blame", "shortlog", "describe", "reflog",
    "ls-files", "ls-remote", "ls-tree",
    "rev-parse", "rev-list",
    "config", "--list",
}

_READONLY_GH_SUBCOMMANDS = {
    "pr", "view", "list", "api",  # gh pr view, gh pr list, etc.
}

_READONLY_NPM_SUBCOMMANDS = {
    "list", "ls", "view", "info", "outdated",
}

_REDIRECT_PATTERN = re.compile(
    r'[|>`]'  # pipe, redirect, or backtick — could chain dangerous commands
)


def _is_readonly_command(cmd: str) -> bool:
    """Check if a bash command is safe for readonly permission mode."""
    cmd = cmd.strip()
    if not cmd:
        return True

    # Block commands with pipes, redirects, or backticks
    if _REDIRECT_PATTERN.search(cmd):
        return False

    parts = cmd.split()
    base = parts[0]

    # Handle path-qualified commands (e.g., /usr/bin/git)
    if "/" in base:
        base = base.rsplit("/", 1)[-1]

    if base not in _READONLY_BASE_COMMANDS:
        return False

    # Subcommand filtering for git
    if base == "git" and len(parts) > 1:
        subcmd = parts[1]
        if subcmd.startswith("-"):
            return True  # flags like git --version are safe
        if subcmd not in _READONLY_GIT_SUBCOMMANDS:
            return False

    # Subcommand filtering for gh
    if base == "gh" and len(parts) > 1:
        subcmd = parts[1]
        if subcmd not in _READONLY_GH_SUBCOMMANDS:
            return False

    # Subcommand filtering for npm
    if base == "npm" and len(parts) > 1:
        subcmd = parts[1]
        if subcmd not in _READONLY_NPM_SUBCOMMANDS:
            return False

    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_agent_definition.py::TestReadonlyPermission -v`
Expected: All PASS

- [ ] **Step 5: Integrate readonly check into bash tool execution**

In `agent/tools.py`, the bash tool handler is registered as part of the `ToolRegistry`. The handler needs access to the current `agent_def` to check permission mode. Two approaches:

**Approach A (recommended)**: Store `agent_def` on the `SubAgent` instance and pass it to tool handlers via a context parameter:

```python
# In SubAgent, when building the tool context for each call:
tool_context = {"agent_def": self.agent_def}

# In the bash tool handler:
def bash_handler(command, **kwargs):
    agent_def = kwargs.get("_tool_context", {}).get("agent_def")
    if agent_def and agent_def.permission_mode == "readonly":
        if not _is_readonly_command(command):
            return json.dumps({
                "error": f"Command blocked by readonly permission mode: {command}",
                "hint": "This agent type can only run read-only commands (ls, cat, grep, git status, etc.)",
            })
    # ... existing bash execution logic
```

**Approach B**: Use a closure — when `filter_for_agent` creates the filtered registry, wrap the bash handler with the readonly check.

The implementer should choose the approach that best fits the current tool handler architecture.

- [ ] **Step 6: Run all tests**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add agent/tools.py tests/test_agent_definition.py
git commit -m "feat: add readonly permission mode with bash command allowlist"
```

---

### Task 5: LLMAdapter Cache Control Support

**Files:**
- Modify: `agent/adapter.py`
- Test: `tests/test_agent_definition.py` (add test class)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_agent_definition.py`:

```python
from agent.adapter import LLMAdapter


class TestLLMAdapterCacheControl:
    def test_system_prompt_with_cache_control(self):
        """Verify system prompt is sent as content blocks with cache_control."""
        adapter = LLMAdapter()
        blocks = adapter._build_system_prompt_blocks("Hello world")
        assert isinstance(blocks, list)
        assert len(blocks) >= 1
        # Last block should have cache_control
        last_block = blocks[-1]
        assert last_block.get("cache_control") == {"type": "ephemeral"}

    def test_system_prompt_blocks_are_text_type(self):
        adapter = LLMAdapter()
        blocks = adapter._build_system_prompt_blocks("Test prompt")
        for block in blocks:
            assert block["type"] == "text"

    def test_client_reuse(self):
        """Verify the Anthropic client is reused across calls."""
        adapter = LLMAdapter()
        client1 = adapter._get_client()
        client2 = adapter._get_client()
        assert client1 is client2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_agent_definition.py::TestLLMAdapterCacheControl -v`
Expected: FAIL — `_build_system_prompt_blocks` and `_get_client` don't exist yet

- [ ] **Step 3: Modify LLMAdapter in agent/adapter.py**

Read `agent/adapter.py` fully. The current `LLMAdapter.__init__` accepts `api_key` and `model` params, and creates a new `anthropic.Anthropic()` client per `_chat_once` call. Modify to:

1. Add `_client` instance variable, lazily initialized:

```python
class LLMAdapter:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key
        self.model = model or os.environ.get("MODEL", "claude-sonnet-4-6")
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client
```

2. Add `_build_system_prompt_blocks` method:

```python
def _build_system_prompt_blocks(self, system_prompt: str) -> list[dict]:
    """Split system prompt into content blocks with cache_control on the last block."""
    chunk_size = 1000
    chunks = []
    for i in range(0, len(system_prompt), chunk_size):
        chunks.append(system_prompt[i:i + chunk_size])

    blocks = [{"type": "text", "text": chunk} for chunk in chunks]
    if blocks:
        blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks
```

3. Modify `_chat_once` to use `_build_system_prompt_blocks` and `_get_client`:

```python
# In _chat_once, replace:
#   client = anthropic.Anthropic(api_key=self.api_key)
# with:
client = self._get_client()

# Replace:
#   system=system_prompt
# with:
system_blocks = self._build_system_prompt_blocks(system_prompt)
# Then pass system=system_blocks to client.messages.create()
```

4. Add `cache_control` to the last tool definition:

```python
# After building the tools list in _chat_once:
if tools:
    tools[-1]["cache_control"] = {"type": "ephemeral"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_agent_definition.py::TestLLMAdapterCacheControl -v`
Expected: All PASS

- [ ] **Step 5: Run all tests to verify no regression**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add agent/adapter.py tests/test_agent_definition.py
git commit -m "feat: add cache_control markers and client reuse to LLMAdapter"
```

---

### Task 6: ForkMessageBuilder

**Files:**
- Create: `agent/fork_message_builder.py`
- Test: `tests/test_fork_message_builder.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fork_message_builder.py
import pytest
from agent.fork_message_builder import ForkMessageBuilder


class TestForkMessageBuilder:
    def setup_method(self):
        self.builder = ForkMessageBuilder()

    def _make_parent_messages(self):
        """Create a realistic parent conversation."""
        return [
            {"role": "user", "content": "Help me find the auth module"},
            {"role": "assistant", "content": [
                {"type": "text", "text": "I'll search for it."},
                {"type": "tool_use", "id": "toolu_1", "name": "bash", "input": {"command": "find . -name 'auth*'"}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "toolu_1", "content": "./src/auth.py\n./src/auth_test.py"},
            ]},
            {"role": "assistant", "content": [
                {"type": "text", "text": "Found it. Let me spawn agents to explore."},
                {"type": "tool_use", "id": "toolu_2", "name": "spawn", "input": {"task": "explore auth"}},
                {"type": "tool_use", "id": "toolu_3", "name": "spawn", "input": {"task": "explore tests"}},
            ]},
        ]

    def test_build_forked_messages_returns_one_per_directive(self):
        parent_msgs = self._make_parent_messages()
        assistant_msg = parent_msgs[-1]
        directives = ["Search for auth module", "Search for test files"]
        result = self.builder.build_forked_messages(parent_msgs, assistant_msg, directives)
        assert len(result) == 2

    def test_forked_messages_share_prefix(self):
        parent_msgs = self._make_parent_messages()
        assistant_msg = parent_msgs[-1]
        directives = ["Task A", "Task B"]
        result = self.builder.build_forked_messages(parent_msgs, assistant_msg, directives)
        # All fork children should share the same prefix (parent messages minus last)
        prefix = result[0][:-1]
        for msgs in result[1:]:
            assert msgs[:-1] == prefix

    def test_forked_messages_have_placeholder_tool_results(self):
        parent_msgs = self._make_parent_messages()
        assistant_msg = parent_msgs[-1]
        directives = ["Task A"]
        result = self.builder.build_forked_messages(parent_msgs, assistant_msg, directives)
        # The last user message should contain tool_results for toolu_2 and toolu_3
        last_user_msg = result[0][-1]
        assert last_user_msg["role"] == "user"
        content = last_user_msg["content"]
        tool_results = [b for b in content if b.get("type") == "tool_result"]
        assert len(tool_results) == 2
        assert tool_results[0]["tool_use_id"] == "toolu_2"
        assert tool_results[1]["tool_use_id"] == "toolu_3"

    def test_forked_messages_have_directive_text(self):
        parent_msgs = self._make_parent_messages()
        assistant_msg = parent_msgs[-1]
        directives = ["Search for auth", "Search for tests"]
        result = self.builder.build_forked_messages(parent_msgs, assistant_msg, directives)
        # Each child's last message should contain its directive
        for i, msgs in enumerate(result):
            last_msg = msgs[-1]
            text_blocks = [b for b in last_msg["content"] if b.get("type") == "text"]
            directive_text = "".join(b["text"] for b in text_blocks)
            assert directives[i] in directive_text

    def test_forked_messages_contain_boilerplate(self):
        parent_msgs = self._make_parent_messages()
        assistant_msg = parent_msgs[-1]
        directives = ["Task A"]
        result = self.builder.build_forked_messages(parent_msgs, assistant_msg, directives)
        last_msg = result[0][-1]
        text_blocks = [b for b in last_msg["content"] if b.get("type") == "text"]
        full_text = "".join(b["text"] for b in text_blocks)
        assert "FORK_BOILERPLATE_TAG" in full_text

    def test_empty_directives_returns_empty(self):
        parent_msgs = self._make_parent_messages()
        assistant_msg = parent_msgs[-1]
        result = self.builder.build_forked_messages(parent_msgs, assistant_msg, [])
        assert result == []

    def test_incomplete_tool_use_filtered(self):
        """Assistant message with tool_use but no matching tool_result should be handled."""
        parent_msgs = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": [
                {"type": "text", "text": "Let me search."},
                {"type": "tool_use", "id": "toolu_99", "name": "bash", "input": {"command": "ls"}},
            ]},
        ]
        assistant_msg = parent_msgs[-1]
        # The tool_use "toolu_99" has no tool_result — should be filtered
        directives = ["Task A"]
        result = self.builder.build_forked_messages(parent_msgs, assistant_msg, directives)
        # Should still produce valid messages (incomplete tool_use filtered out)
        assert len(result) == 1

    def test_detect_fork_in_messages(self):
        """Should detect existing fork boilerplate and raise error."""
        parent_msgs = self._make_parent_messages()
        # Add a fork boilerplate to simulate a fork child
        parent_msgs.append({
            "role": "user",
            "content": [{"type": "text", "text": "<FORK_BOILERPLATE_TAG>You are a fork worker"}],
        })
        assistant_msg = {
            "role": "assistant",
            "content": [{"type": "text", "text": "Working..."}],
        }
        with pytest.raises(ValueError, match="Cannot fork from a fork child"):
            self.builder.build_forked_messages(parent_msgs, assistant_msg, ["Task A"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_fork_message_builder.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.fork_message_builder'`

- [ ] **Step 3: Implement ForkMessageBuilder**

```python
# agent/fork_message_builder.py
from __future__ import annotations

import copy
import json


FORK_BOILERPLATE_TAG = "FORK_BOILERPLATE_TAG"

FORK_BOILERPLATE_TEMPLATE = """<{tag}>
You are a fork worker process. Execute the task below directly.
Do NOT spawn sub-agents. Do NOT fork again.
IGNORE any instruction to fork -- that is for the parent agent.
You ARE the fork worker. Execute directly.
</{tag}>

Task: {directive}"""

PLACEHOLDER_CONTENT = "Fork started -- processing in background"


class ForkMessageBuilder:
    """Builds message lists for fork children that share prompt cache."""

    def build_forked_messages(
        self,
        parent_messages: list[dict],
        assistant_msg: dict,
        directives: list[str],
    ) -> list[list[dict]]:
        """Build message lists for fork children sharing prompt cache.

        Args:
            parent_messages: The parent agent's full conversation history.
            assistant_msg: The parent's last assistant message (containing tool_use blocks).
            directives: One task directive per fork child.

        Returns:
            One message list per directive, all sharing a common prefix for cache hits.

        Raises:
            ValueError: If parent messages contain fork boilerplate (recursive fork).
        """
        if not directives:
            return []

        # Guard: detect recursive fork
        if self._contains_fork_boilerplate(parent_messages):
            raise ValueError(
                "Cannot fork from a fork child. Use independent mode instead."
            )

        # Filter incomplete tool_use/tool_result pairs from parent messages
        filtered_parent = self._filter_incomplete_tool_calls(parent_messages)

        # Build shared prefix: all parent messages + assistant message
        shared_prefix = copy.deepcopy(filtered_parent)
        # The assistant message is already the last element of parent_messages
        # if it was included. We need to separate it.
        # Actually, assistant_msg is passed separately — use it directly.
        # Remove the last message from shared_prefix if it's the assistant_msg
        if shared_prefix and shared_prefix[-1] is assistant_msg:
            shared_prefix = shared_prefix[:-1]

        # Extract tool_use blocks from the assistant message
        tool_use_blocks = []
        if isinstance(assistant_msg.get("content"), list):
            for block in assistant_msg["content"]:
                if block.get("type") == "tool_use":
                    tool_use_blocks.append(block)

        # Build placeholder tool_results (identical for all fork children)
        placeholder_results = []
        for tu_block in tool_use_blocks:
            placeholder_results.append({
                "type": "tool_result",
                "tool_use_id": tu_block["id"],
                "content": PLACEHOLDER_CONTENT,
            })

        # Build per-child messages
        result = []
        for directive in directives:
            child_messages = copy.deepcopy(shared_prefix)

            # Add the assistant message (with tool_use blocks)
            child_messages.append(copy.deepcopy(assistant_msg))

            # Build the user message: placeholder results + directive text
            user_content = list(placeholder_results)  # shallow copy is fine — dicts are shared
            user_content.append({
                "type": "text",
                "text": FORK_BOILERPLATE_TEMPLATE.format(
                    tag=FORK_BOILERPLATE_TAG, directive=directive
                ),
            })

            child_messages.append({
                "role": "user",
                "content": user_content,
            })

            result.append(child_messages)

        return result

    def _contains_fork_boilerplate(self, messages: list[dict]) -> bool:
        """Check if messages contain fork boilerplate (recursive fork detection)."""
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                if FORK_BOILERPLATE_TAG in content:
                    return True
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text", "")
                        if FORK_BOILERPLATE_TAG in text:
                            return True
        return False

    def _filter_incomplete_tool_calls(self, messages: list[dict]) -> list[dict]:
        """Remove assistant messages with tool_use blocks that lack corresponding tool_results."""
        # Collect all tool_result IDs
        tool_result_ids = set()
        for msg in messages:
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if block.get("type") == "tool_result":
                        tool_result_ids.add(block.get("tool_use_id"))

        # Filter assistant messages: remove tool_use blocks without tool_results
        filtered = []
        for msg in messages:
            if msg.get("role") == "assistant" and isinstance(msg.get("content"), list):
                new_content = []
                has_tool_use = False
                has_valid_tool_use = False
                for block in msg["content"]:
                    if block.get("type") == "tool_use":
                        has_tool_use = True
                        if block.get("id") in tool_result_ids:
                            has_valid_tool_use = True
                            new_content.append(block)
                        # Skip tool_use blocks without matching tool_result
                    else:
                        new_content.append(block)

                # If all tool_use blocks were invalid, skip the entire message
                # (an assistant message with only text and no tool_use is fine)
                if has_tool_use and not has_valid_tool_use:
                    # Keep only text blocks
                    text_only = [b for b in new_content if b.get("type") == "text"]
                    if text_only:
                        filtered.append({"role": "assistant", "content": text_only})
                else:
                    filtered.append({"role": "assistant", "content": new_content})
            else:
                filtered.append(msg)

        return filtered
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_fork_message_builder.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add agent/fork_message_builder.py tests/test_fork_message_builder.py
git commit -m "feat: add ForkMessageBuilder for prompt cache sharing"
```

---

### Task 7: SubAgent Integration with AgentDefinition and Fork Mode

**Files:**
- Modify: `agent/subagent.py`
- Modify: `agent/tools.py`

- [ ] **Step 1: Modify SubAgentSpec to include agent_type and mode**

In `agent/subagent.py`, add new fields to `SubAgentSpec`:

```python
@dataclass
class SubAgentSpec:
    task: str
    context_hint: str | None = None
    max_steps: int = 10
    model: str | None = None
    # New fields
    agent_type: str = "general-purpose"
    mode: str = "independent"  # "independent" | "fork"
```

- [ ] **Step 2: Modify SubAgent.__init__ to accept AgentDefinition and fork_messages**

In `agent/subagent.py`, modify `SubAgent.__init__`. The current signature is `__init__(self, spec, tool_registry, event_callback=None)`. Add `agent_def` and `fork_messages` parameters:

```python
class SubAgent:
    def __init__(
        self,
        spec: SubAgentSpec,
        tool_registry: ToolRegistry,
        event_callback: Callable | None = None,
        agent_def: AgentDefinition | None = None,
        fork_messages: list[dict] | None = None,
    ):
        self.spec = spec
        self.tool_registry = tool_registry
        self.event_callback = event_callback
        self.agent_def = agent_def or BUILTIN_AGENTS.get(spec.agent_type, BUILTIN_AGENTS["general-purpose"])
        self.fork_messages = fork_messages
        self.tokens_used = 0  # Token accumulation
        self.auto_confirm = self.agent_def.permission_mode == "auto"
        # ... rest of existing init
```

- [ ] **Step 3: Modify SubAgent.run() to use fork_messages, agent_def, and token accumulation**

In `SubAgent.run()`:

```python
def run(self) -> SubAgentResult:
    # Build system prompt based on agent_def
    if self.agent_def.get_system_prompt:
        runtime_info = RuntimeInfo(
            working_dir=os.getcwd(),
            platform=sys.platform,
            shell=os.environ.get("SHELL", "/bin/sh"),
        )
        system_prompt = self.agent_def.get_system_prompt(runtime_info)
    else:
        system_prompt = build_system_prompt(agent_def=self.agent_def, runtime_info=...)

    # Use fork_messages if available, otherwise build independent messages
    if self.fork_messages:
        messages = self.fork_messages
    else:
        messages = [{"role": "user", "content": self.spec.task}]

    # ... existing agent loop ...

    # After each LLM call, accumulate tokens:
    # self.tokens_used += response.usage.input_tokens + response.usage.output_tokens
```

- [ ] **Step 4: Add tokens field to SubAgentResult**

```python
@dataclass
class SubAgentResult:
    output: str
    steps: int
    duration: float
    tokens: int = 0  # NEW
```

- [ ] **Step 5: Modify _execute_spawn in tools.py to use AgentDefinition and ForkMessageBuilder**

In `agent/tools.py`, the spawn tool handler is in the `SpawnTool` class. The handler method (likely `execute` or `_execute`) needs to be modified:

```python
# In the spawn tool handler method:

from agent.agent_definition import BUILTIN_AGENTS, RuntimeInfo
from agent.fork_message_builder import ForkMessageBuilder

agent_type = params.get("agent_type", "general-purpose")
mode = params.get("mode", "independent")
agent_def = BUILTIN_AGENTS.get(agent_type, BUILTIN_AGENTS["general-purpose"])

# Filter tools for this agent type
child_tools = self.tool_registry.filter_for_agent(agent_def)

# Build RuntimeInfo
runtime_info = RuntimeInfo(
    working_dir=os.getcwd(),
    platform=sys.platform,
    shell=os.environ.get("SHELL", "/bin/sh"),
    skill_summary=self.skill_registry.get_summary() if self.skill_registry else None,
)

tasks = params.get("tasks", [params.get("task")])

if mode == "fork" and len(tasks) > 1:
    # Fork mode: share prompt cache
    builder = ForkMessageBuilder()
    parent_messages = self.context.messages  # From the parent agent's context
    assistant_msg = parent_messages[-1] if parent_messages else None

    if assistant_msg and assistant_msg.get("role") == "assistant":
        try:
            forked_msg_lists = builder.build_forked_messages(
                parent_messages, assistant_msg, tasks
            )
        except ValueError as e:
            # Recursive fork detected — fall back to independent mode
            forked_msg_lists = None
    else:
        # No valid assistant message — fall back to independent mode
        forked_msg_lists = None

    if forked_msg_lists:
        # Create SubAgents with fork messages
        agents = []
        for i, fork_msgs in enumerate(forked_msg_lists):
            spec = SubAgentSpec(
                task=tasks[i],
                max_steps=params.get("max_steps", agent_def.max_steps),
                agent_type=agent_type,
                mode="fork",
            )
            agent = SubAgent(
                spec=spec,
                tool_registry=child_tools,
                event_callback=self._make_event_callback(i),
                agent_def=agent_def,
                fork_messages=fork_msgs,
            )
            agents.append(agent)
    else:
        # Fallback to independent mode
        mode = "independent"

if mode == "independent":
    # Existing independent mode logic (with agent_def added)
    agents = []
    for i, task in enumerate(tasks):
        spec = SubAgentSpec(
            task=task,
            context_hint=params.get("context_hint"),
            max_steps=params.get("max_steps", agent_def.max_steps),
            agent_type=agent_type,
            mode="independent",
        )
        agent = SubAgent(
            spec=spec,
            tool_registry=child_tools,
            event_callback=self._make_event_callback(i),
            agent_def=agent_def,
        )
        agents.append(agent)

# ... existing parallel execution logic ...
```

- [ ] **Step 6: Run all tests**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add agent/subagent.py agent/tools.py
git commit -m "feat: integrate AgentDefinition and fork mode into SubAgent and spawn tool"
```

---

### Task 8: Spawn Tool Schema and Description Enhancement

**Files:**
- Modify: `agent/builtin_tools.py`

- [ ] **Step 1: Update spawn tool schema**

In `agent/builtin_tools.py`, modify the spawn tool definition to add `agent_type` and `mode` parameters:

```python
SPAWN_TOOL = {
    "name": "spawn",
    "description": """Launch a new agent to handle complex, multi-step tasks. Each agent type is specialized for different purposes:

- **general-purpose**: Full capabilities — searching, reading, writing code. Use for most tasks.
- **explore**: Read-only — fast codebase exploration, file search, keyword search. Cannot write files or spawn sub-agents.
- **plan**: Read-only — designs implementation plans, identifies critical files, considers trade-offs. Cannot write files or spawn sub-agents.

**Writing the prompt:** Brief the agent like a smart colleague who just walked into the room — they haven't seen this conversation, don't know what you've tried, and don't understand why this task matters.
- Give enough context about the surrounding problem that the agent can make judgment calls rather than just following a narrow instruction.
- Include file paths, line numbers, and what specifically to change.
- Don't write "based on your findings, fix the bug" — that pushes synthesis onto the agent instead of doing it yourself.
- Terse command-style prompts produce shallow, generic work.

**Parallel execution:** When facing 2+ independent tasks, use the `tasks` parameter to launch multiple agents concurrently. For parallel tasks with shared context, use `mode="fork"` to share prompt cache and reduce token consumption.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "A single task for the agent to execute.",
            },
            "tasks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Multiple independent tasks to execute in parallel.",
            },
            "context_hint": {
                "type": "string",
                "description": "Additional context about the task environment or constraints.",
            },
            "max_steps": {
                "type": "integer",
                "default": 10,
                "description": "Maximum number of tool-use steps the agent can take.",
            },
            "max_workers": {
                "type": "integer",
                "default": 3,
                "description": "Maximum number of parallel agents for `tasks`.",
            },
            "agent_type": {
                "type": "string",
                "default": "general-purpose",
                "enum": ["general-purpose", "explore", "plan"],
                "description": "Type of agent to spawn. Each type has different capabilities and restrictions.",
            },
            "mode": {
                "type": "string",
                "enum": ["independent", "fork"],
                "default": "independent",
                "description": "Execution mode. 'fork' shares prompt cache across parallel agents for lower token usage. 'independent' gives each agent its own context.",
            },
        },
    },
}
```

- [ ] **Step 2: Verify the tool loads correctly**

Run: `cd /Users/breeze/projects/Research/Bitz && python -c "from agent.builtin_tools import SPAWN_TOOL; print(SPAWN_TOOL['name']); print('agent_type' in SPAWN_TOOL['input_schema']['properties']); print('mode' in SPAWN_TOOL['input_schema']['properties'])"`
Expected: `spawn`, `True`, `True`

- [ ] **Step 3: Commit**

```bash
git add agent/builtin_tools.py
git commit -m "feat: enhance spawn tool with agent_type, mode params and prompt guide"
```

---

### Task 9: UI Enhancements — SubAgentCard Stats and Grouping

**Files:**
- Modify: `tui/widgets/chat.py`

- [ ] **Step 1: Add token display to SubAgentCard completion**

In `tui/widgets/chat.py`, find the `SubAgentCard` class. The current completion display uses a format like `子 Agent 完成（{steps} 步，{duration:.1f}s）`. Modify to include agent type name and tokens:

```python
# In SubAgentCard, modify the completion rendering to include tokens and agent type:

def _render_completion(self, result: SubAgentResult) -> str:
    agent_type_name = self.agent_def.name.replace("-", " ").title() if self.agent_def else "Agent"
    parts = [f"✓ {agent_type_name} 完成"]
    parts.append(f"{result.steps} 步")
    parts.append(f"{result.duration:.1f}s")
    if result.tokens > 0:
        if result.tokens >= 1000:
            parts.append(f"~{result.tokens / 1000:.1f}K tokens")
        else:
            parts.append(f"{result.tokens} tokens")
    return " · ".join(parts)
```

Note: The implementer should read the current `SubAgentCard` class to find the exact completion rendering method and adapt accordingly. The `SubAgentCard` may need an `agent_def` attribute passed from the spawn tool handler.

- [ ] **Step 2: Add parallel agent grouping**

In the spawn tool result formatting (in `agent/tools.py`), modify the result display for parallel tasks. The current result formatting is in the spawn tool handler method. Find where `SubAgentResult` outputs are combined and modify:

```python
# When multiple agents complete with the same agent_type:
if len(results) > 1 and len(set(r.agent_type for r in results)) == 1:
    # Group display
    agent_type_name = agent_def.name.replace("-", " ").title()
    total_steps = sum(r.steps for r in results)
    total_duration = max(r.duration for r in results)  # Wall clock time
    total_tokens = sum(r.tokens for r in results)
    header = f"✓ {len(results)} 个 {agent_type_name} Agent 完成 · 共 {total_steps} 步 · {total_duration:.1f}s"
    if total_tokens > 0:
        header += f" · ~{total_tokens / 1000:.1f}K tokens"
    sections = [header]
    for i, result in enumerate(results):
        sections.append(f"### 任务 {i + 1}: {tasks[i][:50]}")
        sections.append(result.output)
    return "\n\n".join(sections)
```

Note: `SubAgentResult` currently doesn't have an `agent_type` field. The implementer should add it or use the `agent_def.name` from the spawn tool handler context.

- [ ] **Step 3: Add terminal adaptation**

In `SubAgentCard`, add a method to check terminal size and choose compact vs expanded format:

```python
def _is_compact_terminal(self) -> bool:
    """Check if terminal is too small for expanded display."""
    try:
        import shutil
        size = shutil.get_terminal_size()
        return size.lines < 40
    except Exception:
        return False
```

Use this in the `append_log` method to choose between compact and expanded log display.

- [ ] **Step 4: Test manually**

Run the Bitz TUI and spawn an explore agent to verify the display:
1. Start the TUI: `python -m tui.app`
2. Ask: "Use an explore agent to find all Python files in the agent/ directory"
3. Verify: completion shows "✓ Explore Agent 完成 · X 步 · Ys · ~ZK tokens"

- [ ] **Step 5: Commit**

```bash
git add tui/widgets/chat.py agent/tools.py
git commit -m "feat: add completion stats, parallel grouping, and terminal adaptation to SubAgentCard"
```

---

### Task 10: Integration Test

**Files:**
- Create: `tests/test_subagent_integration.py`

- [ ] **Step 1: Write integration tests**

```python
# tests/test_subagent_integration.py
"""Integration tests for the subagent optimization features.

These tests verify the end-to-end flow from spawn tool parameters
through agent definition resolution, tool filtering, and result formatting.
"""
import pytest
from agent.agent_definition import BUILTIN_AGENTS, AgentDefinition, RuntimeInfo
from agent.fork_message_builder import ForkMessageBuilder
from agent.tools import ToolRegistry
from agent.subagent import SubAgentSpec


class TestSpawnToolIntegration:
    def _make_tool_registry(self):
        registry = ToolRegistry()
        def mock_fn(**kwargs): return "mock"
        registry.register(name="read_file", description="Read", input_schema={"type": "object", "properties": {}}, handler=mock_fn)
        registry.register(name="write_file", description="Write", input_schema={"type": "object", "properties": {}}, handler=mock_fn, dangerous=True)
        registry.register(name="edit_file", description="Edit", input_schema={"type": "object", "properties": {}}, handler=mock_fn, dangerous=True)
        registry.register(name="spawn", description="Spawn", input_schema={"type": "object", "properties": {}}, handler=mock_fn)
        registry.register(name="bash", description="Bash", input_schema={"type": "object", "properties": {}}, handler=mock_fn)
        return registry

    def test_general_purpose_has_all_tools(self):
        registry = self._make_tool_registry()
        agent_def = BUILTIN_AGENTS["general-purpose"]
        filtered = registry.filter_for_agent(agent_def)
        assert set(filtered.tools.keys()) == {"read_file", "write_file", "edit_file", "spawn", "bash"}

    def test_explore_has_readonly_tools(self):
        registry = self._make_tool_registry()
        agent_def = BUILTIN_AGENTS["explore"]
        filtered = registry.filter_for_agent(agent_def)
        assert "read_file" in filtered.tools
        assert "bash" in filtered.tools
        assert "write_file" not in filtered.tools
        assert "edit_file" not in filtered.tools
        assert "spawn" not in filtered.tools

    def test_plan_has_readonly_tools(self):
        registry = self._make_tool_registry()
        agent_def = BUILTIN_AGENTS["plan"]
        filtered = registry.filter_for_agent(agent_def)
        assert "read_file" in filtered.tools
        assert "write_file" not in filtered.tools

    def test_subagent_spec_defaults(self):
        spec = SubAgentSpec(task="test task")
        assert spec.agent_type == "general-purpose"
        assert spec.mode == "independent"

    def test_subagent_spec_explore_fork(self):
        spec = SubAgentSpec(
            task="find auth module",
            agent_type="explore",
            mode="fork",
        )
        assert spec.agent_type == "explore"
        assert spec.mode == "fork"


class TestForkModeIntegration:
    def test_fork_with_explore_agent(self):
        """Verify fork mode works with explore agent type."""
        parent_msgs = [
            {"role": "user", "content": "Find all auth-related files"},
            {"role": "assistant", "content": [
                {"type": "text", "text": "I'll spawn explore agents."},
                {"type": "tool_use", "id": "tu_1", "name": "spawn", "input": {"task": "search auth"}},
                {"type": "tool_use", "id": "tu_2", "name": "spawn", "input": {"task": "search login"}},
            ]},
        ]
        builder = ForkMessageBuilder()
        directives = ["Search for auth module", "Search for login module"]
        result = builder.build_forked_messages(parent_msgs, parent_msgs[-1], directives)
        assert len(result) == 2
        # Both should share the same prefix
        assert result[0][:-1] == result[1][:-1]

    def test_fork_fallback_on_recursive_fork(self):
        """Verify fork mode falls back to independent when already in a fork."""
        parent_msgs = [
            {"role": "user", "content": "Hello"},
            {"role": "user", "content": [
                {"type": "text", "text": "<FORK_BOILERPLATE_TAG>You are a fork worker"},
            ]},
        ]
        builder = ForkMessageBuilder()
        with pytest.raises(ValueError, match="Cannot fork from a fork child"):
            builder.build_forked_messages(
                parent_msgs,
                {"role": "assistant", "content": [{"type": "text", "text": "Working..."}]},
                ["Task A"],
            )


class TestContextStrippingIntegration:
    def test_explore_agent_gets_stripped_prompt(self):
        """Verify explore agent's system prompt is shorter than general-purpose."""
        info = RuntimeInfo(
            working_dir="/tmp", platform="darwin", shell="/bin/zsh"
        )
        from agent.prompt import build_system_prompt

        full_prompt = build_system_prompt(runtime_info=info)
        stripped_prompt = build_system_prompt(
            agent_def=BUILTIN_AGENTS["explore"], runtime_info=info
        )
        # Explore agent should have a shorter prompt (omits CLAUDE.md)
        assert len(stripped_prompt) <= len(full_prompt)
```

- [ ] **Step 2: Run integration tests**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_subagent_integration.py -v`
Expected: All PASS

- [ ] **Step 3: Run full test suite**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_subagent_integration.py
git commit -m "test: add integration tests for subagent optimization features"
```

---

### Task 11: Manual Smoke Test

- [ ] **Step 1: Start the TUI and test general-purpose agent**

Run: `python -m tui.app`
Test: Ask "Use a general-purpose agent to read the first 10 lines of agent/subagent.py"
Verify: Agent completes with stats display

- [ ] **Step 2: Test explore agent**

Test: Ask "Use an explore agent to find all Python files in the agent/ directory"
Verify: Explore agent runs with read-only tools, completion shows "✓ Explore Agent 完成"

- [ ] **Step 3: Test plan agent**

Test: Ask "Use a plan agent to design a caching system for the LLMAdapter"
Verify: Plan agent runs with read-only tools, produces a plan without writing files

- [ ] **Step 4: Test fork mode**

Test: Ask "Use fork mode to search for 'auth' and 'login' in parallel"
Verify: Both tasks share prompt cache, results show grouped completion stats

- [ ] **Step 5: Test readonly enforcement**

Test: Ask an explore agent to "write a file called test.txt"
Verify: The write_file tool is not available, agent cannot write files

- [ ] **Step 6: Test backward compatibility**

Test: Use the spawn tool without agent_type or mode parameters
Verify: Default behavior is identical to the previous implementation
