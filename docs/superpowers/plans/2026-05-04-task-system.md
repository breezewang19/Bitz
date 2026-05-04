# Task System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent task list system (TaskCreate/Update/List/Get tools + TUI widget) to Bitz, modeled after Claude Code's V2 task system.

**Architecture:** New `agent/tasks.py` module handles data model and file-based persistence. Four task tools registered in `agent/builtin_tools.py` following the existing tool pattern. New `tui/widgets/task_list.py` Textual widget displays tasks in the TUI, integrated into `BitzApp`.

**Tech Stack:** Python 3.11+, dataclasses, pathlib, Textual 3.x, pytest

**Spec:** `docs/superpowers/specs/2026-05-04-task-system-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `agent/tasks.py` | Create | Task data model + persistence CRUD + dependency helpers |
| `agent/builtin_tools.py` | Modify | Add 4 task tool registrations in `create_tools()` |
| `tui/widgets/task_list.py` | Create | TaskListWidget Textual component |
| `tui/app.py` | Modify | Mount TaskListWidget, wire refresh in `_install_tool_logger()` |
| `tui/widgets/status.py` | Modify | Add task count display |
| `tests/test_tasks.py` | Create | Unit tests for task persistence |
| `tests/test_task_tools.py` | Create | Integration tests for task tools |
| `tests/test_task_list_widget.py` | Create | TUI widget tests |

---

### Task 1: Task Data Model and Persistence — Core CRUD

**Files:**
- Create: `agent/tasks.py`
- Test: `tests/test_tasks.py`

- [ ] **Step 1: Write failing tests for Task data model and basic CRUD**

```python
# tests/test_tasks.py
import json
import pytest
from pathlib import Path
from agent.tasks import Task, TaskStatus, create_task, get_task, list_tasks, delete_task, update_task, get_project_slug


@pytest.fixture
def task_dir(tmp_path, monkeypatch):
    """Create a temporary task directory and patch get_project_slug."""
    slug = "test-project"
    tdir = tmp_path / "bitz-tasks" / slug
    tdir.mkdir(parents=True)
    monkeypatch.setattr("agent.tasks._get_tasks_dir", lambda _slug: tdir)
    return tdir


class TestTaskModel:
    def test_task_status_values(self):
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.IN_PROGRESS == "in_progress"
        assert TaskStatus.COMPLETED == "completed"

    def test_task_creation_defaults(self):
        t = Task(id="1", subject="Test", description="A test task")
        assert t.status == TaskStatus.PENDING
        assert t.blocks == []
        assert t.blockedBy == []
        assert t.activeForm is None
        assert t.metadata == {}


class TestCreateTask:
    def test_creates_task_with_auto_increment_id(self, task_dir):
        t1 = create_task("test-project", "First", "Do first thing")
        t2 = create_task("test-project", "Second", "Do second thing")
        assert t1.id == "1"
        assert t2.id == "2"

    def test_creates_json_file(self, task_dir):
        create_task("test-project", "Test", "A test")
        assert (task_dir / "1.json").exists()

    def test_writes_highwatermark(self, task_dir):
        create_task("test-project", "Test", "A test")
        assert (task_dir / ".highwatermark").read_text() == "1"

    def test_task_fields_stored_correctly(self, task_dir):
        t = create_task("test-project", "Fix bug", "Fix the login bug", active_form="Fixing bug", metadata={"priority": "high"})
        data = json.loads((task_dir / "1.json").read_text())
        assert data["subject"] == "Fix bug"
        assert data["description"] == "Fix the login bug"
        assert data["activeForm"] == "Fixing bug"
        assert data["status"] == "pending"
        assert data["metadata"]["priority"] == "high"

    def test_auto_creates_directory(self, tmp_path, monkeypatch):
        new_dir = tmp_path / "new-project"
        monkeypatch.setattr("agent.tasks._get_tasks_dir", lambda _slug: new_dir)
        t = create_task("new-project", "Test", "A test")
        assert new_dir.exists()
        assert t.id == "1"


class TestGetTask:
    def test_returns_existing_task(self, task_dir):
        create_task("test-project", "Test", "A test")
        t = get_task("test-project", "1")
        assert t is not None
        assert t.subject == "Test"

    def test_returns_none_for_missing(self, task_dir):
        assert get_task("test-project", "999") is None

    def test_returns_none_for_corrupt_json(self, task_dir):
        (task_dir / "1.json").write_text("not json{{{")
        assert get_task("test-project", "1") is None


class TestListTasks:
    def test_lists_all_tasks(self, task_dir):
        create_task("test-project", "First", "One")
        create_task("test-project", "Second", "Two")
        tasks = list_tasks("test-project")
        assert len(tasks) == 2

    def test_includes_internal_tasks(self, task_dir):
        create_task("test-project", "Internal", "Hidden", metadata={"_internal": True})
        tasks = list_tasks("test-project")
        assert len(tasks) == 1

    def test_skips_corrupt_files(self, task_dir):
        create_task("test-project", "Good", "A good task")
        (task_dir / "2.json").write_text("bad json")
        tasks = list_tasks("test-project")
        assert len(tasks) == 1
        assert tasks[0].subject == "Good"


class TestUpdateTask:
    def test_updates_subject(self, task_dir):
        create_task("test-project", "Old", "Desc")
        t = update_task("test-project", "1", subject="New")
        assert t.subject == "New"

    def test_updates_status(self, task_dir):
        create_task("test-project", "Test", "Desc")
        t = update_task("test-project", "1", status="in_progress")
        assert t.status == TaskStatus.IN_PROGRESS

    def test_returns_none_for_missing(self, task_dir):
        assert update_task("test-project", "999", subject="X") is None

    def test_metadata_shallow_merge(self, task_dir):
        create_task("test-project", "Test", "Desc", metadata={"a": 1, "b": 2})
        t = update_task("test-project", "1", metadata={"b": 3, "c": 4})
        assert t.metadata == {"a": 1, "b": 3, "c": 4}

    def test_metadata_null_deletes_key(self, task_dir):
        create_task("test-project", "Test", "Desc", metadata={"a": 1, "b": 2})
        t = update_task("test-project", "1", metadata={"a": None})
        assert "a" not in t.metadata
        assert t.metadata["b"] == 2


