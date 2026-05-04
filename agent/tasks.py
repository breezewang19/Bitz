"""Task data model and persistence CRUD layer."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any

from agent.session import sanitize_path

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Model
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

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict with status as string (not enum)."""
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        """Deserialize from dict, converting status string to enum."""
        data = dict(data)  # shallow copy to avoid mutating input
        status_val = data.pop("status", "pending")
        data["status"] = TaskStatus(status_val)
        # Ensure defaults for optional / default-factory fields
        data.setdefault("activeForm", None)
        data.setdefault("blocks", [])
        data.setdefault("blockedBy", [])
        data.setdefault("metadata", {})
        return cls(**data)


# ---------------------------------------------------------------------------
# Directory / path helpers
# ---------------------------------------------------------------------------

def get_project_slug() -> str:
    """Return a slug derived from the current working directory."""
    return sanitize_path(os.getcwd())


def _get_tasks_dir(project_slug: str, base_dir: Path | None = None) -> Path:
    """Return the tasks directory for a project slug.

    Default: ``~/.bitz/tasks/<slug>/``.
    """
    root = base_dir or (Path.home() / ".bitz" / "tasks")
    return root / project_slug


def _ensure_dir(path: Path) -> None:
    """Create *path* (and parents) if it does not exist."""
    path.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# High-water-mark helpers
# ---------------------------------------------------------------------------

