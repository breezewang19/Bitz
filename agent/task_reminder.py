# agent/task_reminder.py
"""Task reminder — nudge agent to use task tools after prolonged disuse."""
from __future__ import annotations


TASK_TOOL_NAMES = {"task_create", "task_update", "task_list", "task_get"}
REMINDER_THRESHOLD = 10  # steps since last task tool use
REMINDER_COOLDOWN = 10   # steps between reminders

_NUDGE = (
    "你最近没有使用任务工具。如果正在处理多步骤任务，"
    "考虑用 task_create 创建新任务，用 task_update 更新状态"
    "（开始时 in_progress，完成时 completed）。"
    "不要向用户提及此提醒。"
)


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
        task_summary: Formatted task list string, or None if no active tasks.

    Returns the reminder text, or None if no reminder is needed.
    """
    # Check threshold: steps since last task tool use
    if last_task_tool_step is not None:
        if step_count - last_task_tool_step < REMINDER_THRESHOLD:
            return None
    else:
        # Never used a task tool — use step_count as proxy
        if step_count < REMINDER_THRESHOLD:
            return None

    # Check cooldown: steps since last reminder
    if last_reminder_step is not None:
        if step_count - last_reminder_step < REMINDER_COOLDOWN:
            return None

    # Build reminder
    if task_summary:
        return f"{_NUDGE}\n\n当前任务：\n{task_summary}"
    return _NUDGE


def get_task_summary(project_slug: str, session_id: str | None = None, base_dir=None) -> str | None:
    """Return a formatted task list string for active tasks, or None.

    Filtering mirrors task_list_handler in builtin_tools.py:
    exclude _internal tasks, show only pending/in_progress.
    """
    from agent.tasks import list_tasks
    all_tasks = list_tasks(project_slug, session_id=session_id, base_dir=base_dir)
    active = [t for t in all_tasks
              if t.status.value in ("pending", "in_progress")
              and not t.metadata.get("_internal")]
    if not active:
        return None
    lines = [f"#{t.id} [{t.status.value}] {t.subject}" for t in active]
    return "\n".join(lines)
