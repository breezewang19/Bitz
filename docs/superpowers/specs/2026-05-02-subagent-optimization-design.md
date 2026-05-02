# SubAgent Optimization Design

Optimize the Bitz Python subagent system by referencing Claude Code's TypeScript agent architecture. Goals: improve performance (prompt cache sharing), expand capabilities (role-based agent types), and enhance UX (progress grouping, completion stats).

Approach: incremental enhancement on the existing `SubAgent`/`SubAgentSpec` architecture, maintaining backward compatibility with the current `spawn` tool interface.

## 1. AgentDefinition Data Model

New file: `agent/agent_definition.py`

```python
@dataclass
class RuntimeInfo:
    working_dir: str
    platform: str
    shell: str
    skill_summary: str | None

@dataclass
class AgentDefinition:
    name: str                                    # "explore", "plan", "general-purpose"
    description: str                             # Description shown to the LLM
    disallowed_tools: list[str]                  # Denylist (safer than allowlist)
    model: str | None                            # None = inherit parent model
    get_system_prompt: Callable[[RuntimeInfo], str] | None = None  # Dynamic prompt builder; if None, use build_system_prompt()
    omit_claude_md: bool = False                 # Skip CLAUDE.md rules injection
    max_steps: int = 10                          # Default max steps
    permission_mode: str = "auto"                # "auto" | "readonly"
```

**Removed fields**: `background` (not specified in this phase), `omit_git_status` (no git status injection exists in current `build_system_prompt()`).

**Renamed `AgentContext` → `RuntimeInfo`**: Avoids collision with existing `Context` class in `agent/context.py` that manages conversation messages.

**`get_system_prompt` vs `build_system_prompt` interaction**: If `get_system_prompt` is provided, it completely replaces `build_system_prompt()`. If `None` (default), `build_system_prompt()` is called with the `AgentDefinition` for conditional section injection. These are mutually exclusive — never both applied.

### Built-in Agent Definitions

| Agent | disallowed_tools | model | omit_claude_md | permission_mode |
|-------|-----------------|-------|----------------|-----------------|
| general-purpose | [] | None (inherit) | False | auto |
| explore | [write_file, edit_file, spawn] | None (inherit) | True | readonly |
| plan | [write_file, edit_file, spawn] | None (inherit) | True | readonly |

### Design Decisions

- **Denylist over allowlist**: New tools are available by default; explicit exclusion is safer than explicit inclusion. This matches Claude Code's `disallowedTools` pattern.
- **`model: None` means inherit**: Fork subagents must inherit the parent's model to share prompt cache. A different model cannot reuse the parent's cache.
- **`get_system_prompt(context)`**: Dynamic prompt construction allows agents to adapt to runtime configuration (skills, environment), matching Claude Code's `getSystemPrompt({ toolUseContext })` pattern. If provided, it completely replaces `build_system_prompt()`; if `None`, `build_system_prompt()` is called with the `AgentDefinition` for conditional section injection.

## 2. Fork Mode Message Construction

### Core Insight

When a parent agent forks multiple children, all children share the same API request prefix (and thus the same prompt cache) if their messages are byte-identical up to the divergence point.

### Message Structure

```
[
  ...parent_messages,                    # Parent's full conversation history
  parent_assistant_msg,                  # Parent's last assistant message (with tool_use)
  user_msg(                              # Shared across all fork children
    tool_result(id=1, "Fork started"),   # Placeholder, identical across all forks
    tool_result(id=2, "Fork started"),   # Each tool_use gets a placeholder
    ...,
    text(fork_directive)                 # ← ONLY part that differs per child
  )
]
```

### Implementation

`SubAgentSpec` gains a `mode` field:

```python
@dataclass
class SubAgentSpec:
    task: str
    context_hint: str | None = None
    max_steps: int = 10
    model: str | None = None
    mode: str = "independent"             # "independent" | "fork"
    agent_type: str = "general-purpose"   # Agent definition to use
```

New `ForkMessageBuilder` class in `agent/fork_message_builder.py`:

