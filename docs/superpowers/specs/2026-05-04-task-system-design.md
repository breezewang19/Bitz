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

**Metadata conventions**:
- `metadata._internal`: Reserved for framework use; tasks with this key are hidden from TaskList tool output but remain in persistence (needed for dependency cleanup)
- Null values in metadata updates delete the corresponding key (matching Claude Code behavior)

## 2. Persistence Layer

**Storage location**: `~/.bitz/tasks/<project-slug>/`
- Per-task JSON files: `1.json`, `2.json`, ...
- High water mark file: `.highwatermark` (prevents ID reuse after deletion)
- Project slug derived from working directory (same method as session persistence)

### Core Functions (`agent/tasks.py`)

#### `create_task(project_slug, subject, description, active_form=None, metadata=None) -> Task`
- Scan `*.json` filenames (not contents) + read `.highwatermark` to determine next ID
- Write `<id>.json` with status `pending`, empty `blocks`/`blockedBy`
- Update `.highwatermark`
- Return the created Task

#### `update_task(project_slug, task_id, **updates) -> Task | None`
- Read existing task, return None if not found
- Apply updates (only changed fields)
- For `status="deleted"`: delegate to `delete_task()`
- For `add_blocks`: call `block_task(project_slug, task_id, block_id)` for each (task_id blocks block_id)
- For `add_blocked_by`: call `block_task(project_slug, blocker_id, task_id)` for each (blocker_id blocks task_id)
- Write updated task to JSON file
- Return the updated Task

#### `delete_task(project_slug, task_id) -> bool`
- Update `.highwatermark` to max(current_highwatermark, task_id_numeric)
- Delete the JSON file
- Clean up dependency references in all other tasks (remove task_id from their `blocks` and `blockedBy`)
- Return True if deleted, False if not found

#### `list_tasks(project_slug) -> list[Task]`
- Read all `*.json` files from the task directory
- Parse each with `get_task()`, skip None results
- Return all tasks (including `_internal` — filtering is a tool-layer concern)

#### `get_task(project_slug, task_id) -> Task | None`
- Read `<task_id>.json`
- Parse and return Task, or None if file doesn't exist or is corrupt

