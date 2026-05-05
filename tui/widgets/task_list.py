"""TaskListWidget – displays the current task list with status icons and dependency info."""
from __future__ import annotations

import time
from pathlib import Path

from textual.widgets import Static

from agent.tasks import TaskStatus, list_tasks


class TaskListWidget(Static):
    """Displays the current task list with status icons and dependency info."""

    DEFAULT_CSS = """
    TaskListWidget {
        height: auto;
        max-height: 12;
        padding: 0 1;
        border-bottom: solid $primary;
        background: $surface;
    }
    """

    RECENT_COMPLETED_TTL: int = 30  # seconds
    MAX_DISPLAY: int = 10
    HIDE_DELAY: int = 5  # seconds before hiding when all completed

    def __init__(
        self,
        project_slug: str | None = None,
        session_id: str | None = None,
        base_dir: Path | None = None,
        **kwargs,
    ) -> None:
        super().__init__("", **kwargs)
        self.project_slug = project_slug
        self.session_id = session_id
        self.base_dir = base_dir
        self._hide_timer = None
        self._has_content = False
        self._collapsed = False

    @property
    def has_content(self) -> bool:
        """Whether the widget is currently showing tasks."""
        return self._has_content

    def on_mount(self) -> None:
        self.refresh_tasks()
        self.set_interval(2, self.refresh_tasks)

    def refresh_tasks(self) -> None:
        """Load tasks from disk and update display."""
        if not self.project_slug:
            self._clear()
            return

        try:
            tasks = list_tasks(self.project_slug, session_id=self.session_id, base_dir=self.base_dir)
        except Exception:
            tasks = []

        if not tasks:
            self._clear()
            return

        # Check if all tasks are completed
        all_completed = all(t.status == TaskStatus.COMPLETED for t in tasks)

        if all_completed and self._collapsed:
            # Already collapsed after all-completed, don't re-render
            return

        if all_completed:
            # Render once with completed tasks, then start hide timer
            now = time.time()
            limited = self._sort_and_limit(tasks, now)
            self._render_tasks(limited)
            if self._hide_timer is None:
                self._hide_timer = self.set_timer(self.HIDE_DELAY, self._collapse)
            return

        # Active tasks exist — cancel any pending hide and reset collapsed state
        if self._hide_timer is not None:
            self._hide_timer.stop()
            self._hide_timer = None
        self._collapsed = False

        now = time.time()
        limited = self._sort_and_limit(tasks, now)
        self._render_tasks(limited)

    def _clear(self) -> None:
        """Clear the widget content."""
        self._collapsed = False
        self._has_content = False
        self.update("")

    def _collapse(self) -> None:
        """Hide the widget (called by timer after all tasks completed)."""
        self._hide_timer = None
        self._collapsed = True
        self._has_content = False
        self.update("")

    def _render_tasks(self, tasks: list) -> None:
        """Format and display tasks."""
        in_progress_count = sum(
            1 for t in tasks if t.status == TaskStatus.IN_PROGRESS
        )
        completed_count = sum(
            1 for t in tasks if t.status == TaskStatus.COMPLETED
        )
        total = len(tasks)

        # Show completed count when all done, in_progress count otherwise
        active_count = completed_count if completed_count == total else in_progress_count
        header = f"Tasks ({active_count}/{total})"
        sep = "─" * 30

        lines = [header, sep]
        for t in tasks:
            icon = self._status_icon(t.status)
            # For in_progress tasks with activeForm, show activeForm
            if t.status == TaskStatus.IN_PROGRESS and t.activeForm:
                label = t.activeForm
            else:
                label = t.subject

            line = f" {icon} #{t.id} {label}"

            # Show blocked indicator
            if t.blockedBy:
                blocked_ids = ", ".join(f"#{bid}" for bid in t.blockedBy)
                line += f"  [blocked by {blocked_ids}]"

            lines.append(line)

        self._has_content = True
        self.update("\n".join(lines))

    def _sort_and_limit(self, tasks: list, now: float) -> list:
        """Sort tasks by priority and limit to MAX_DISPLAY.

        Priority order: recent completed (within TTL) > in_progress > pending > older completed.
        """
        recent_completed = []
        in_progress = []
        pending = []
        older_completed = []

        for t in tasks:
            if t.status == TaskStatus.COMPLETED:
                completed_at = t.metadata.get("_completedAt", 0)
                if now - completed_at < self.RECENT_COMPLETED_TTL:
                    recent_completed.append(t)
                else:
                    older_completed.append(t)
            elif t.status == TaskStatus.IN_PROGRESS:
                in_progress.append(t)
            else:
                pending.append(t)

        result = recent_completed + in_progress + pending + older_completed
        return result[: self.MAX_DISPLAY]

    @staticmethod
    def _status_icon(status: TaskStatus) -> str:
        """Return the Unicode status icon."""
        if status == TaskStatus.IN_PROGRESS:
            return "◉"
        if status == TaskStatus.COMPLETED:
            return "✓"
        return "○"