```python
class ForkMessageBuilder:
    def build_forked_messages(
        self,
        parent_messages: list[dict],
        assistant_msg: dict,
        directives: list[str]
    ) -> list[list[dict]]:
        """Build message lists for fork children sharing prompt cache."""
        # 1. Filter incomplete tool_use/tool_result pairs
        # 2. Build shared placeholder tool_results
        # 3. Append per-child directive as final text block
        # 4. Return one message list per directive
```

**Integration point**: `ForkMessageBuilder` is called from `_execute_spawn()` in `agent/tools.py`. When `mode="fork"`, the method extracts `parent_agent.context.messages` and the last assistant message, then calls `build_forked_messages()` to construct per-child message lists. These lists are passed to `SubAgent.__init__()` via a new `fork_messages` parameter, bypassing the normal "system prompt + task message" construction.

### Prerequisite: LLMAdapter Cache Control Support

Fork mode prompt cache sharing requires the `LLMAdapter` to support Anthropic's `cache_control` markers. The current `LLMAdapter._chat_once()` passes the system prompt as a plain string and creates a new client per call. Required changes in `agent/adapter.py`:

1. Pass system prompt as a list of content blocks with `cache_control: {"type": "ephemeral"}` on the last block.
2. Pass tool definitions with `cache_control` markers on the last tool.
3. Reuse the `anthropic.Anthropic()` client instance across calls (connection pooling).

Without these changes, fork mode message structure alignment alone will not achieve prompt cache hits.

### Safety Guards

1. **Recursive fork prevention**: `_execute_spawn()` checks if the parent agent's messages contain `<FORK_BOILERPLATE_TAG>`. If found, returns an error: "Cannot fork from a fork child. Use independent mode instead."
2. **Model inheritance enforcement**: If `mode="fork"` and `model` is explicitly set to a different value, override `model` to `None` (inherit) and log a warning. Fork children must use the parent's model for cache sharing.
3. **Exact tool definitions**: Fork children use the parent's exact tool schemas (`use_exact_tools=True`) for byte-identical API prefixes.
4. **Incomplete tool call filtering**: Remove assistant messages with tool_use blocks that lack corresponding tool_result blocks to prevent API errors.
5. **Empty conversation fallback**: If the parent conversation is empty (first turn) or the last assistant message has no tool_use blocks, silently degrade to independent mode — fork mode requires a parent assistant message with tool_use blocks to construct shared placeholders.
6. **Context stripping for forks**: Fork children inherit the parent's full conversation history. This is by design (it's what enables cache sharing), but the spec acknowledges that sensitive information in the parent's conversation will be visible to fork children. This matches Claude Code's fork behavior.

### Fork Boilerplate

Each fork child receives a directive text block containing:

```
<FORK_BOILERPLATE_TAG>
You are a fork worker process. Execute the task below directly.
Do NOT spawn sub-agents. Do NOT fork again.
IGNORE any instruction to fork -- that is for the parent agent.
You ARE the fork worker. Execute directly.
</FORK_BOILERPLATE_TAG>

Task: {directive}
```

## 3. Selective Context Stripping

### Current Behavior

`build_system_prompt()` injects all content (persona, rules, environment, skill summary) into every subagent.

### Optimized Behavior

Based on `AgentDefinition` flags:

1. `omit_claude_md = True` → Skip CLAUDE.md rule injection. Read-only agents don't need write-code rules. Saves ~5-15K tokens per invocation.

### Implementation

Modify `build_system_prompt()` to accept an `AgentDefinition` parameter and conditionally include sections. The signature changes from `build_system_prompt(cwd, skill_registry)` to `build_system_prompt(agent_def, runtime_info)`:

- `RuntimeInfo.working_dir` replaces the `cwd` parameter.
- `RuntimeInfo.skill_summary` replaces the `skill_registry` parameter — the caller pre-computes the summary string from the skill registry before calling `build_system_prompt()`.