class TestDeleteTask:
    def test_deletes_json_file(self, task_dir):
        create_task("test-project", "Test", "Desc")
        result = delete_task("test-project", "1")
        assert result is True
        assert not (task_dir / "1.json").exists()

    def test_returns_false_for_missing(self, task_dir):
        assert delete_task("test-project", "999") is False

    def test_updates_highwatermark(self, task_dir):
        create_task("test-project", "First", "One")
        create_task("test-project", "Second", "Two")
        delete_task("test-project", "2")
        assert (task_dir / ".highwatermark").read_text() == "2"

    def test_cleans_up_dependency_references(self, task_dir):
        t1 = create_task("test-project", "Blocker", "Blocks task 2")
        t2 = create_task("test-project", "Blocked", "Blocked by task 1")
        from agent.tasks import block_task
        block_task("test-project", "1", "2")
        delete_task("test-project", "1")
        remaining = get_task("test-project", "2")
        assert "1" not in remaining.blockedBy

    def test_id_never_reused_after_delete(self, task_dir):
        create_task("test-project", "First", "One")
        create_task("test-project", "Second", "Two")
        delete_task("test-project", "1")
        t3 = create_task("test-project", "Third", "Three")
        assert t3.id == "3"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_tasks.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.tasks'`

- [ ] **Step 3: Implement `agent/tasks.py` — data model and core CRUD**

```python
# agent/tasks.py
"""Persistent task list — modeled after Claude Code's V2 task system (src/utils/tasks.ts)."""

from __future__ import annotations

import json
import os
import logging
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any

from agent.session import sanitize_path

log = logging.getLogger(__name__)

_TASKS_BASE = Path.home() / ".bitz" / "tasks"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass
class Task:
    id: str
    subject: str
    description: str
    activeForm: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    blocks: list[str] = field(default_factory=list)
    blockedBy: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> Task:
        data = dict(data)
        data["status"] = TaskStatus(data["status"])
        return cls(**data)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_tasks_dir(project_slug: str) -> Path:
    return _TASKS_BASE / project_slug


def get_project_slug() -> str:
    return sanitize_path(os.getcwd())


def _read_highwatermark(tasks_dir: Path) -> int:
    hwm_file = tasks_dir / ".highwatermark"
    if hwm_file.exists():
        try:
            return int(hwm_file.read_text().strip())
        except (ValueError, OSError):
            pass
    return 0


def _write_highwatermark(tasks_dir: Path, value: int) -> None:
    (tasks_dir / ".highwatermark").write_text(str(value))


def _max_id_from_filenames(tasks_dir: Path) -> int:
    max_id = 0
    if tasks_dir.exists():
        for f in tasks_dir.iterdir():
            if f.suffix == ".json" and f.stem.isdigit():
                max_id = max(max_id, int(f.stem))
    return max_id


def _next_id(tasks_dir: Path) -> str:
    current_max = max(_max_id_from_filenames(tasks_dir), _read_highwatermark(tasks_dir))
    next_val = current_max + 1
    _write_highwatermark(tasks_dir, next_val)
    return str(next_val)


def _ensure_dir(tasks_dir: Path) -> None:
    tasks_dir.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------

def create_task(project_slug: str, subject: str, description: str,
                active_form: str | None = None,
                metadata: dict[str, Any] | None = None) -> Task:
    tasks_dir = _get_tasks_dir(project_slug)
    _ensure_dir(tasks_dir)
    task_id = _next_id(tasks_dir)
    task = Task(
        id=task_id,
        subject=subject,
        description=description,
        activeForm=active_form,
        metadata=metadata or {},
    )
    (tasks_dir / f"{task_id}.json").write_text(json.dumps(task.to_dict(), ensure_ascii=False, indent=2))
    return task


def get_task(project_slug: str, task_id: str) -> Task | None:
    tasks_dir = _get_tasks_dir(project_slug)
    fpath = tasks_dir / f"{task_id}.json"
    if not fpath.exists():
        return None
    try:
        data = json.loads(fpath.read_text())
        return Task.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        log.warning("Corrupt task file %s: %s", fpath, e)
        return None


def list_tasks(project_slug: str) -> list[Task]:
    tasks_dir = _get_tasks_dir(project_slug)
    if not tasks_dir.exists():
        return []
    tasks = []
    for f in sorted(tasks_dir.glob("*.json"), key=lambda p: p.stem):
        if not f.stem.isdigit():
            continue
        t = get_task(project_slug, f.stem)
        if t is not None:
            tasks.append(t)
    return tasks


def update_task(project_slug: str, task_id: str, **updates) -> Task | None:
    task = get_task(project_slug, task_id)
    if task is None:
        return None

    # Handle delete
    if updates.get("status") == "deleted":
        delete_task(project_slug, task_id)
        return None

    # Handle dependency additions
    add_blocks = updates.pop("add_blocks", None)
    add_blocked_by = updates.pop("add_blocked_by", None)

    # Apply field updates
    for key, value in updates.items():
        if key == "status" and isinstance(value, str):
            value = TaskStatus(value)
        if key == "metadata" and isinstance(value, dict):
            # Shallow merge: new keys replace, None values delete
            for k, v in value.items():
                if v is None:
                    task.metadata.pop(k, None)
                else:
                    task.metadata[k] = v
        elif hasattr(task, key):
            setattr(task, key, value)

    # Write updated task
    tasks_dir = _get_tasks_dir(project_slug)
    (tasks_dir / f"{task_id}.json").write_text(json.dumps(task.to_dict(), ensure_ascii=False, indent=2))

    # Apply dependency additions after writing base update
    if add_blocks:
        for block_id in add_blocks:
            block_task(project_slug, task_id, block_id)
    if add_blocked_by:
        for blocker_id in add_blocked_by:
            block_task(project_slug, blocker_id, task_id)

    # Re-read to get updated dependency fields
    return get_task(project_slug, task_id)


def delete_task(project_slug: str, task_id: str) -> bool:
    tasks_dir = _get_tasks_dir(project_slug)
    fpath = tasks_dir / f"{task_id}.json"
    if not fpath.exists():
        return False

    # Update highwatermark
    current_hwm = _read_highwatermark(tasks_dir)
    new_hwm = max(current_hwm, int(task_id))
    _write_highwatermark(tasks_dir, new_hwm)

    # Delete the file
    fpath.unlink()

    # Clean up dependency references in all other tasks
    for t in list_tasks(project_slug):
        changed = False
        if task_id in t.blocks:
            t.blocks.remove(task_id)
            changed = True
        if task_id in t.blockedBy:
            t.blockedBy.remove(task_id)
            changed = True
        if changed:
            (tasks_dir / f"{t.id}.json").write_text(json.dumps(t.to_dict(), ensure_ascii=False, indent=2))

    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_tasks.py::TestTaskModel tests/test_tasks.py::TestCreateTask tests/test_tasks.py::TestGetTask tests/test_tasks.py::TestListTasks tests/test_tasks.py::TestUpdateTask tests/test_tasks.py::TestDeleteTask -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add agent/tasks.py tests/test_tasks.py
git commit -m "feat: add Task data model and persistence CRUD"
```

