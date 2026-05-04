"""Tests for task tools registered in builtin_tools (TaskCreate, TaskUpdate, TaskList, TaskGet)."""
import pytest
from pathlib import Path
from unittest.mock import patch

from agent.builtin_tools import create_tools
from agent.tasks import (
    Task,
    TaskStatus,
    create_task,
    get_task,
    list_tasks,
    update_task,
    delete_task,
    block_task,
    is_blocked,
    _get_tasks_dir,
)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def tools_and_dir(tmp_path):
    """Return (ToolRegistry, slug, base_dir) with a patched task directory."""
    tools = create_tools()
    slug = "test-project"
    base_dir = tmp_path / ".bitz" / "tasks"
    with patch("agent.builtin_tools.get_project_slug", return_value=slug), \
         patch("agent.builtin_tools._TASK_BASE_DIR", base_dir):
        yield tools, slug, base_dir


def _execute(tools, name, args, *, slug, base_dir):
    """Helper to execute a tool with patched slug/base_dir."""
    with patch("agent.builtin_tools.get_project_slug", return_value=slug), \
         patch("agent.builtin_tools._TASK_BASE_DIR", base_dir):
        return tools.execute(name, args, confirmed=True)


# ---------------------------------------------------------------------------
# TestTaskCreateTool
# ---------------------------------------------------------------------------


class TestTaskCreateTool:
    def test_create_task(self, tools_and_dir):
        tools, slug, base_dir = tools_and_dir
        result = _execute(tools, "task_create", {
            "subject": "Fix bug",
            "description": "Fix the login bug",
        }, slug=slug, base_dir=base_dir)
        assert "Task #1 created successfully" in result
        assert "Fix bug" in result
        # Verify persisted
        t = get_task(slug, "1", base_dir=base_dir)
        assert t is not None
        assert t.subject == "Fix bug"
        assert t.description == "Fix the login bug"

    def test_create_task_with_active_form(self, tools_and_dir):
        tools, slug, base_dir = tools_and_dir
        result = _execute(tools, "task_create", {
            "subject": "Run tests",
            "description": "Run all tests",
            "active_form": "Running tests",
        }, slug=slug, base_dir=base_dir)
        assert "Task #1 created successfully" in result
        t = get_task(slug, "1", base_dir=base_dir)
        assert t.activeForm == "Running tests"

    def test_create_task_with_metadata(self, tools_and_dir):
        tools, slug, base_dir = tools_and_dir
        result = _execute(tools, "task_create", {
            "subject": "Task",
            "description": "Desc",
            "metadata": {"priority": "high"},
        }, slug=slug, base_dir=base_dir)
        assert "Task #1 created successfully" in result
        t = get_task(slug, "1", base_dir=base_dir)
        assert t.metadata == {"priority": "high"}

    def test_create_task_missing_required_subject(self, tools_and_dir):
        tools, slug, base_dir = tools_and_dir
        # The tool handler receives keyword args; missing required args
        # will cause a TypeError which execute() catches
        result = _execute(tools, "task_create", {
            "description": "No subject",
        }, slug=slug, base_dir=base_dir)
        assert "Error" in result

    def test_create_task_missing_required_description(self, tools_and_dir):
        tools, slug, base_dir = tools_and_dir
        result = _execute(tools, "task_create", {
            "subject": "No desc",
        }, slug=slug, base_dir=base_dir)
        assert "Error" in result


# ---------------------------------------------------------------------------
# TestTaskListTool
# ---------------------------------------------------------------------------


class TestTaskListTool:
    def test_list_tasks(self, tools_and_dir):
        tools, slug, base_dir = tools_and_dir
        create_task(slug, "First", "Desc 1", base_dir=base_dir)
        create_task(slug, "Second", "Desc 2", base_dir=base_dir)
        result = _execute(tools, "task_list", {}, slug=slug, base_dir=base_dir)
        assert "#1" in result
        assert "#2" in result
        assert "First" in result
        assert "Second" in result

    def test_list_hides_internal_tasks(self, tools_and_dir):
        tools, slug, base_dir = tools_and_dir
        create_task(slug, "Internal", "Desc", metadata={"_internal": True}, base_dir=base_dir)
        create_task(slug, "External", "Desc", base_dir=base_dir)
        result = _execute(tools, "task_list", {}, slug=slug, base_dir=base_dir)
        assert "External" in result
        assert "Internal" not in result

    def test_list_shows_blocked_status(self, tools_and_dir):
        tools, slug, base_dir = tools_and_dir
        create_task(slug, "Blocker", "Desc", base_dir=base_dir)
        create_task(slug, "Blocked", "Desc", base_dir=base_dir)
        block_task(slug, "1", "2", base_dir=base_dir)
        result = _execute(tools, "task_list", {}, slug=slug, base_dir=base_dir)
        assert "blocked by" in result
        assert "#1" in result

    def test_list_empty(self, tools_and_dir):
        tools, slug, base_dir = tools_and_dir
        result = _execute(tools, "task_list", {}, slug=slug, base_dir=base_dir)
        assert "No tasks" in result


# ---------------------------------------------------------------------------
# TestTaskUpdateTool
# ---------------------------------------------------------------------------