def _read_highwatermark(tasks_dir: Path) -> int:
    """Read the high-water mark file.  Returns 0 if missing / corrupt."""
    hw_path = tasks_dir / ".highwatermark"
    if not hw_path.exists():
        return 0
    try:
        return int(hw_path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return 0


def _write_highwatermark(tasks_dir: Path, value: int) -> None:
    """Write the high-water mark value."""
    _ensure_dir(tasks_dir)
    (tasks_dir / ".highwatermark").write_text(str(value), encoding="utf-8")


def _max_id_from_filenames(tasks_dir: Path) -> int:
    """Scan ``*.json`` filenames and return the max numeric ID (0 if none)."""
    if not tasks_dir.exists():
        return 0
    max_id = 0
    for p in tasks_dir.glob("*.json"):
        stem = p.stem
        if stem.isdigit():
            max_id = max(max_id, int(stem))
    return max_id


def _next_id(tasks_dir: Path) -> int:
    """Determine the next task ID (1-based).

    Takes max of (max filename ID, highwatermark) + 1.
    """
    return max(_max_id_from_filenames(tasks_dir), _read_highwatermark(tasks_dir)) + 1


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------

def create_task(
    project_slug: str,
    subject: str,
    description: str,
    active_form: str | None = None,
    metadata: dict[str, Any] | None = None,
    *,
    base_dir: Path | None = None,
) -> Task:
    """Create a new task and persist it to disk.

    Returns the created :class:`Task`.
    """
    tasks_dir = _get_tasks_dir(project_slug, base_dir)
    _ensure_dir(tasks_dir)

    next_id = _next_id(tasks_dir)
    task = Task(
        id=str(next_id),
        subject=subject,
        description=description,
        activeForm=active_form,
        metadata=metadata if metadata is not None else {},
    )

    # Write JSON file
    task_path = tasks_dir / f"{task.id}.json"
    task_path.write_text(
        json.dumps(task.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Update high-water mark
    _write_highwatermark(tasks_dir, next_id)

    return task


def get_task(
    project_slug: str,
    task_id: str,
    *,
    base_dir: Path | None = None,
) -> Task | None:
    """Read a single task by ID.  Returns ``None`` if not found or corrupt."""
    tasks_dir = _get_tasks_dir(project_slug, base_dir)
    task_path = tasks_dir / f"{task_id}.json"
    if not task_path.exists():
        return None
    try:
        data = json.loads(task_path.read_text(encoding="utf-8"))
        return Task.from_dict(data)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        log.warning("Skipping corrupt task file %s: %s", task_path, exc)
        return None


def list_tasks(
    project_slug: str,
    *,
    base_dir: Path | None = None,
) -> list[Task]:
    """List all tasks (including ``_internal`` ones).

    Filtering of ``_internal`` tasks is a tool-layer concern.
    """
    tasks_dir = _get_tasks_dir(project_slug, base_dir)
    if not tasks_dir.exists():
        return []
    tasks: list[Task] = []
    for p in sorted(tasks_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            tasks.append(Task.from_dict(data))
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            log.warning("Skipping corrupt task file %s: %s", p, exc)
            continue
    return tasks


def has_cycle(all_tasks: list[Task], start_id: str, target_id: str) -> bool:
    """DFS from *start_id* following ``blocks`` edges.

    Return ``True`` if *target_id* is reachable, indicating that adding a
    dependency from *target_id* back to *start_id* would create a cycle.
    """
    # Build adjacency map: task_id -> list of task IDs it blocks
    adj: dict[str, list[str]] = {t.id: list(t.blocks) for t in all_tasks}

    visited: set[str] = set()
    stack = [start_id]
    while stack:
        current = stack.pop()
        if current == target_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        stack.extend(adj.get(current, []))
    return False


def block_task(
    project_slug: str,
    blocker_id: str,
    blocked_id: str,
    *,
    base_dir: Path | None = None,
) -> bool:
    """Create a bidirectional dependency between two tasks.

    *blocker_id* gains *blocked_id* in ``blocks``; *blocked_id* gains
    *blocker_id* in ``blockedBy``.

    Returns ``False`` if a circular dependency would result or either task
    doesn't exist.  Returns ``True`` on success.
    """
    # Load both tasks
    blocker = get_task(project_slug, blocker_id, base_dir=base_dir)
    blocked = get_task(project_slug, blocked_id, base_dir=base_dir)
    if blocker is None or blocked is None:
        return False

    # Check for circular dependency: would adding blocker->blocked create a
    # path from blocked back to blocker?
    all_tasks = list_tasks(project_slug, base_dir=base_dir)
    if has_cycle(all_tasks, start_id=blocked_id, target_id=blocker_id):
        return False

    tasks_dir = _get_tasks_dir(project_slug, base_dir)

    # Apply bidirectional links
    if blocked_id not in blocker.blocks:
        blocker.blocks.append(blocked_id)
        _write_task(tasks_dir, blocker)

    if blocker_id not in blocked.blockedBy:
        blocked.blockedBy.append(blocker_id)
        _write_task(tasks_dir, blocked)

    return True


def is_blocked(task: Task, all_tasks: list[Task]) -> bool:
    """Return ``True`` if any task in *task.blockedBy* is not COMPLETED."""
    by_id: dict[str, Task] = {t.id: t for t in all_tasks}
    for blocker_id in task.blockedBy:
        blocker = by_id.get(blocker_id)
        if blocker is not None and blocker.status != TaskStatus.COMPLETED:
            return True
    return False


def update_task(
    project_slug: str,
    task_id: str,
    *,
    base_dir: Path | None = None,
    **updates: Any,
) -> Task | None:
    """Update an existing task.

    Special handling:
    - ``status="deleted"``: delegates to :func:`delete_task`.
    - ``add_blocks`` / ``add_blocked_by``: sets dependency links via :func:`block_task`.
    - ``metadata``: shallow-merged with null-deletion.
    """
    tasks_dir = _get_tasks_dir(project_slug, base_dir)
    task = get_task(project_slug, task_id, base_dir=base_dir)
    if task is None:
        return None

    # --- Handle status="deleted" as a delete action ---
    status_update = updates.get("status")
    if status_update == "deleted":
        delete_task(project_slug, task_id, base_dir=base_dir)
        return None  # task no longer exists

    # --- Extract add_blocks / add_blocked_by before general field update ---
    add_blocks = updates.pop("add_blocks", None)
    add_blocked_by = updates.pop("add_blocked_by", None)

    # --- Apply scalar / simple fields ---
    if "status" in updates:
        task.status = TaskStatus(updates.pop("status"))
    if "subject" in updates:
        task.subject = updates.pop("subject")
    if "description" in updates:
        task.description = updates.pop("description")
    if "active_form" in updates:
        task.activeForm = updates.pop("active_form")

    # --- Metadata: shallow merge with null-deletion ---
    meta_update = updates.pop("metadata", None)
    if meta_update is not None:
        for k, v in meta_update.items():
            if v is None:
                task.metadata.pop(k, None)
            else:
                task.metadata[k] = v

    # --- Dependency links (delegated to block_task) ---
    if add_blocks:
        for block_id in add_blocks:
            block_task(project_slug, task_id, block_id, base_dir=base_dir)
        # Refresh task from disk to reflect changes made by block_task
        task = get_task(project_slug, task_id, base_dir=base_dir)
        if task is None:
            return None

    if add_blocked_by:
        for blocker_id in add_blocked_by:
            block_task(project_slug, blocker_id, task_id, base_dir=base_dir)
        # Refresh task from disk to reflect changes made by block_task
        task = get_task(project_slug, task_id, base_dir=base_dir)
        if task is None:
            return None

    # --- Persist ---
    _write_task(tasks_dir, task)
    return task


def delete_task(
    project_slug: str,
    task_id: str,
    *,
    base_dir: Path | None = None,
) -> bool:
    """Delete a task by ID.

    - Updates high-water mark to ``max(current_hw, task_id_numeric)``.
    - Removes the JSON file.
    - Cleans up dependency references in all other tasks.
    - Returns ``True`` if deleted, ``False`` if not found.
    """
    tasks_dir = _get_tasks_dir(project_slug, base_dir)
    task_path = tasks_dir / f"{task_id}.json"
    if not task_path.exists():
        return False

    # --- Update high-water mark ---
    current_hw = _read_highwatermark(tasks_dir)
    task_id_num = int(task_id) if task_id.isdigit() else 0
    new_hw = max(current_hw, task_id_num)
    _write_highwatermark(tasks_dir, new_hw)

    # --- Delete the file ---
    task_path.unlink()

    # --- Clean up dependency references in all other tasks ---
    all_tasks = list_tasks(project_slug, base_dir=base_dir)
    for other in all_tasks:
        changed = False
        if task_id in other.blocks:
            other.blocks.remove(task_id)
            changed = True
        if task_id in other.blockedBy:
            other.blockedBy.remove(task_id)
            changed = True
        if changed:
            _write_task(tasks_dir, other)

    return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _write_task(tasks_dir: Path, task: Task) -> None:
    """Persist a task to its JSON file."""
    _ensure_dir(tasks_dir)
    task_path = tasks_dir / f"{task.id}.json"
    task_path.write_text(
        json.dumps(task.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