---

### Task 2: Task Dependencies — block_task, has_cycle, is_blocked

**Files:**
- Modify: `agent/tasks.py`
- Modify: `tests/test_tasks.py`

- [ ] **Step 1: Write failing tests for dependency functions**

Append to `tests/test_tasks.py`:

```python
class TestBlockTask:
    def test_creates_bidirectional_link(self, task_dir):
        create_task("test-project", "Blocker", "Blocks task 2")
        create_task("test-project", "Blocked", "Blocked by task 1")
        result = block_task("test-project", "1", "2")
        assert result is True
        blocker = get_task("test-project", "1")
        blocked = get_task("test-project", "2")
        assert "2" in blocker.blocks
        assert "1" in blocked.blockedBy

    def test_rejects_circular_dependency(self, task_dir):
        create_task("test-project", "A", "Task A")
        create_task("test-project", "B", "Task B")
        create_task("test-project", "C", "Task C")
        block_task("test-project", "1", "2")
        block_task("test-project", "2", "3")
        result = block_task("test-project", "3", "1")
        assert result is False

    def test_rejects_direct_cycle(self, task_dir):
        create_task("test-project", "A", "Task A")
        create_task("test-project", "B", "Task B")
        block_task("test-project", "1", "2")
        result = block_task("test-project", "2", "1")
        assert result is False

    def test_allows_non_circular_chain(self, task_dir):
        create_task("test-project", "A", "Task A")
        create_task("test-project", "B", "Task B")
        create_task("test-project", "C", "Task C")
        assert block_task("test-project", "1", "2") is True
        assert block_task("test-project", "2", "3") is True


class TestHasCycle:
    def test_detects_no_cycle(self, task_dir):
        create_task("test-project", "A", "Task A")
        create_task("test-project", "B", "Task B")
        tasks = list_tasks("test-project")
        assert has_cycle(tasks, "1", "2") is False

    def test_detects_cycle(self, task_dir):
        create_task("test-project", "A", "Task A")
        create_task("test-project", "B", "Task B")
        block_task("test-project", "2", "1")
        tasks = list_tasks("test-project")
        assert has_cycle(tasks, "1", "2") is True


class TestIsBlocked:
    def test_not_blocked_when_no_blockers(self, task_dir):
        create_task("test-project", "Free", "No blockers")
        tasks = list_tasks("test-project")
        assert is_blocked(tasks[0], tasks) is False

    def test_blocked_by_pending_task(self, task_dir):
        create_task("test-project", "Blocker", "Blocks task 2")
        create_task("test-project", "Blocked", "Blocked by task 1")
        block_task("test-project", "1", "2")
        tasks = list_tasks("test-project")
        blocked = [t for t in tasks if t.id == "2"][0]
        assert is_blocked(blocked, tasks) is True

    def test_not_blocked_after_blocker_completes(self, task_dir):
        create_task("test-project", "Blocker", "Blocks task 2")
        create_task("test-project", "Blocked", "Blocked by task 1")
        block_task("test-project", "1", "2")
        update_task("test-project", "1", status="completed")
        tasks = list_tasks("test-project")
        blocked = [t for t in tasks if t.id == "2"][0]
        assert is_blocked(blocked, tasks) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_tasks.py::TestBlockTask tests/test_tasks.py::TestHasCycle tests/test_tasks.py::TestIsBlocked -v`
Expected: FAIL — `ImportError: cannot import name 'block_task'` (or `has_cycle`, `is_blocked`)

- [ ] **Step 3: Implement dependency functions in `agent/tasks.py`**

Append to `agent/tasks.py`:

