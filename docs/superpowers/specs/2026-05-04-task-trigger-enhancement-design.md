# Task Trigger Enhancement Design

## Overview

Enhance Bitz's task system trigger mechanisms to match Claude Code's effectiveness. Three changes: enrich tool descriptions with detailed usage guidance, integrate task tool guidance into the system prompt, and add a task reminder mechanism that nudges the agent after prolonged disuse of task tools.

**Scope**: Single-agent scenario, no teammate/owner features.

## 1. Enrich Tool Descriptions

**File**: `agent/builtin_tools.py`

Replace the 4 task tools' `description` fields with detailed Chinese prompts (~300-500 chars each), modeled after Claude Code's `prompt.ts` files but adapted for Bitz's single-agent context.

### task_create

```
为当前编码会话创建结构化任务列表，帮助跟踪进度、组织复杂任务。

## 何时使用
- 复杂多步骤任务（3 步以上）
- 需要仔细规划或多步操作的任务
- 用户给出多个任务（编号或逗号分隔）
- 收到新指令后，立即将需求捕获为任务
- 开始工作时，先标记为 in_progress

## 何时不使用
- 单一简单任务
- 任务可在 3 步以内轻松完成
- 纯对话或信息查询

## 字段
- subject: 简短的祈使句标题（如"修复登录流程的认证 bug"）
- description: 详细需求说明
- activeForm: 进行中时显示在 spinner 的文本（如"修复认证 bug"），省略则显示 subject

所有任务创建时状态为 pending。

## 提示
- 创建后用 task_update 设置依赖关系（blocks/blockedBy）
- 先用 task_list 检查，避免创建重复任务
```

### task_update

```
更新任务列表中的任务。

## 何时使用
- 开始工作时标记为 in_progress
- 完成工作时标记为 completed
- 任务不再需要时标记为 deleted
- 需求变化时更新描述
- 设置任务间依赖关系

## 完成条件
仅在以下情况标记 completed：
- 测试通过
- 实现完整
- 无未解决错误

如果遇到阻塞或无法完成，保持 in_progress 并创建新任务描述阻塞原因。

## 可更新字段
- status: pending → in_progress → completed；deleted 永久删除
- subject/description/activeForm: 更新任务内容
- metadata: 合并元数据（设为 null 删除键）
- add_blocks: 标记此任务完成后才能开始的任务
- add_blocked_by: 标记必须先完成的任务

## 示例
开始工作：{"task_id": "1", "status": "in_progress"}
完成工作：{"task_id": "1", "status": "completed"}
删除任务：{"task_id": "1", "status": "deleted"}
设置依赖：{"task_id": "2", "add_blocked_by": ["1"]}
```

### task_list

```
列出任务列表中的所有任务。

## 何时使用
- 查看可用任务（pending 且未被阻塞）
- 检查项目整体进度
- 寻找被阻塞的任务
- 完成一个任务后，查看下一个可用任务
- 多个任务可用时，优先按 ID 顺序处理（低 ID 先做）

## 输出
每条任务显示：#id [状态] 标题，如有未解决的阻塞则显示 [blocked by #id]
```

### task_get

```
按 ID 获取任务详情。

## 何时使用
- 开始工作前获取完整描述和上下文
- 理解任务依赖（它阻塞谁、谁阻塞它）
- 获取完整需求后再开始工作

## 输出
- subject: 任务标题
- description: 详细需求和上下文
- status: pending/in_progress/completed
- blocks: 等待此任务完成的任务
- blockedBy: 必须先完成的任务

## 提示
- 获取任务后，先检查 blockedBy 是否为空再开始工作
- 用 task_list 查看所有任务概览
```

## 2. System Prompt Integration

**File**: `agent/prompt.py`

Add one bullet to the `## 工具使用` section in `RULES`:

```
- 用 task_create 拆分复杂任务，用 task_update 跟踪进度（开始时标记 in_progress，完成时标记 completed），不要批量标记完成
```

This mirrors Claude Code's "Break down and manage your work with the task_create tool..." but is more concise and fits the existing Chinese rule style.

## 3. Task Reminder Mechanism

