# SubAgent Optimization Design

Optimize the Bitz Python subagent system by referencing Claude Code's TypeScript agent architecture. Goals: improve performance (prompt cache sharing), expand capabilities (role-based agent types), and enhance UX (progress grouping, completion stats).

Approach: incremental enhancement on the existing `SubAgent`/`SubAgentSpec` architecture, maintaining backward compatibility with the current `spawn` tool interface.

## 1. AgentDefinition Data Model

New file: `agent/agent_definition.py`

```python
@dataclass
class AgentContext:
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
    get_system_prompt: Callable[[AgentContext], str] | None  # Dynamic prompt builder
    omit_claude_md: bool = False                 # Skip CLAUDE.md rules injection
    omit_git_status: bool = False                # Skip git status injection
    max_steps: int = 10                          # Default max steps
    background: bool = False                     # Run asynchronously
    permission_mode: str = "auto"                # "auto" | "bubble" | "readonly"
```

### Built-in Agent Definitions

| Agent | disallowed_tools | model | omit_claude_md | omit_git_status | permission_mode |
|-------|-----------------|-------|----------------|-----------------|-----------------|
| general-purpose | [] | None (inherit) | False | False | auto |
| explore | [write_file, edit_file, spawn] | None (inherit) | True | True | readonly |
| plan | [write_file, edit_file, spawn] | None (inherit) | True | True | readonly |

### Design Decisions

- **Denylist over allowlist**: New tools are available by default; explicit exclusion is safer than explicit inclusion. This matches Claude Code's `disallowedTools` pattern.
- **`model: None` means inherit**: Fork subagents must inherit the parent's model to share prompt cache. A different model cannot reuse the parent's cache.
- **`get_system_prompt(context)`**: Dynamic prompt construction allows agents to adapt to runtime configuration (skills, environment), matching Claude Code's `getSystemPrompt({ toolUseContext })` pattern.

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

### Safety Guards

1. **Recursive fork prevention**: Detect fork boilerplate tag in messages; refuse to fork again if already a fork child.
2. **Model inheritance**: Fork children MUST use the parent's model (different models can't share cache).
3. **Exact tool definitions**: Fork children use the parent's exact tool schemas (`use_exact_tools=True`) for byte-identical API prefixes.
4. **Incomplete tool call filtering**: Remove assistant messages with tool_use blocks that lack corresponding tool_result blocks to prevent API errors.

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
2. `omit_git_status = True` → Skip git status injection. Read-only agents can run `git status` themselves if needed. Saves up to ~40KB of stale state.

### Implementation

Modify `build_system_prompt()` to accept an `AgentDefinition` parameter and conditionally include sections:

```python
def build_system_prompt(
    agent_def: AgentDefinition | None = None,
    context: AgentContext | None = None
) -> str:
    sections = [PERSONA, RULES]
    if not agent_def or not agent_def.omit_claude_md:
        sections.append(claude_md_rules)
    sections.append(build_environment_section(context))
    if not agent_def or not agent_def.omit_git_status:
        sections.append(git_status_section)
    if context and context.skill_summary:
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
| `"bubble"` | Dangerous operations reported to parent agent via event callback for user confirmation |
| `"readonly"` | All write operations blocked (write_file, edit_file, dangerous bash commands) |

### Implementation

- Explore/Plan agents default to `"readonly"` mode
- General-purpose agent defaults to `"auto"` mode
- `"bubble"` mode emits a `permission_request` event that the parent agent's TUI handles

### Tool Filtering

Current: only `spawn` is removed from child tool registry.

Optimized: filter based on `AgentDefinition.disallowed_tools` using denylist pattern:

```python
def filter_tools_for_agent(
    tools: ToolRegistry,
    agent_def: AgentDefinition
) -> ToolRegistry:
    filtered = tools.copy()
    for tool_name in agent_def.disallowed_tools:
        filtered.remove(tool_name)
    return filtered
```

For `"readonly"` permission mode, additionally block:
- `write_file`, `edit_file`
- Bash commands matching dangerous patterns (rm, pip install, etc.)

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
- `token_count(task_index, count)` — token usage tracking

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

Separate the static tool description from the dynamic agent list. The agent list is injected via a system-reminder attachment rather than embedded in the tool description. This prevents prompt cache busts when agent types change.

### Parallel Execution Guidance

When multiple independent tasks are present, explicitly recommend using `tasks` for parallel execution:

- "Launch multiple agents concurrently whenever the tasks are independent"
- "For parallel tasks with shared context, use mode='fork' to share prompt cache"

## 8. File Changes Summary

| File | Change |
|------|--------|
| `agent/agent_definition.py` | NEW — AgentDefinition, AgentContext, built-in definitions |
| `agent/fork_message_builder.py` | NEW — ForkMessageBuilder for prompt cache sharing |
| `agent/subagent.py` | MODIFY — Accept AgentDefinition, support fork mode, context stripping |
| `agent/prompt.py` | MODIFY — Conditional section injection based on AgentDefinition |
| `agent/tools.py` | MODIFY — Spawn tool schema, agent_type/mode params, tool filtering |
| `agent/builtin_tools.py` | MODIFY — Enhanced spawn tool description with prompt guide |
| `tui/widgets/chat.py` | MODIFY — SubAgentCard enhancements (stats, grouping) |
| `tui/app.py` | MODIFY — Event handling for new event types |

## 9. Implementation Order

1. AgentDefinition data model + built-in definitions
2. Selective context stripping in `build_system_prompt()`
3. Tool filtering based on `disallowed_tools` + permission scoping
4. Fork mode message construction
5. Spawn tool interface changes (agent_type, mode params)
6. Agent prompt optimization (writing guide, static/dynamic separation)
7. UI enhancements (progress grouping, completion stats, terminal adaptation)