```python
# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def has_cycle(all_tasks: list[Task], start_id: str, target_id: str) -> bool:
    """DFS from start_id following blocks edges; return True if target_id is reachable."""
    visited: set[str] = set()
    task_map = {t.id: t for t in all_tasks}

    def dfs(current: str) -> bool:
        if current == target_id:
            return True
        if current in visited:
            return False
        visited.add(current)
        task = task_map.get(current)
        if task is None:
            return False
        for blocked_id in task.blocks:
            if dfs(blocked_id):
                return True
        return False

    return dfs(start_id)


def block_task(project_slug: str, blocker_id: str, blocked_id: str) -> bool:
    """Create bidirectional dependency: blocker_id blocks blocked_id."""
    all_tasks = list_tasks(project_slug)

    # Check for circular dependency: would adding blocker_id->blocked_id create a cycle?
    # A cycle exists if blocked_id can already reach blocker_id via blocks edges
    if has_cycle(all_tasks, blocked_id, blocker_id):
        return False

    blocker = get_task(project_slug, blocker_id)
    blocked = get_task(project_slug, blocked_id)
    if blocker is None or blocked is None:
        return False

    if blocked_id not in blocker.blocks:
        blocker.blocks.append(blocked_id)
    if blocker_id not in blocked.blockedBy:
        blocked.blockedBy.append(blocker_id)

    tasks_dir = _get_tasks_dir(project_slug)
    (tasks_dir / f"{blocker_id}.json").write_text(json.dumps(blocker.to_dict(), ensure_ascii=False, indent=2))
    (tasks_dir / f"{blocked_id}.json").write_text(json.dumps(blocked.to_dict(), ensure_ascii=False, indent=2))
    return True


def is_blocked(task: Task, all_tasks: list[Task]) -> bool:
    """Return True if task has any unresolved blocker."""
    task_map = {t.id: t for t in all_tasks}
    for blocker_id in task.blockedBy:
        blocker = task_map.get(blocker_id)
        if blocker is not None and blocker.status != TaskStatus.COMPLETED:
            return True
    return False
```

Also update the import line in `tests/test_tasks.py` to include `block_task`, `has_cycle`, `is_blocked`:

```python
from agent.tasks import Task, TaskStatus, create_task, get_task, list_tasks, delete_task, update_task, get_project_slug, block_task, has_cycle, is_blocked
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_tasks.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add agent/tasks.py tests/test_tasks.py
git commit -m "feat: add task dependency helpers (block_task, has_cycle, is_blocked)"
```

---

### Task 3: Task Tools — TaskCreate and TaskList

**Files:**
- Modify: `agent/builtin_tools.py`
- Create: `tests/test_task_tools.py`

- [ ] **Step 1: Write failing tests for TaskCreate and TaskList tools**

```python
# tests/test_task_tools.py
import json
import pytest
from pathlib import Path
from agent.tools import ToolRegistry
from agent.builtin_tools import create_tools


@pytest.fixture
def tools_and_dir(tmp_path, monkeypatch):
    """Create a ToolRegistry with task tools, patching the task directory."""
    slug = "test-project"
    tdir = tmp_path / "bitz-tasks" / slug
    tdir.mkdir(parents=True)
    monkeypatch.setattr("agent.tasks._get_tasks_dir", lambda _slug: tdir)
    monkeypatch.setattr("agent.tasks.get_project_slug", lambda: slug)
    tools = create_tools()
    return tools, tdir


class TestTaskCreateTool:
    def test_creates_task_via_tool(self, tools_and_dir):
        tools, tdir = tools_and_dir
        result = tools.execute("task_create", {"subject": "Fix bug", "description": "Fix the login bug"})
        assert "Task #1 created successfully" in result
        assert "Fix bug" in result

    def test_creates_task_with_active_form(self, tools_and_dir):
        tools, tdir = tools_and_dir
        result = tools.execute("task_create", {
            "subject": "Fix bug",
            "description": "Fix the login bug",
            "active_form": "Fixing bug"
        })
        assert "Task #1 created successfully" in result

    def test_requires_subject_and_description(self, tools_and_dir):
        tools, tdir = tools_and_dir
        # Missing required fields — the LLM should not send this, but test the handler
        result = tools.execute("task_create", {"subject": "Fix bug"})
        assert "Error" in result or "required" in result.lower()


class TestTaskListTool:
    def test_lists_tasks(self, tools_and_dir):
        tools, tdir = tools_and_dir
        tools.execute("task_create", {"subject": "First", "description": "One"})
        tools.execute("task_create", {"subject": "Second", "description": "Two"})
        result = tools.execute("task_list", {})
        assert "#1" in result
        assert "#2" in result
        assert "pending" in result

    def test_hides_internal_tasks(self, tools_and_dir):
        tools, tdir = tools_and_dir
        tools.execute("task_create", {"subject": "Visible", "description": "Shown"})
        tools.execute("task_create", {"subject": "Internal", "description": "Hidden", "metadata": {"_internal": True}})
        result = tools.execute("task_list", {})
        assert "Visible" in result
        assert "Internal" not in result

    def test_shows_blocked_status(self, tools_and_dir):
        tools, tdir = tools_and_dir
        tools.execute("task_create", {"subject": "Blocker", "description": "Blocks 2"})
        tools.execute("task_create", {"subject": "Blocked", "description": "Blocked by 1"})
        tools.execute("task_update", {"task_id": "1", "add_blocks": ["2"]})
        result = tools.execute("task_list", {})
        assert "blocked by #1" in result

    def test_empty_list(self, tools_and_dir):
        tools, tdir = tools_and_dir
        result = tools.execute("task_list", {})
        assert "No tasks" in result or result.strip() == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_task_tools.py -v`
Expected: FAIL — task tools not registered

- [ ] **Step 3: Implement TaskCreate and TaskList tool handlers and registrations**

Add to `agent/builtin_tools.py`, inside `create_tools()` function, after the spawn tool registration and before `return tools`:

