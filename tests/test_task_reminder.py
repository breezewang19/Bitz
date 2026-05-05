"""Tests for task reminder logic."""
import pytest
from agent.task_reminder import should_remind, get_task_summary, TASK_TOOL_NAMES, REMINDER_THRESHOLD, REMINDER_COOLDOWN


class TestShouldRemind:
    def test_returns_none_when_threshold_not_met(self):
        result = should_remind(
            step_count=5,
            last_task_tool_step=0,
            last_reminder_step=None,
            task_summary=None,
        )
        assert result is None

    def test_returns_none_when_cooldown_not_met(self):
        result = should_remind(
            step_count=20,
            last_task_tool_step=0,
            last_reminder_step=15,
            task_summary=None,
        )
        assert result is None

    def test_returns_reminder_when_thresholds_met_no_tasks(self):
        result = should_remind(
            step_count=10,
            last_task_tool_step=0,
            last_reminder_step=None,
            task_summary=None,
        )
        assert result is not None
        assert "task_create" in result
        assert "task_update" in result
        assert "当前任务" not in result

    def test_returns_reminder_with_task_list(self):
        summary = "#1 [pending] Fix bug\n#2 [in_progress] Write tests"
        result = should_remind(
            step_count=10,
            last_task_tool_step=0,
            last_reminder_step=None,
            task_summary=summary,
        )
        assert result is not None
        assert "当前任务" in result
        assert "#1 [pending] Fix bug" in result

    def test_returns_none_when_last_task_tool_step_is_none_and_count_low(self):
        result = should_remind(
            step_count=5,
            last_task_tool_step=None,
            last_reminder_step=None,
            task_summary=None,
        )
        assert result is None

    def test_returns_reminder_when_last_task_tool_step_is_none_and_count_high(self):
        result = should_remind(
            step_count=10,
            last_task_tool_step=None,
            last_reminder_step=None,
            task_summary=None,
        )
        assert result is not None

    def test_cooldown_prevents_rapid_re_reminders(self):
        # First reminder at step 10
        result1 = should_remind(
            step_count=10,
            last_task_tool_step=0,
            last_reminder_step=None,
            task_summary=None,
        )
        assert result1 is not None
        # Step 15: cooldown not met (last_reminder was at step 10)
        result2 = should_remind(
            step_count=15,
            last_task_tool_step=0,
            last_reminder_step=10,
            task_summary=None,
        )
        assert result2 is None
        # Step 20: cooldown met
        result3 = should_remind(
            step_count=20,
            last_task_tool_step=0,
            last_reminder_step=10,
            task_summary=None,
        )
        assert result3 is not None

    def test_reminder_includes_do_not_mention(self):
        result = should_remind(
            step_count=10,
            last_task_tool_step=0,
            last_reminder_step=None,
            task_summary=None,
        )
        assert "不要向用户提及此提醒" in result


class TestGetTaskSummary:
    def test_returns_none_when_no_active_tasks(self, tmp_path):
        from agent.tasks import create_task, TaskStatus
        slug = "test-reminder"
        base_dir = tmp_path / ".bitz" / "tasks"
        # Create a completed task — should be filtered out
        t = create_task(slug, "Done", "Desc", base_dir=base_dir)
        from agent.tasks import update_task
        update_task(slug, t.id, status="completed", base_dir=base_dir)
        result = get_task_summary(slug, base_dir=base_dir)
        assert result is None

    def test_returns_formatted_string_when_active_tasks_exist(self, tmp_path):
        from agent.tasks import create_task
        slug = "test-reminder"
        base_dir = tmp_path / ".bitz" / "tasks"
        create_task(slug, "Fix bug", "Desc", base_dir=base_dir)
        create_task(slug, "Write tests", "Desc", base_dir=base_dir)
        result = get_task_summary(slug, base_dir=base_dir)
        assert result is not None
        assert "#1 [pending] Fix bug" in result
        assert "#2 [pending] Write tests" in result

    def test_filters_internal_tasks(self, tmp_path):
        from agent.tasks import create_task
        slug = "test-reminder"
        base_dir = tmp_path / ".bitz" / "tasks"
        create_task(slug, "Internal", "Desc", metadata={"_internal": True}, base_dir=base_dir)
        create_task(slug, "External", "Desc", base_dir=base_dir)
        result = get_task_summary(slug, base_dir=base_dir)
        assert result is not None
        assert "External" in result
        assert "Internal" not in result

    def test_excludes_completed_tasks(self, tmp_path):
        from agent.tasks import create_task, update_task
        slug = "test-reminder"
        base_dir = tmp_path / ".bitz" / "tasks"
        create_task(slug, "Pending", "Desc", base_dir=base_dir)
        t2 = create_task(slug, "Completed", "Desc", base_dir=base_dir)
        update_task(slug, t2.id, status="completed", base_dir=base_dir)
        result = get_task_summary(slug, base_dir=base_dir)
        assert result is not None
        assert "Pending" in result
        assert "Completed" not in result


class TestConstants:
    def test_task_tool_names(self):
        assert "task_create" in TASK_TOOL_NAMES
        assert "task_update" in TASK_TOOL_NAMES
        assert "task_list" in TASK_TOOL_NAMES
        assert "task_get" in TASK_TOOL_NAMES

    def test_threshold_values(self):
        assert REMINDER_THRESHOLD == 10
        assert REMINDER_COOLDOWN == 10