class TestTaskUpdateTool:
    def test_update_status(self, tools_and_dir):
        tools, slug, base_dir = tools_and_dir
        create_task(slug, "Task", "Desc", base_dir=base_dir)
        result = _execute(tools, "task_update", {
            "task_id": "1",
            "status": "in_progress",
        }, slug=slug, base_dir=base_dir)
        assert "Updated task #1" in result
        assert "status" in result
        t = get_task(slug, "1", base_dir=base_dir)
        assert t.status == TaskStatus.IN_PROGRESS

    def test_delete_task_via_status(self, tools_and_dir):
        tools, slug, base_dir = tools_and_dir
        create_task(slug, "Task", "Desc", base_dir=base_dir)
        result = _execute(tools, "task_update", {
            "task_id": "1",
            "status": "deleted",
        }, slug=slug, base_dir=base_dir)
        # Task should be deleted
        t = get_task(slug, "1", base_dir=base_dir)
        assert t is None

    def test_update_add_blocks(self, tools_and_dir):
        tools, slug, base_dir = tools_and_dir
        create_task(slug, "Task 1", "Desc", base_dir=base_dir)
        create_task(slug, "Task 2", "Desc", base_dir=base_dir)
        result = _execute(tools, "task_update", {
            "task_id": "1",
            "add_blocks": ["2"],
        }, slug=slug, base_dir=base_dir)
        assert "Updated task #1" in result
        t1 = get_task(slug, "1", base_dir=base_dir)
        assert "2" in t1.blocks
        t2 = get_task(slug, "2", base_dir=base_dir)
        assert "1" in t2.blockedBy

    def test_update_add_blocked_by(self, tools_and_dir):
        tools, slug, base_dir = tools_and_dir
        create_task(slug, "Task 1", "Desc", base_dir=base_dir)
        create_task(slug, "Task 2", "Desc", base_dir=base_dir)
        result = _execute(tools, "task_update", {
            "task_id": "2",
            "add_blocked_by": ["1"],
        }, slug=slug, base_dir=base_dir)
        assert "Updated task #2" in result
        t2 = get_task(slug, "2", base_dir=base_dir)
        assert "1" in t2.blockedBy

    def test_update_not_found(self, tools_and_dir):
        tools, slug, base_dir = tools_and_dir
        result = _execute(tools, "task_update", {
            "task_id": "999",
            "subject": "Nope",
        }, slug=slug, base_dir=base_dir)
        assert "not found" in result

    def test_update_metadata_merge(self, tools_and_dir):
        tools, slug, base_dir = tools_and_dir
        create_task(slug, "Task", "Desc", metadata={"a": 1, "b": 2}, base_dir=base_dir)
        result = _execute(tools, "task_update", {
            "task_id": "1",
            "metadata": {"b": 20, "c": 3},
        }, slug=slug, base_dir=base_dir)
        assert "Updated task #1" in result
        t = get_task(slug, "1", base_dir=base_dir)
        assert t.metadata == {"a": 1, "b": 20, "c": 3}

    def test_update_subject_and_description(self, tools_and_dir):
        tools, slug, base_dir = tools_and_dir
        create_task(slug, "Old", "Old desc", base_dir=base_dir)
        result = _execute(tools, "task_update", {
            "task_id": "1",
            "subject": "New",
            "description": "New desc",
        }, slug=slug, base_dir=base_dir)
        assert "Updated task #1" in result
        assert "subject" in result
        assert "description" in result
        t = get_task(slug, "1", base_dir=base_dir)
        assert t.subject == "New"
        assert t.description == "New desc"


# ---------------------------------------------------------------------------
# TestTaskGetTool
# ---------------------------------------------------------------------------


class TestTaskGetTool:
    def test_returns_details(self, tools_and_dir):
        tools, slug, base_dir = tools_and_dir
        create_task(slug, "Fix bug", "Fix the login bug", base_dir=base_dir)
        result = _execute(tools, "task_get", {"task_id": "1"}, slug=slug, base_dir=base_dir)
        assert "Task #1" in result
        assert "Fix bug" in result
        assert "Fix the login bug" in result
        assert "pending" in result

    def test_not_found(self, tools_and_dir):
        tools, slug, base_dir = tools_and_dir
        result = _execute(tools, "task_get", {"task_id": "999"}, slug=slug, base_dir=base_dir)
        assert "not found" in result

    def test_shows_dependencies(self, tools_and_dir):
        tools, slug, base_dir = tools_and_dir
        create_task(slug, "Blocker", "Desc", base_dir=base_dir)
        create_task(slug, "Blocked", "Desc", base_dir=base_dir)
        block_task(slug, "1", "2", base_dir=base_dir)
        result = _execute(tools, "task_get", {"task_id": "2"}, slug=slug, base_dir=base_dir)
        assert "Blocked by" in result
        assert "#1" in result
        # Also check the blocker task shows "Blocks"
        result2 = _execute(tools, "task_get", {"task_id": "1"}, slug=slug, base_dir=base_dir)
        assert "Blocks" in result2
        assert "#2" in result2

    def test_shows_active_form(self, tools_and_dir):
        tools, slug, base_dir = tools_and_dir
        create_task(slug, "Task", "Desc", active_form="Working", base_dir=base_dir)
        result = _execute(tools, "task_get", {"task_id": "1"}, slug=slug, base_dir=base_dir)
        assert "Active form" in result
        assert "Working" in result

    def test_can_get_internal_task(self, tools_and_dir):
        tools, slug, base_dir = tools_and_dir
        create_task(slug, "Internal", "Desc", metadata={"_internal": True}, base_dir=base_dir)
        result = _execute(tools, "task_get", {"task_id": "1"}, slug=slug, base_dir=base_dir)
        # task_get should be able to retrieve internal tasks
        assert "Task #1" in result
        assert "Internal" in result