```python
    # ── Task tools ──────────────────────────────────────────────────────
    from agent.tasks import create_task, list_tasks, get_project_slug, is_blocked

    def task_create_handler(subject: str, description: str, active_form: str | None = None, metadata: dict | None = None) -> str:
        try:
            slug = get_project_slug()
            t = create_task(slug, subject, description, active_form=active_form, metadata=metadata)
            return f"Task #{t.id} created successfully: {t.subject}"
        except Exception as e:
            return f"Error creating task: {e}"

    def task_list_handler() -> str:
        try:
            slug = get_project_slug()
            tasks = list_tasks(slug)
            # Filter out _internal tasks
            visible = [t for t in tasks if not t.metadata.get("_internal")]
            if not visible:
                return "No tasks"
            lines = []
            for t in visible:
                unresolved = [bid for bid in t.blockedBy
                              if any(bt.id == bid and bt.status != TaskStatus.COMPLETED for bt in tasks)]
                line = f"#{t.id} [{t.status.value}] {t.subject}"
                if unresolved:
                    line += f" [blocked by {', '.join('#' + b for b in unresolved)}]"
                lines.append(line)
            return "\n".join(lines)
        except Exception as e:
            return f"Error listing tasks: {e}"

    tools.register(
        name="task_create",
        description="Create a new task to track work. Use proactively for non-trivial tasks (3+ steps). "
                    "Subject should be a brief imperative-form title. "
                    "Use active_form for present-continuous spinner text (e.g., 'Running tests'). "
                    "Don't create tasks for trivial single-step actions.",
        input_schema={
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "Brief imperative-form title (e.g., 'Fix authentication bug')"},
                "description": {"type": "string", "description": "Detailed requirements and context"},
                "active_form": {"type": "string", "description": "Present continuous form for spinner (e.g., 'Fixing authentication bug')"},
                "metadata": {"type": "object", "description": "Arbitrary metadata key-value pairs"}
            },
            "required": ["subject", "description"]
        },
        handler=task_create_handler,
    )

    tools.register(
        name="task_list",
        description="List all tasks and their status. Use to check available tasks or track progress. "
                    "Tasks with blockedBy cannot start until blockers complete.",
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=task_list_handler,
    )
```

Note: `task_list_handler` references `TaskStatus` — add `from agent.tasks import TaskStatus` to the import line at the top of the task tools section.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_task_tools.py::TestTaskCreateTool tests/test_task_tools.py::TestTaskListTool -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add agent/builtin_tools.py tests/test_task_tools.py
git commit -m "feat: add TaskCreate and TaskList tools"
```

---

### Task 4: Task Tools — TaskUpdate and TaskGet

**Files:**
- Modify: `agent/builtin_tools.py`
- Modify: `tests/test_task_tools.py`

- [ ] **Step 1: Write failing tests for TaskUpdate and TaskGet tools**

Append to `tests/test_task_tools.py`:

```python
class TestTaskUpdateTool:
    def test_updates_status(self, tools_and_dir):
        tools, tdir = tools_and_dir
        tools.execute("task_create", {"subject": "Test", "description": "Desc"})
        result = tools.execute("task_update", {"task_id": "1", "status": "in_progress"})
        assert "Updated task #1" in result

    def test_deletes_task(self, tools_and_dir):
        tools, tdir = tools_and_dir
        tools.execute("task_create", {"subject": "Test", "description": "Desc"})
        result = tools.execute("task_update", {"task_id": "1", "status": "deleted"})
        assert "deleted" in result

    def test_adds_blocks(self, tools_and_dir):
        tools, tdir = tools_and_dir
        tools.execute("task_create", {"subject": "A", "description": "Task A"})
        tools.execute("task_create", {"subject": "B", "description": "Task B"})
        result = tools.execute("task_update", {"task_id": "1", "add_blocks": ["2"]})
        assert "Updated task #1" in result

    def test_adds_blocked_by(self, tools_and_dir):
        tools, tdir = tools_and_dir
        tools.execute("task_create", {"subject": "A", "description": "Task A"})
        tools.execute("task_create", {"subject": "B", "description": "Task B"})
        result = tools.execute("task_update", {"task_id": "2", "add_blocked_by": ["1"]})
        assert "Updated task #2" in result

    def test_not_found(self, tools_and_dir):
        tools, tdir = tools_and_dir
        result = tools.execute("task_update", {"task_id": "999", "status": "in_progress"})
        assert "not found" in result.lower()

    def test_metadata_merge(self, tools_and_dir):
        tools, tdir = tools_and_dir
        tools.execute("task_create", {"subject": "Test", "description": "Desc", "metadata": {"a": 1}})
        result = tools.execute("task_update", {"task_id": "1", "metadata": {"b": 2}})
        assert "Updated task #1" in result
        data = json.loads((tdir / "1.json").read_text())
        assert data["metadata"]["a"] == 1
        assert data["metadata"]["b"] == 2