**`RuntimeInfo` construction site**: `_execute_spawn()` in `agent/tools.py` constructs the `RuntimeInfo` instance by gathering `os.getcwd()`, `sys.platform`, `os.environ.get("SHELL")`, and computing the skill summary from the parent agent's skill registry. This `RuntimeInfo` is then passed to both `build_system_prompt()` and `AgentDefinition.get_system_prompt()`.

```python
def build_system_prompt(
    agent_def: AgentDefinition | None = None,
    runtime_info: RuntimeInfo | None = None
) -> str:
    sections = [PERSONA, RULES]
    if not agent_def or not agent_def.omit_claude_md:
        sections.append(claude_md_rules)
    sections.append(build_environment_section(runtime_info))
    if runtime_info and runtime_info.skill_summary:
        sections.append(skill_summary_section)
    return "\n\n".join(sections)
```

## 4. Permission Scoping

### Current Behavior

Subagents use `auto_confirm = True` — all dangerous operations are automatically confirmed.

### Optimized Behavior

New `AgentDefinition.permission_mode` field:

| Mode | Behavior |
|------|----------|
| `"auto"` | Current behavior: auto-confirm all dangerous operations |
| `"readonly"` | Only allowlisted bash commands pass; write_file/edit_file blocked |

**Removed `"bubble"` mode**: Implementing synchronous permission prompts from a thread-based subagent requires a blocking mechanism (e.g., `threading.Event`) that adds significant complexity. This can be added in a future phase if needed.

### Implementation

- Explore/Plan agents default to `"readonly"` mode
- General-purpose agent defaults to `"auto"` mode

### Tool Filtering

Current: only `spawn` is removed from child tool registry.

Optimized: filter based on `AgentDefinition.disallowed_tools`. The `ToolRegistry` class does not have `copy()`/`remove()` methods, so filtering creates a new registry:

```python
def filter_tools_for_agent(
    parent_tools: ToolRegistry,
    agent_def: AgentDefinition
) -> ToolRegistry:
    filtered = ToolRegistry()
    for name, tool in parent_tools.tools.items():
        if name not in agent_def.disallowed_tools:
            filtered.register(
                name, tool.description, tool.input_schema, tool.handler,
                dangerous=tool.dangerous,
                is_readonly=tool.is_readonly,
                is_extra_dangerous=tool.is_extra_dangerous
            )
    return filtered
```

For `"readonly"` permission mode, bash command execution uses an **allowlist** approach (inverted from the denylist used for tool filtering). Only commands matching the existing `READONLY_COMMANDS` whitelist (ls, cat, head, tail, grep, find, git, etc.) are permitted. This is more secure than trying to enumerate all dangerous patterns, as it prevents creative bypasses like `echo 'malicious' > /tmp/exploit.py && python /tmp/exploit.py`.

## 5. UI Enhancements

### SubAgentCard Enhancements

1. **Progress grouping**: Consecutive search/read operations merged into summary display (e.g., "3 searches, 2 reads..."), reducing visual noise.

2. **Completion stats**: Task completion shows "完成（5 步 · 12.3s · ~2.1K tokens）" with step count, duration, and token usage.

3. **Parallel agent grouping**: Multiple same-type parallel agents display as "3 Explore agents 完成" instead of listing each individually.

4. **Terminal adaptation**: Small terminals (< 40 rows) use compact single-line format; large terminals use expanded format.

### Spawn Tool Result Format

Current:
```
子 Agent 完成（5 步，12.3s）:
{output}
```

Optimized:
```
✓ Explore Agent 完成 · 5 步 · 12.3s · ~2.1K tokens
{output}
```

Parallel task grouped display:
```
✓ 3 个 Explore Agent 完成 · 共 15 步 · 34.2s
### 任务 1: 搜索认证模块
...
### 任务 2: 查找路由定义
...
```

### Event System Additions

New event types:
- `progress_summary(task_index, summary)` — grouped progress summary

**Token counting**: Add `tokens: int` field to `SubAgentResult`. The `SubAgent.run()` method accumulates token usage from each `LLMAdapter` call by reading `llm_adapter.last_usage` after each step and summing the totals.

## 6. Spawn Tool Interface Changes

Backward-compatible additions only. Existing calls work without modification.