#### `block_task(project_slug, blocker_id, blocked_id) -> bool`
- Creates bidirectional dependency link (same as Claude Code's `blockTask`)
- `blocker_id.blocks` gains `blocked_id`; `blocked_id.blockedBy` gains `blocker_id`
- Detect circular dependencies via `has_cycle()` check before creating the link
- If circular: return False
- Write both tasks
- Return True

#### `has_cycle(all_tasks, start_id, target_id) -> bool`
- DFS from `start_id` following `blocks` edges, check if `target_id` is reachable
- Used by `block_task()` to prevent circular dependencies

#### `is_blocked(task, all_tasks) -> bool`
- Check if any task in `task.blockedBy` has status != `completed`
- Return True if any unresolved blocker exists
- Used by TaskList tool to show blocked status

#### `get_project_slug() -> str`
- Returns `sanitize_path(os.getcwd())` using `sanitize_path` from `agent/session.py`
- Ensures consistent slug generation with session persistence

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
- Return `"Updated task #<id> <changed_fields>"`

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

**Behavior**: Return full task details formatted as:
```
Task #<id>: <subject>
Status: <status>
Description: <description>
Blocked by: #<id>, #<id>
Blocks: #<id>
```

## 4. TUI Integration

### TaskListWidget (`tui/widgets/task_list.py`)

A Textual widget that displays the current task list, modeled after Claude Code's `TaskListV2.tsx`.

**Display format**:
```
Tasks (2/5)
─────────────
◉ Fixing auth bug...     [in_progress]
○ Write tests            [blocked by #1]
✓ Setup project          [completed]
```

When a task is `in_progress` and has an `activeForm`, the TUI shows the `activeForm` text instead of `subject` (matching Claude Code's spinner behavior).

**Status icons**:
- `◉` (in_progress, colored)
- `○` (pending, dim)
- `✓` (completed, green)

**Priority ordering** (same as Claude Code):
1. Recently completed (within 30s) > in_progress > pending > older completed

**Auto-hide**: Collapse 5 seconds after all tasks complete. Tasks remain persisted on disk (unlike Claude Code which auto-deletes completed tasks — Bitz preserves them for review).

**Max display**: 10 items.

**Refresh mechanism**:
- `set_interval(2, refresh)` for periodic polling
- Direct `refresh()` call after task tool execution for immediate update

### Integration Points

1. **BitzApp**: Add TaskListWidget in `BitzApp.compose()` alongside `ChatLog`, as a collapsible panel above the chat area
2. **StatusBar**: Show task count (e.g., "Tasks: 2/5")
3. **Tool execution callback**: After task tools execute, call `task_list_widget.refresh()` via `BitzApp._install_tool_logger()`

## 5. Error Handling

| Scenario | Handling |
|---|---|
| Task directory doesn't exist | Auto-create (same as session persistence) |
| Task JSON corrupt | Skip with warning, don't crash |
| Task ID not found | Return error message |
| Circular dependency | `block_task()` detects via DFS and rejects |
| Invalid status transition | Allow any transition (same as Claude Code) |
| `.highwatermark` missing | Rebuild from existing files |

## 6. Tool Prompts

Each task tool needs a description/prompt for the LLM to understand when and how to use it. These are modeled after Claude Code's `prompt.ts` files but adapted for Bitz's single-agent context.

### TaskCreate prompt (key points)
- Use proactively when starting a non-trivial implementation task (3+ steps)
- Create tasks with clear, specific subjects in imperative form
- Use `activeForm` for in-progress spinner text
- Don't create tasks for trivial single-step actions

### TaskUpdate prompt (key points)
- Mark tasks `in_progress` before starting work, `completed` when done
- Use `deleted` status to remove tasks that are no longer relevant
- Set up `add_blocks`/`add_blocked_by` for task dependencies
- Never mark a task completed unless fully accomplished

### TaskList prompt (key points)
- Use to check what tasks are available or track overall progress
- Tasks with `blockedBy` cannot start until blockers complete

### TaskGet prompt (key points)
- Use when you need full task details before starting work
- Check `blockedBy` to understand what must complete first

## 7. Testing Strategy

- **Unit tests** (`tests/test_tasks.py`):
  - CRUD operations (create, read, update, delete)
  - Dependency management (block_task, has_cycle, is_blocked)
  - Circular dependency detection (A->B->C->A should be rejected)
  - Highwatermark behavior after deletion (deleted IDs never reused)
  - Metadata merge and null-deletion
  - Corrupt JSON handling
  - Missing directory auto-creation
  - `_internal` metadata filtering (in tool layer, not persistence)
- **Tool tests** (`tests/test_task_tools.py`):
  - Tool input validation (required fields, invalid status)
  - Tool execution in agent loop context
  - TaskCreate creates with correct defaults
  - TaskUpdate handles `deleted` status correctly
  - TaskList filters `_internal` tasks and unresolved blockers
  - TaskGet returns formatted output
- **TUI tests** (`tests/test_task_list_widget.py`):
  - Widget rendering with Textual `app.run_test()`
  - Status display and icon mapping
  - activeForm shown for in_progress tasks
  - Auto-hide after all tasks complete
  - Priority ordering
  - Use pytest fixtures for temporary task directories

## 8. File Changes Summary

| File | Action | Description |
|---|---|---|
| `agent/tasks.py` | **New** | Task data model + persistence layer |
| `agent/builtin_tools.py` | **Modify** | Add 4 task tool definitions |
| `tui/widgets/task_list.py` | **New** | TaskListWidget component |
| `tui/app.py` | **Modify** | Integrate TaskListWidget into BitzApp |
| `tests/test_tasks.py` | **New** | Unit tests for task persistence |
| `tests/test_task_tools.py` | **New** | Integration tests for task tools |
