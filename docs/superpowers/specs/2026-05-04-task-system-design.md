# Task System Design for Bitz

## Overview

Add a persistent task list system to Bitz, modeled after Claude Code's V2 task system (`src/utils/tasks.ts`). The system provides TaskCreate/TaskUpdate/TaskList/Get tools for the agent to track work progress, manage dependencies, and display task status in the TUI.

**Scope**: V2 persistent task list only (no runtime background task system).
**Scenario**: Single agent (no multi-agent claiming or team notifications).

## Claude Code Reference Mapping

| Claude Code | Bitz | Notes |
|---|---|---|
| `src/utils/tasks.ts` | `agent/tasks.py` | Task data model + persistence |
| `src/tools/TaskCreateTool/` | `agent/builtin_tools.py` (task_create) | Tool definition |
| `src/tools/TaskUpdateTool/` | `agent/builtin_tools.py` (task_update) | Tool definition |
| `src/tools/TaskListTool/` | `agent/builtin_tools.py` (task_list) | Tool definition |
| `src/tools/TaskGetTool/` | `agent/builtin_tools.py` (task_get) | Tool definition |
| `src/components/TaskListV2.tsx` | `tui/widgets/task_list.py` | TUI component |
| `src/hooks/useTasksV2.ts` | Textual `set_interval` + refresh | Refresh mechanism |
| `claimTask()` | **Not included** | Single agent, no claiming |
| `getAgentStatuses()` | **Not included** | Single agent, no team |
| `proper-lockfile` | **Not included** | Single agent, no concurrent writes |
| `createSignal/notifyTasksUpdated` | Textual message system | Different mechanism |

## 1. Data Model

```python
class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

@dataclass
class Task:
    id: str                    # Auto-incremented numeric string "1", "2", "3"...
    subject: str               # Brief imperative-form title
    description: str           # Detailed requirements
    activeForm: str | None     # Present continuous form for spinner (e.g., "Running tests")
    status: TaskStatus         # pending | in_progress | completed
    blocks: list[str]          # Task IDs this task blocks
    blockedBy: list[str]       # Task IDs blocking this task
    metadata: dict[str, Any]   # Arbitrary metadata; null values delete keys
```

**Differences from Claude Code**: No `owner` field (single agent scenario).

**Status workflow**: `pending` -> `in_progress` -> `completed`. The `deleted` status is a special action in TaskUpdate, not a valid TaskStatus value.

## 2. Persistence Layer

**Storage location**: `~/.bitz/tasks/<project-slug>/`
- Per-task JSON files: `1.json`, `2.json`, ...
- High water mark file: `.highwatermark` (prevents ID reuse after deletion)
- Project slug derived from working directory (same method as session persistence)

### Core Functions (`agent/tasks.py`)

#### `create_task(project_slug, subject, description, active_form=None, metadata=None) -> Task`
- Read all `*.json` files + `.highwatermark` to determine next ID
- Write `<id>.json` with status `pending`, empty `blocks`/`blockedBy`
- Update `.highwatermark`
- Return the created Task

#### `update_task(project_slug, task_id, **updates) -> Task | None`
- Read existing task, return None if not found
- Apply updates (only changed fields)
- For `status="deleted"`: delegate to `delete_task()`
- For `add_blocks`: call `block_task()` for each
- For `add_blocked_by`: call `block_task()` in reverse for each
- Write updated task to JSON file
- Return the updated Task

#### `delete_task(project_slug, task_id) -> bool`
- Update `.highwatermark` if this task's ID is the highest
- Delete the JSON file
- Clean up dependency references in all other tasks (remove task_id from their `blocks` and `blockedBy`)
- Return True if deleted, False if not found

#### `list_tasks(project_slug) -> list[Task]`
- Read all `*.json` files from the task directory
- Parse each with `get_task()`, skip None results
- Filter out tasks with `metadata._internal`
- Return all tasks

#### `get_task(project_slug, task_id) -> Task | None`
- Read `<task_id>.json`
- Parse and return Task, or None if file doesn't exist or is corrupt

#### `block_task(project_slug, blocker_id, blocked_id) -> bool`
- Detect circular dependencies (DFS from blocked_id, check if blocker_id is reachable)
- If circular: return False
- Update blocker task: add `blocked_id` to `blocks`
- Update blocked task: add `blocker_id` to `blockedBy`
- Write both tasks
- Return True

#### `is_blocked(task, all_tasks) -> bool`
- Check if any task in `task.blockedBy` has status != `completed`
- Return True if any unresolved blocker exists

### ID Generation Logic

Consistent with Claude Code:
1. Scan all `*.json` filenames in the task directory
2. Read `.highwatermark` file
3. Take max of (max filename ID, highwatermark value) + 1
4. Write new `.highwatermark` value

### JSON Format