class TestTaskGetTool:
    def test_returns_task_details(self, tools_and_dir):
        tools, tdir = tools_and_dir
        tools.execute("task_create", {"subject": "Fix bug", "description": "Fix the login bug", "active_form": "Fixing bug"})
        result = tools.execute("task_get", {"task_id": "1"})
        assert "Task #1: Fix bug" in result
        assert "Status: pending" in result
        assert "Active form: Fixing bug" in result
        assert "Fix the login bug" in result

    def test_not_found(self, tools_and_dir):
        tools, tdir = tools_and_dir
        result = tools.execute("task_get", {"task_id": "999"})
        assert "not found" in result.lower()

    def test_shows_dependencies(self, tools_and_dir):
        tools, tdir = tools_and_dir
        tools.execute("task_create", {"subject": "A", "description": "Task A"})
        tools.execute("task_create", {"subject": "B", "description": "Task B"})
        tools.execute("task_update", {"task_id": "1", "add_blocks": ["2"]})
        result = tools.execute("task_get", {"task_id": "1"})
        assert "Blocks: #2" in result
        result2 = tools.execute("task_get", {"task_id": "2"})
        assert "Blocked by: #1" in result2

    def test_can_get_internal_task(self, tools_and_dir):
        tools, tdir = tools_and_dir
        tools.execute("task_create", {"subject": "Internal", "description": "Hidden", "metadata": {"_internal": True}})
        result = tools.execute("task_get", {"task_id": "1"})
        assert "Internal" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_task_tools.py::TestTaskUpdateTool tests/test_task_tools.py::TestTaskGetTool -v`
Expected: FAIL — `task_update` and `task_get` tools not registered

- [ ] **Step 3: Implement TaskUpdate and TaskGet tool handlers and registrations**

Add to `agent/builtin_tools.py`, after the `task_list` registration from Task 3, still inside `create_tools()`:

```python
    from agent.tasks import update_task, get_task, delete_task

    def task_update_handler(task_id: str, subject: str | None = None, description: str | None = None,
                            active_form: str | None = None, status: str | None = None,
                            metadata: dict | None = None,
                            add_blocks: list[str] | None = None,
                            add_blocked_by: list[str] | None = None) -> str:
        try:
            slug = get_project_slug()

            # Handle delete as a special case — don't include in updates dict
            if status == "deleted":
                ok = delete_task(slug, task_id)
                return f"Task #{task_id} deleted" if ok else f"Task #{task_id} not found"

            updates = {}
            if subject is not None:
                updates["subject"] = subject
            if description is not None:
                updates["description"] = description
            if active_form is not None:
                updates["active_form"] = active_form
            if status is not None:
                updates["status"] = status
            if metadata is not None:
                updates["metadata"] = metadata
            if add_blocks is not None:
                updates["add_blocks"] = add_blocks
            if add_blocked_by is not None:
                updates["add_blocked_by"] = add_blocked_by

            t = update_task(slug, task_id, **updates)
            if t is None:
                return f"Task #{task_id} not found"

            changed = [k for k, v in updates.items() if k not in ("add_blocks", "add_blocked_by") and v is not None]
            return f"Updated task #{task_id} {', '.join(changed)}" if changed else f"Updated task #{task_id}"
        except Exception as e:
            return f"Error updating task: {e}"

    def task_get_handler(task_id: str) -> str:
        try:
            slug = get_project_slug()
            t = get_task(slug, task_id)
            if t is None:
                return f"Task #{task_id} not found"
            lines = [f"Task #{t.id}: {t.subject}",
                     f"Status: {t.status.value}"]
            if t.activeForm:
                lines.append(f"Active form: {t.activeForm}")
            lines.append(f"Description: {t.description}")
            if t.blockedBy:
                lines.append(f"Blocked by: {', '.join('#' + b for b in t.blockedBy)}")
            if t.blocks:
                lines.append(f"Blocks: {', '.join('#' + b for b in t.blocks)}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error getting task: {e}"

    tools.register(
        name="task_update",
        description="Update an existing task. Mark in_progress before starting work, completed when done. "
                    "Use status 'deleted' to remove tasks. Set add_blocks/add_blocked_by for dependencies. "
                    "Never mark completed unless fully accomplished.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to update"},
                "subject": {"type": "string", "description": "New subject"},
                "description": {"type": "string", "description": "New description"},
                "active_form": {"type": "string", "description": "New present-continuous form"},
                "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "deleted"],
                           "description": "New status. Use 'deleted' to remove the task."},
                "metadata": {"type": "object", "description": "Metadata to merge. Null values delete keys."},
                "add_blocks": {"type": "array", "items": {"type": "string"},
                               "description": "Task IDs this task blocks"},
                "add_blocked_by": {"type": "array", "items": {"type": "string"},
                                   "description": "Task IDs that must complete before this one"}
            },
            "required": ["task_id"]
        },
        handler=task_update_handler,
    )

    tools.register(
        name="task_get",
        description="Get full details of a specific task. Use before starting work to understand requirements "
                    "and check blockedBy to see what must complete first.",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to retrieve"}
            },
            "required": ["task_id"]
        },
        handler=task_get_handler,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_task_tools.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add agent/builtin_tools.py tests/test_task_tools.py
git commit -m "feat: add TaskUpdate and TaskGet tools"
```

---

### Task 5: TaskListWidget — TUI Component

**Files:**
- Create: `tui/widgets/task_list.py`
- Create: `tests/test_task_list_widget.py`

- [ ] **Step 1: Write failing tests for TaskListWidget**

```python
# tests/test_task_list_widget.py
import pytest
from pathlib import Path
from textual.app import App, ComposeResult

from agent.tasks import create_task, update_task, block_task
from tui.widgets.task_list import TaskListWidget


class TaskListTestApp(App):
    CSS = "TaskListWidget { height: auto; }"

    def __init__(self, task_dir, slug, **kwargs):
        super().__init__(**kwargs)
        self.task_dir = task_dir
        self.slug = slug

    def compose(self) -> ComposeResult:
        yield TaskListWidget(project_slug=self.slug)


@pytest.fixture
def task_app(tmp_path, monkeypatch):
    slug = "test-project"
    tdir = tmp_path / "bitz-tasks" / slug
    tdir.mkdir(parents=True)
    monkeypatch.setattr("agent.tasks._get_tasks_dir", lambda _slug: tdir)
    return TaskListTestApp(tdir, slug), tdir, slug


@pytest.mark.asyncio
async def test_renders_empty_state(task_app):
    app, tdir, slug = task_app
    async with app.run_test() as pilot:
        widget = app.query_one(TaskListWidget)
        assert widget.display is False


@pytest.mark.asyncio
async def test_renders_tasks(task_app):
    app, tdir, slug = task_app
    create_task(slug, "Fix bug", "Fix the login bug")
    async with app.run_test() as pilot:
        widget = app.query_one(TaskListWidget)
        widget.refresh_tasks()
        await pilot.pause()
        content = str(widget.renderable)
        assert "Fix bug" in content