### New File: `agent/task_reminder.py`

Pure function module with no class dependencies:

```python
TASK_TOOL_NAMES = {"task_create", "task_update", "task_list", "task_get"}
REMINDER_THRESHOLD = 10  # steps since last task tool use
REMINDER_COOLDOWN = 10   # steps between reminders

def should_remind(
    step_count: int,
    last_task_tool_step: int | None,
    last_reminder_step: int | None,
    task_summary: str | None,
) -> str | None:
    """Check whether a task reminder should be injected.

    Args:
        step_count: Current agent step count.
        last_task_tool_step: Step count when a task tool was last used, or None.
        last_reminder_step: Step count when a reminder was last injected, or None.
        task_summary: Formatted task list string (e.g. "#1 [pending] Fix bug"),
                      or None if no active tasks exist.

    Returns the reminder text, or None if no reminder is needed.
    """
```

Note: All four task tools count as task engagement. Using `task_list`/`task_get` shows the agent is actively managing its task state, which should reset the reminder counter.

### Trigger Conditions

All must be true:
1. `last_task_tool_step is None` or `step_count - last_task_tool_step >= REMINDER_THRESHOLD`
2. `last_reminder_step is None` or `step_count - last_reminder_step >= REMINDER_COOLDOWN`

The reminder fires regardless of whether active tasks exist. The presence/absence of tasks only affects the reminder content, not whether it triggers.

### Reminder Content

The `task_summary` parameter determines the variant:

When `task_summary is None` (no active tasks):
```
你最近没有使用任务工具。如果正在处理多步骤任务，考虑用 task_create 创建新任务，用 task_update 更新状态（开始时 in_progress，完成时 completed）。不要向用户提及此提醒。
```

When `task_summary` is a formatted string (active tasks exist):
```
你最近没有使用任务工具。如果正在处理多步骤任务，考虑用 task_create 创建新任务，用 task_update 更新状态（开始时 in_progress，完成时 completed）。不要向用户提及此提醒。

当前任务：
#1 [pending] 修复认证 bug
#2 [in_progress] 编写测试
```

### Data Source for `task_summary`

The caller in `loop.py` obtains `task_summary` by calling a helper function in `task_reminder.py`:

```python
def get_task_summary(project_slug: str, base_dir: str | None = None) -> str | None:
    """Return a formatted task list string for active tasks, or None.

    Filtering mirrors task_list_handler in builtin_tools.py:
    exclude _internal tasks, show only pending/in_progress.
    """
    from agent.tasks import list_tasks
    all_tasks = list_tasks(project_slug, base_dir=base_dir)
    active = [t for t in all_tasks
              if t.status.value in ("pending", "in_progress")
              and not t.metadata.get("_internal")]
    if not active:
        return None
    lines = [f"#{t.id} [{t.status.value}] {t.subject}" for t in active]
    return "\n".join(lines)
```

The `Agent` class obtains `project_slug` via `get_project_slug()` from `agent/tasks.py` (same function used by `builtin_tools.py`).

### Integration in `agent/loop.py`

Add to the `Agent` class:
- `_last_task_tool_step: int | None = None`
- `_last_reminder_step: int | None = None`

After the context is updated with the current turn's results (after `context.add_assistant_message()` and `context.add_tool_results()` calls, at the end of the tool_use branch, before the `continue`):

1. Check if any executed tool name is in `TASK_TOOL_NAMES`; if so, update `_last_task_tool_step = self._step_count`
2. Call `should_remind()` with current state and `task_summary` from `get_task_summary()`
3. If reminder returned, inject via `context.add_system_reminder(text)` and update `_last_reminder_step = self._step_count`

This injection position ensures the reminder appears after the current turn's tool results, maintaining correct message ordering for the Anthropic API.

**Step count semantics**: `_step_count` in `loop.py` only increments in the `tool_use` branch. The reminder threshold (10) therefore means "10 tool-use turns since last task tool use." End-turn responses do not count as steps. This is intentional: reminders are designed for tool-heavy workflows where the agent is actively working but neglecting task tracking. Pure conversation turns don't need task reminders.