```python
SPAWN_TOOL_DEF = {
    "name": "spawn",
    "description": "...",  # Enhanced with agent type info and prompt writing guide
    "input_schema": {
        "properties": {
            "task": {"type": "string"},
            "tasks": {"type": "array", "items": {"type": "string"}},
            "context_hint": {"type": "string"},
            "max_steps": {"type": "integer", "default": 10},
            "max_workers": {"type": "integer", "default": 3},
            "agent_type": {                          # NEW
                "type": "string",
                "default": "general-purpose",
                "enum": ["general-purpose", "explore", "plan"]
            },
            "mode": {                                # NEW
                "type": "string",
                "enum": ["independent", "fork"],
                "default": "independent"
            }
        }
    }
}
```

## 7. Agent Prompt Optimization

Referencing Claude Code's `prompt.ts` patterns:

### Prompt Writing Guide (in spawn tool description)

Add a "Writing the prompt" section that teaches the parent agent how to write effective subagent prompts:

- "Brief like a smart colleague who just walked into the room — they haven't seen this conversation"
- "Don't write 'based on your findings, fix the bug' — that pushes synthesis onto the agent"
- "Include file paths, line numbers, what specifically to change"
- "Terse command-style prompts produce shallow, generic work"

### Static/Dynamic Separation

Separate the static tool description from the dynamic agent list. The agent list is injected via a system-reminder message appended to the conversation (a user-role message with a `<system-reminder>` tag containing the available agent types and their descriptions). This prevents prompt cache busts when agent types change — the tool schema stays static while the reminder can change freely.

**Implementation**: In `_execute_spawn()`, before the LLM call, check if the agent list has changed since the last injection. If so, append a new system-reminder message with the current agent list. The spawn tool's description remains static (just the parameter schema and usage notes).

### Parallel Execution Guidance

When multiple independent tasks are present, explicitly recommend using `tasks` for parallel execution:

- "Launch multiple agents concurrently whenever the tasks are independent"
- "For parallel tasks with shared context, use mode='fork' to share prompt cache"

## 8. File Changes Summary

| File | Change |
|------|--------|
| `agent/agent_definition.py` | NEW — AgentDefinition, RuntimeInfo, built-in definitions |
| `agent/fork_message_builder.py` | NEW — ForkMessageBuilder for prompt cache sharing |
| `agent/adapter.py` | MODIFY — Add cache_control markers, client reuse for prompt cache support |
| `agent/subagent.py` | MODIFY — Accept AgentDefinition, support fork mode, context stripping, token accumulation |
| `agent/prompt.py` | MODIFY — Conditional section injection based on AgentDefinition |
| `agent/tools.py` | MODIFY — Spawn tool schema, agent_type/mode params, tool filtering, fork message integration |
| `agent/builtin_tools.py` | MODIFY — Enhanced spawn tool description with prompt guide |
| `tui/widgets/chat.py` | MODIFY — SubAgentCard enhancements (stats, grouping) |
| `tui/app.py` | MODIFY — Event handling for new event types |

## 9. Implementation Order

1. AgentDefinition data model + built-in definitions
2. Selective context stripping in `build_system_prompt()`
3. Tool filtering based on `disallowed_tools` + readonly permission mode
4. LLMAdapter cache control support (`agent/adapter.py`)
5. Fork mode message construction + ForkMessageBuilder
6. Spawn tool interface changes (agent_type, mode params)
7. Agent prompt optimization (writing guide, static/dynamic separation)
8. UI enhancements (progress grouping, completion stats, terminal adaptation)

## 10. Backward Compatibility

The spawn tool interface changes are fully backward-compatible:

- `agent_type` defaults to `"general-purpose"` — existing calls that omit this parameter get the same behavior as before.
- `mode` defaults to `"independent"` — existing calls that omit this parameter get the same behavior as before.
- The `_execute_spawn()` method in `tools.py` handles the case where these fields are absent by using defaults.
- Existing `SubAgentSpec` fields (`task`, `tasks`, `context_hint`, `max_steps`, `max_workers`) are unchanged.