@pytest.mark.asyncio
async def test_shows_active_form_for_in_progress(task_app):
    app, tdir, slug = task_app
    create_task(slug, "Fix bug", "Fix the login bug", active_form="Fixing bug")
    update_task(slug, "1", status="in_progress")
    async with app.run_test() as pilot:
        widget = app.query_one(TaskListWidget)
        widget.refresh_tasks()
        await pilot.pause()
        content = str(widget.renderable)
        assert "Fixing bug" in content


@pytest.mark.asyncio
async def test_shows_blocked_status(task_app):
    app, tdir, slug = task_app
    create_task(slug, "Blocker", "Blocks task 2")
    create_task(slug, "Blocked", "Blocked by task 1")
    block_task(slug, "1", "2")
    async with app.run_test() as pilot:
        widget = app.query_one(TaskListWidget)
        widget.refresh_tasks()
        await pilot.pause()
        content = str(widget.renderable)
        assert "blocked" in content.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_task_list_widget.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tui.widgets.task_list'`

- [ ] **Step 3: Implement TaskListWidget**

```python
# tui/widgets/task_list.py
"""Task list widget — modeled after Claude Code's TaskListV2.tsx."""

from __future__ import annotations

import time
from textual.widgets import Static
from agent.tasks import list_tasks, is_blocked, get_project_slug, TaskStatus


class TaskListWidget(Static):
    """Displays the current task list with status icons and dependency info."""

    DEFAULT_CSS = """
    TaskListWidget {
        height: auto;
        max-height: 12;
        padding: 0 1;
        border-bottom: solid $primary-darken-2;
        background: $surface;
        color: $text;
    }
    """

    RECENT_COMPLETED_TTL = 30  # seconds
    MAX_DISPLAY = 10
    HIDE_DELAY = 5  # seconds

    def __init__(self, project_slug: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self._slug = project_slug
        self._all_completed_at: float | None = None
        self._hide_timer = None

    @property
    def slug(self) -> str:
        return self._slug or get_project_slug()

    def on_mount(self) -> None:
        self.refresh_tasks()
        self.set_interval(2, self.refresh_tasks)

    def refresh_tasks(self) -> None:
        """Reload tasks from disk and re-render."""
        try:
            tasks = list_tasks(self.slug)
        except Exception:
            self.display = False
            return

        if not tasks:
            self.display = False
            self._all_completed_at = None
            return

        # Check if all completed
        all_done = all(t.status == TaskStatus.COMPLETED for t in tasks)
        if all_done and self._all_completed_at is None:
            self._all_completed_at = time.time()
            self._hide_timer = self.set_timer(self.HIDE_DELAY, self._collapse)
        elif not all_done:
            self._all_completed_at = None
            if self._hide_timer is not None:
                self._hide_timer.stop()
                self._hide_timer = None

        self.display = True
        self.update(self._render(tasks))

    def _collapse(self) -> None:
        """Hide the widget after all tasks complete."""
        self.display = False

    def _render(self, tasks: list) -> str:
        now = time.time()
        visible = self._sort_and_limit(tasks, now)

        in_progress = sum(1 for t in tasks if t.status == TaskStatus.IN_PROGRESS)
        total = len(tasks)

        lines = [f"Tasks ({in_progress}/{total})"]
        lines.append("─" * 30)

        for t in visible:
            icon = self._status_icon(t.status)
            label = t.activeForm if (t.status == TaskStatus.IN_PROGRESS and t.activeForm) else t.subject
            line = f"{icon} {label}"

            # Show blocked status
            if t.status != TaskStatus.COMPLETED and is_blocked(t, tasks):
                blockers = [f"#{bid}" for bid in t.blockedBy
                            if any(bt.id == bid and bt.status != TaskStatus.COMPLETED for bt in tasks)]
                if blockers:
                    line += f"  [blocked by {', '.join(blockers)}]"

            lines.append(line)

        return "\n".join(lines)

    def _sort_and_limit(self, tasks: list, now: float) -> list:
        """Sort by priority: recent completed > in_progress > pending > older completed."""
        def sort_key(t):
            if t.status == TaskStatus.COMPLETED:
                completed_at = t.metadata.get("_completedAt", 0)
                if now - completed_at <= self.RECENT_COMPLETED_TTL:
                    return (-1, -completed_at)  # Recent completed first
                return (2, -completed_at)  # Older completed last
            elif t.status == TaskStatus.IN_PROGRESS:
                return (0, 0)
            else:  # pending
                return (1, 0)

        sorted_tasks = sorted(tasks, key=sort_key)
        return sorted_tasks[:self.MAX_DISPLAY]

    @staticmethod
    def _status_icon(status: TaskStatus) -> str:
        if status == TaskStatus.IN_PROGRESS:
            return "◉"
        elif status == TaskStatus.COMPLETED:
            return "✓"
        else:
            return "○"
```

Also update `agent/tasks.py` `update_task()` to record completion timestamp in metadata when status changes to `completed`. Add this after the `setattr(task, key, value)` line in the field updates loop:

```python
        # Record completion timestamp for TUI sorting
        if key == "status" and value == TaskStatus.COMPLETED:
            task.metadata["_completedAt"] = time.time()
```

And add `import time` at the top of `agent/tasks.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_task_list_widget.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add tui/widgets/task_list.py agent/tasks.py tests/test_task_list_widget.py
git commit -m "feat: add TaskListWidget TUI component"
```

---

### Task 6: Integrate TaskListWidget into BitzApp

**Files:**
- Modify: `tui/app.py`
- Modify: `tui/widgets/status.py`

- [ ] **Step 1: Add TaskListWidget to BitzApp.compose()**