```json
{
  "id": "1",
  "subject": "Fix authentication bug",
  "description": "The login flow fails when...",
  "activeForm": "Fixing authentication bug",
  "status": "pending",
  "blocks": ["3"],
  "blockedBy": ["2"],
  "metadata": {}
}
```

## 3. Tool Layer

Four new tools registered in `agent/builtin_tools.py`, following the existing tool definition pattern (name, description, input_schema, handler).

### TaskCreate

**Input schema**:
```json
{
  "type": "object",
  "properties": {
    "subject": {"type": "string", "description": "Brief imperative-form title"},
    "description": {"type": "string", "description": "Detailed requirements"},
    "active_form": {"type": "string", "description": "Present continuous form for spinner"},
    "metadata": {"type": "object", "description": "Arbitrary metadata"}
  },
  "required": ["subject", "description"]
}
```

**Behavior**: Create task with `status: "pending"`, return `"Task #<id> created successfully: <subject>"`

### TaskUpdate

**Input schema**:
```json
{
  "type": "object",
  "properties": {
    "task_id": {"type": "string", "description": "Task ID to update"},
    "subject": {"type": "string"},
    "description": {"type": "string"},
    "active_form": {"type": "string"},
    "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "deleted"]},
    "metadata": {"type": "object"},
    "add_blocks": {"type": "array", "items": {"type": "string"}, "description": "Task IDs this task blocks"},
    "add_blocked_by": {"type": "array", "items": {"type": "string"}, "description": "Task IDs that must complete before this one"}
  },
  "required": ["task_id"]
}
```

**Behavior**:
- `status: "deleted"` -> call `delete_task()`, return early
- `add_blocks` -> call `block_task(project_slug, task_id, block_id)` for each
- `add_blocked_by` -> call `block_task(project_slug, blocker_id, task_id)` for each
- Return `"Updated task #<id>: <changed_fields>"`

### TaskList

**Input schema**: `{}` (no parameters)

**Behavior**:
- List all tasks (excluding `_internal`)
- Filter `blockedBy` to show only unresolved blockers
- Format: `#<id> [<status>] <subject> [blocked by #<id>, #<id>]`

### TaskGet

**Input schema**:
```json
{
  "type": "object",
  "properties": {
    "task_id": {"type": "string", "description": "Task ID to retrieve"}
  },
  "required": ["task_id"]
}
```

**Behavior**: Return full task details (subject, description, status, blocks, blockedBy)

## 4. TUI Integration

### TaskListWidget (`tui/widgets/task_list.py`)

A Textual widget that displays the current task list, modeled after Claude Code's `TaskListV2.tsx`.

**Display format**:
```
Tasks (2/5)
─────────────
◉ Fix auth bug          [in_progress]
○ Write tests           [blocked by #1]
✓ Setup project         [completed]
```

**Status icons**:
- `◉` (in_progress, colored)
- `○` (pending, dim)
- `✓` (completed, green)

**Priority ordering** (same as Claude Code):
1. Recently completed (within 30s) > in_progress > pending > older completed

**Auto-hide**: Collapse 5 seconds after all tasks complete.

**Max display**: 10 items.

**Refresh mechanism**:
- `set_interval(2, refresh)` for periodic polling
- Direct `refresh()` call after task tool execution for immediate update

### Integration Points

1. **ChatScreen**: Add TaskListWidget as a collapsible panel above or below the chat area
2. **StatusBar**: Show task count (e.g., "Tasks: 2/5")
3. **Tool execution callback**: After task tools execute, call `task_list_widget.refresh()`

## 5. Error Handling

| Scenario | Handling |
|---|---|
| Task directory doesn't exist | Auto-create (same as session persistence) |
| Task JSON corrupt | Skip with warning, don't crash |
| Task ID not found | Return error message |
| Circular dependency | `block_task()` detects via DFS and rejects |
| Invalid status transition | Allow any transition (same as Claude Code) |
| `.highwatermark` missing | Rebuild from existing files |

## 6. Testing Strategy

- **Unit tests** (`tests/test_tasks.py`): CRUD operations, dependency management, circular dependency detection, edge cases
- **Tool tests** (`tests/test_task_tools.py`): Tool input validation, tool execution in agent loop context
- **TUI tests** (`tests/test_task_list_widget.py`): Widget rendering, status display, auto-hide behavior

## 7. File Changes Summary

| File | Action | Description |
|---|---|---|
| `agent/tasks.py` | **New** | Task data model + persistence layer |
| `agent/builtin_tools.py` | **Modify** | Add 4 task tool definitions |
| `tui/widgets/task_list.py` | **New** | TaskListWidget component |
| `tui/app.py` | **Modify** | Integrate TaskListWidget into ChatScreen |
| `tests/test_tasks.py` | **New** | Unit tests for task persistence |
| `tests/test_task_tools.py` | **New** | Integration tests for task tools |
