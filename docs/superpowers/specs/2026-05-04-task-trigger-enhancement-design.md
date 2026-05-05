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
TASK_TOOL_NAMES = {"task_create", "task_update"}
REMINDER_THRESHOLD = 10  # steps since last task tool use
REMINDER_COOLDOWN = 10   # steps between reminders

def should_remind(
    messages: list[dict],
    step_count: int,
    last_task_tool_step: int | None,
    last_reminder_step: int | None,
    has_active_tasks: bool,
) -> str | None:
    """Check whether a task reminder should be injected.

    Returns the reminder text, or None if no reminder is needed.
    """
```

### Trigger Conditions

All must be true:
1. `last_task_tool_step is None` or `step_count - last_task_tool_step >= REMINDER_THRESHOLD`
2. `last_reminder_step is None` or `step_count - last_reminder_step >= REMINDER_COOLDOWN`
3. `has_active_tasks` is True (there are pending or in_progress tasks)

### Reminder Content

Without active tasks:
```
你最近没有使用任务工具。如果正在处理多步骤任务，考虑用 task_create 创建新任务，用 task_update 更新状态（开始时 in_progress，完成时 completed）。不要向用户提及此提醒。
```

With active tasks:
```
你最近没有使用任务工具。如果正在处理多步骤任务，考虑用 task_create 创建新任务，用 task_update 更新状态（开始时 in_progress，完成时 completed）。不要向用户提及此提醒。

当前任务：
#1 [pending] 修复认证 bug
#2 [in_progress] 编写测试
```

### Integration in `agent/loop.py`

Add to the `Agent` class:
- `_last_task_tool_step: int | None = None`
- `_last_reminder_step: int | None = None`

After `self._step_count += 1` in the tool_use branch:
1. Check if any executed tool name is in `TASK_TOOL_NAMES`; if so, update `_last_task_tool_step`
2. Call `should_remind()` with current state
3. If reminder returned, inject via `context.add_system_reminder(text)` and update `_last_reminder_step`

### Context Support: `agent/context.py`

Add method:
```python
def add_system_reminder(self, text: str) -> None:
    """Add a meta user message for system reminders (task reminders, etc.)."""
    self.messages.append({
        "role": "user",
        "content": text,
        "_meta": True,
    })
```

The `_meta` flag distinguishes system reminders from real user messages. The `_trim()` method should preserve these like regular messages.

## 4. Testing Strategy

### `tests/test_task_reminder.py` (new)

- `should_remind` returns None when threshold not met
- `should_remind` returns None when cooldown not met
- `should_remind` returns reminder when both thresholds met and active tasks exist
- `should_remind` returns None when no active tasks
- `should_remind` includes task list in output when active tasks exist
- `should_remind` returns plain nudge when no active tasks
- Step counting resets after task tool use
- Cooldown prevents rapid re-reminders

### `tests/test_task_tools.py` (modify)

- Verify task_create description contains "何时使用" section
- Verify task_update description contains "完成条件" section
- Verify task_list description contains "输出" section
- Verify task_get description contains "提示" section

### `tests/test_prompt.py` (modify or new)

- Verify RULES contains task_create/task_update guidance

## 5. File Changes Summary

| File | Action | Description |
|---|---|---|
| `agent/builtin_tools.py` | Modify | Replace 4 task tool descriptions with detailed Chinese prompts |
| `agent/prompt.py` | Modify | Add task tool guidance bullet to RULES |
| `agent/task_reminder.py` | **New** | Pure function module for reminder logic |
| `agent/loop.py` | Modify | Add reminder check after step increment, track task tool usage |
| `agent/context.py` | Modify | Add `add_system_reminder()` method |
| `tests/test_task_reminder.py` | **New** | Unit tests for reminder logic |
| `tests/test_task_tools.py` | Modify | Add description content tests |
| `tests/test_prompt.py` | Modify or new | Verify RULES contains task guidance |