In `tui/app.py`, add the import at the top:

```python
from tui.widgets.task_list import TaskListWidget
```

Modify the `compose()` method to include TaskListWidget:

```python
def compose(self) -> ComposeResult:
    yield TaskListWidget(id="task-list")
    yield ChatLog()
    yield ThinkingIndicator()
    yield StatusBar()
    yield InputBar(skill_registry=self._skill_registry)
```

- [ ] **Step 2: Wire refresh in `_install_tool_logger()` with thread safety**

In the `logged_execute` function inside `_install_tool_logger()`, add task widget refresh after tool execution. Find the line `app._post_tool_result(name, result, is_error, diff_text)` and add immediately after it (still inside the `try` block, before `finally`):

```python
                # Refresh task list after task tool execution (thread-safe)
                if name.startswith("task_"):
                    try:
                        task_widget = app.query_one("#task-list", TaskListWidget)
                        app.call_from_thread(task_widget.refresh_tasks)
                    except Exception:
                        pass
                    # Also update task count in StatusBar
                    try:
                        from agent.tasks import list_tasks as _list_tasks, get_project_slug as _get_slug, TaskStatus as _TS
                        _slug = _get_slug()
                        _tasks = _list_tasks(_slug)
                        _in_progress = sum(1 for t in _tasks if t.status == _TS.IN_PROGRESS)
                        status_bar = app.query_one(StatusBar)
                        app.call_from_thread(status_bar.update_task_count, _in_progress, len(_tasks))
                    except Exception:
                        pass
```

- [ ] **Step 3: Add task count to StatusBar using Rich Text pattern**

In `tui/widgets/status.py`, add a `task_count` field and update method. The existing `_render_left()` uses `Text` objects from `rich.text.Text` — we must follow the same pattern.

Add to `StatusBar.__init__()`:
```python
self.task_in_progress: int = 0
self.task_total: int = 0
```

Add method:
```python
def update_task_count(self, in_progress: int, total: int) -> None:
    self.task_in_progress = in_progress
    self.task_total = total
    self._refresh()
```

In `_render_left()`, insert the task count `Text` object after the token display and before the persistence error check. Find the block after `if self.input_tokens > 0 or self.output_tokens > 0:` and before `if self.persistence_error:`, add:

```python
        if self.task_total > 0:
            parts.append(Text(f"Tasks: {self.task_in_progress}/{self.task_total}", style=color))
```

- [ ] **Step 4: Run all tests**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add tui/app.py tui/widgets/status.py
git commit -m "feat: integrate TaskListWidget into BitzApp and StatusBar"
```

---

### Task 7: Edge Case Tests and Final Verification

**Files:**
- Modify: `tests/test_tasks.py`

- [ ] **Step 1: Add edge case tests**

Append to `tests/test_tasks.py`:

```python
class TestEdgeCases:
    def test_highwatermark_survives_multiple_deletes(self, task_dir):
        create_task("test-project", "A", "Task A")
        create_task("test-project", "B", "Task B")
        create_task("test-project", "C", "Task C")
        delete_task("test-project", "2")
        delete_task("test-project", "3")
        t4 = create_task("test-project", "D", "Task D")
        assert t4.id == "4"

    def test_missing_highwatermark_rebuilds(self, task_dir):
        create_task("test-project", "A", "Task A")
        create_task("test-project", "B", "Task B")
        (task_dir / ".highwatermark").unlink()
        t3 = create_task("test-project", "C", "Task C")
        assert t3.id == "3"

    def test_empty_task_dir(self, task_dir):
        tasks = list_tasks("test-project")
        assert tasks == []

    def test_update_only_changed_fields(self, task_dir):
        create_task("test-project", "Original", "Original desc")
        t = update_task("test-project", "1", subject="Updated")
        assert t.subject == "Updated"
        assert t.description == "Original desc"

    def test_block_task_with_nonexistent_task(self, task_dir):
        create_task("test-project", "A", "Task A")
        result = block_task("test-project", "1", "999")
        assert result is False

    def test_longer_cycle_detection(self, task_dir):
        """A -> B -> C -> D -> A should be rejected."""
        for i, name in enumerate(["A", "B", "C", "D"], 1):
            create_task("test-project", name, f"Task {name}")
        assert block_task("test-project", "1", "2") is True
        assert block_task("test-project", "2", "3") is True
        assert block_task("test-project", "3", "4") is True
        assert block_task("test-project", "4", "1") is False

    def test_delete_cleans_up_both_directions(self, task_dir):
        create_task("test-project", "A", "Task A")
        create_task("test-project", "B", "Task B")
        create_task("test-project", "C", "Task C")
        block_task("test-project", "1", "2")
        block_task("test-project", "1", "3")
        delete_task("test-project", "1")
        t2 = get_task("test-project", "2")
        t3 = get_task("test-project", "3")
        assert "1" not in t2.blockedBy
        assert "1" not in t3.blockedBy
```

- [ ] **Step 2: Run all tests**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_tasks.py
git commit -m "test: add task system edge case tests"
```

---

### Task 8: Manual Smoke Test

- [ ] **Step 1: Start the TUI and verify task tools work**

Run: `cd /Users/breeze/projects/Research/Bitz && python tui.py`

In the chat, ask the agent to:
1. Create a task: "Create a task to fix the login bug"
2. Verify the TaskListWidget appears in the TUI
3. Update the task: "Mark task 1 as in progress"
4. Verify the status icon changes to ◉
5. Complete the task: "Mark task 1 as completed"
6. Verify the task shows ✓ and auto-hides after 5 seconds

- [ ] **Step 2: Verify StatusBar shows task count**

Check that "Tasks: 1/1" appears in the status bar when a task exists.

- [ ] **Step 3: Commit any fixes**

```bash
git add -A
git commit -m "fix: task system smoke test fixes"
```