**`confirm_pending` path**: When tools are confirmed via `Agent.confirm_pending()`, the same task tool check and reminder logic should apply. Add the check after the confirmed tool results are written to context in `confirm_pending()`, mirroring the logic in the `tool_use` branch.

### Context Support: `agent/context.py`

Add method:
```python
def add_system_reminder(self, text: str) -> None:
    """Add a system reminder as a user message.

    The reminder is stored with a _meta key for internal tracking.
    get_messages() strips _meta before returning messages to the API.
    """
    self.messages.append({
        "role": "user",
        "content": text,
        "_meta": True,
    })
    self._trim()
    # Intentionally skip _persist(): reminders are ephemeral nudges,
    # not part of the permanent conversation record.
```

**API safety**: `get_messages()` must strip the `_meta` key before returning messages to the Anthropic API. Modify `get_messages()` to remove any non-standard keys from message dicts:

```python
def get_messages(self) -> list[dict]:
    """Return messages suitable for the Anthropic API."""
    result = []
    for msg in self.messages:
        clean = {k: v for k, v in msg.items() if k in ("role", "content")}
        result.append(clean)
    return result
```

**Consecutive user messages**: The reminder is injected after `add_tool_results()`, which creates a `user` role message. This results in consecutive `user` messages (tool_result then reminder). The Anthropic API accepts this pattern — multiple `user` messages are merged automatically. No special handling needed.

**Persistence decision**: `_persist()` is intentionally skipped for reminder messages. They are ephemeral nudges that should not survive session restore. If a session is restored, the agent will naturally re-engage with task tools or trigger a fresh reminder after the threshold is met again.

**Trimming behavior**: `_meta` messages are subject to normal `_trim()` behavior — they are ephemeral nudges, not permanent context. They will be trimmed like any other message when they fall outside the `keep_last_n` window. `_meta` messages must never appear between a `tool_use` and its corresponding `tool_result` (guaranteed by the injection position after tool results are written).

## 4. Testing Strategy

### `tests/test_task_reminder.py` (new)

- `should_remind` returns None when threshold not met
- `should_remind` returns None when cooldown not met
- `should_remind` returns reminder when both thresholds met
- `should_remind` includes task list in output when task_summary provided
- `should_remind` returns plain nudge when task_summary is None
- Step counting resets after task tool use
- Cooldown prevents rapid re-reminders
- `get_task_summary` returns None when no active tasks
- `get_task_summary` returns formatted string when active tasks exist
- `get_task_summary` filters out _internal tasks

### `tests/test_context.py` (modify)

- `add_system_reminder` appends user message with _meta flag
- `get_messages` strips _meta key from messages
- `get_messages` preserves standard role/content fields

### `tests/test_task_tools.py` (modify)

- Verify task_create description contains "何时使用" section
- Verify task_update description contains "完成条件" section
- Verify task_list description contains "输出" section
- Verify task_get description contains "提示" section

### `tests/test_prompt.py` (**New**)

- Verify RULES contains task_create/task_update guidance

Note: Tool descriptions are in Chinese while `input_schema` field descriptions remain in English, consistent with the existing pattern in `builtin_tools.py` (all non-spawn tools use English for input_schema descriptions).

## 5. File Changes Summary

| File | Action | Description |
|---|---|---|
| `agent/builtin_tools.py` | Modify | Replace 4 task tool descriptions with detailed Chinese prompts |
| `agent/prompt.py` | Modify | Add task tool guidance bullet to RULES |
| `agent/task_reminder.py` | **New** | Pure function module for reminder logic |
| `agent/loop.py` | Modify | Add reminder check after step increment, track task tool usage |
| `agent/context.py` | Modify | Add `add_system_reminder()` method; `get_messages()` strips `_meta` key |
| `tests/test_task_reminder.py` | **New** | Unit tests for reminder logic |
| `tests/test_task_tools.py` | Modify | Add description content tests |
| `tests/test_context.py` | Modify | Tests for `add_system_reminder()` and `_meta` stripping |
| `tests/test_prompt.py` | **New** | Verify RULES contains task guidance |
