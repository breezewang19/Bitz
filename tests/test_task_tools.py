"""Tests for task tools registered in builtin_tools (TaskCreate, TaskUpdate, TaskList, TaskGet)."""
import pytest
from pathlib import Path
from unittest.mock import patch

from agent.builtin_tools import create_tools
from agent.execution_context import ExecutionContext
from agent.tool_result import ToolResult
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
    """Return (ToolRegistry, slug, base_dir, context) with a patched task directory."""
    tools = create_tools()
    slug = "test-project"
    base_dir = tmp_path / ".bitz" / "tasks"
    session_id = "test-session"
    context = ExecutionContext(
        session_id=session_id,
        task_base_dir=str(base_dir),
    )
    tools.set_exec_context(context)
    with patch("agent.builtin_tools.get_project_slug", return_value=slug):
        yield tools, slug, base_dir, context, session_id


def _execute(tools, name, args, *, slug, context):
    """Helper to execute a tool with patched slug."""
    with patch("agent.builtin_tools.get_project_slug", return_value=slug):
        result = tools.execute(name, args, confirmed=True)
    return result


# ---------------------------------------------------------------------------
# TestTaskCreateTool
# ---------------------------------------------------------------------------


class TestTaskCreateTool:
    def test_create_task(self, tools_and_dir):
        tools, slug, base_dir, context, session_id = tools_and_dir
        result = _execute(tools, "task_create", {
            "subject": "Fix bug",
            "description": "Fix the login bug",
        }, slug=slug, context=context)
        assert isinstance(result, ToolResult)
        assert result.success
        assert "Task #1 created successfully" in result.data
        assert "Fix bug" in result.data
        # Verify persisted
        t = get_task(slug, "1", base_dir=base_dir, session_id=session_id)
        assert t is not None
        assert t.subject == "Fix bug"
        assert t.description == "Fix the login bug"

    def test_create_task_with_active_form(self, tools_and_dir):
        tools, slug, base_dir, context, session_id = tools_and_dir
        result = _execute(tools, "task_create", {
            "subject": "Run tests",
            "description": "Run all tests",
            "active_form": "Running tests",
        }, slug=slug, context=context)
        assert isinstance(result, ToolResult)
        assert result.success
        assert "Task #1 created successfully" in result.data
        t = get_task(slug, "1", base_dir=base_dir, session_id=session_id)
        assert t.activeForm == "Running tests"

    def test_create_task_with_metadata(self, tools_and_dir):
        tools, slug, base_dir, context, session_id = tools_and_dir
        result = _execute(tools, "task_create", {
            "subject": "Task",
            "description": "Desc",
            "metadata": {"priority": "high"},
        }, slug=slug, context=context)
        assert isinstance(result, ToolResult)
        assert result.success
        assert "Task #1 created successfully" in result.data
        t = get_task(slug, "1", base_dir=base_dir, session_id=session_id)
        assert t.metadata == {"priority": "high"}

    def test_create_task_missing_required_subject(self, tools_and_dir):
        tools, slug, base_dir, context, session_id = tools_and_dir
        result = _execute(tools, "task_create", {
            "description": "No subject",
        }, slug=slug, context=context)
        assert isinstance(result, ToolResult)
        assert not result.success

    def test_create_task_missing_required_description(self, tools_and_dir):
        tools, slug, base_dir, context, session_id = tools_and_dir
        result = _execute(tools, "task_create", {
            "subject": "No desc",
        }, slug=slug, context=context)
        assert isinstance(result, ToolResult)
        assert not result.success


# ---------------------------------------------------------------------------
# TestTaskListTool
# ---------------------------------------------------------------------------


class TestTaskListTool:
    def test_list_tasks(self, tools_and_dir):
        tools, slug, base_dir, context, session_id = tools_and_dir
        create_task(slug, "First", "Desc 1", base_dir=base_dir, session_id=session_id)
        create_task(slug, "Second", "Desc 2", base_dir=base_dir, session_id=session_id)
        result = _execute(tools, "task_list", {}, slug=slug, context=context)
        assert isinstance(result, ToolResult)
        assert result.success
        assert "#1" in result.data
        assert "#2" in result.data
        assert "First" in result.data
        assert "Second" in result.data

    def test_list_hides_internal_tasks(self, tools_and_dir):
        tools, slug, base_dir, context, session_id = tools_and_dir
        create_task(slug, "Internal", "Desc", metadata={"_internal": True}, base_dir=base_dir, session_id=session_id)
        create_task(slug, "External", "Desc", base_dir=base_dir, session_id=session_id)
        result = _execute(tools, "task_list", {}, slug=slug, context=context)
        assert isinstance(result, ToolResult)
        assert result.success
        assert "External" in result.data
        assert "Internal" not in result.data

    def test_list_shows_blocked_status(self, tools_and_dir):
        tools, slug, base_dir, context, session_id = tools_and_dir
        create_task(slug, "Blocker", "Desc", base_dir=base_dir, session_id=session_id)
        create_task(slug, "Blocked", "Desc", base_dir=base_dir, session_id=session_id)
        block_task(slug, "1", "2", base_dir=base_dir, session_id=session_id)
        result = _execute(tools, "task_list", {}, slug=slug, context=context)
        assert isinstance(result, ToolResult)
        assert result.success
        assert "blocked by" in result.data
        assert "#1" in result.data

    def test_list_empty(self, tools_and_dir):
        tools, slug, base_dir, context, session_id = tools_and_dir
        result = _execute(tools, "task_list", {}, slug=slug, context=context)
        assert isinstance(result, ToolResult)
        assert result.success
        assert "No tasks" in result.data


# ---------------------------------------------------------------------------
# TestTaskUpdateTool
# ---------------------------------------------------------------------------


class TestTaskUpdateTool:
    def test_update_status(self, tools_and_dir):
        tools, slug, base_dir, context, session_id = tools_and_dir
        create_task(slug, "Task", "Desc", base_dir=base_dir, session_id=session_id)
        result = _execute(tools, "task_update", {
            "task_id": "1",
            "status": "in_progress",
        }, slug=slug, context=context)
        assert isinstance(result, ToolResult)
        assert result.success
        assert "Updated task #1" in result.data
        assert "status" in result.data
        t = get_task(slug, "1", base_dir=base_dir, session_id=session_id)
        assert t.status == TaskStatus.IN_PROGRESS

    def test_delete_task_via_status(self, tools_and_dir):
        tools, slug, base_dir, context, session_id = tools_and_dir
        create_task(slug, "Task", "Desc", base_dir=base_dir, session_id=session_id)
        result = _execute(tools, "task_update", {
            "task_id": "1",
            "status": "deleted",
        }, slug=slug, context=context)
        assert isinstance(result, ToolResult)
        assert result.success
        # Task should be deleted
        t = get_task(slug, "1", base_dir=base_dir, session_id=session_id)
        assert t is None

    def test_update_add_blocks(self, tools_and_dir):
        tools, slug, base_dir, context, session_id = tools_and_dir
        create_task(slug, "Task 1", "Desc", base_dir=base_dir, session_id=session_id)
        create_task(slug, "Task 2", "Desc", base_dir=base_dir, session_id=session_id)
        result = _execute(tools, "task_update", {
            "task_id": "1",
            "add_blocks": ["2"],
        }, slug=slug, context=context)
        assert isinstance(result, ToolResult)
        assert result.success
        assert "Updated task #1" in result.data
        t1 = get_task(slug, "1", base_dir=base_dir, session_id=session_id)
        assert "2" in t1.blocks
        t2 = get_task(slug, "2", base_dir=base_dir, session_id=session_id)
        assert "1" in t2.blockedBy

    def test_update_add_blocked_by(self, tools_and_dir):
        tools, slug, base_dir, context, session_id = tools_and_dir
        create_task(slug, "Task 1", "Desc", base_dir=base_dir, session_id=session_id)
        create_task(slug, "Task 2", "Desc", base_dir=base_dir, session_id=session_id)
        result = _execute(tools, "task_update", {
            "task_id": "2",
            "add_blocked_by": ["1"],
        }, slug=slug, context=context)
        assert isinstance(result, ToolResult)
        assert result.success
        assert "Updated task #2" in result.data
        t2 = get_task(slug, "2", base_dir=base_dir, session_id=session_id)
        assert "1" in t2.blockedBy

    def test_update_not_found(self, tools_and_dir):
        tools, slug, base_dir, context, session_id = tools_and_dir
        result = _execute(tools, "task_update", {
            "task_id": "999",
            "subject": "Nope",
        }, slug=slug, context=context)
        assert isinstance(result, ToolResult)
        assert result.success  # "not found" is still a successful ToolResult.ok
        assert "not found" in result.data

    def test_update_metadata_merge(self, tools_and_dir):
        tools, slug, base_dir, context, session_id = tools_and_dir
        create_task(slug, "Task", "Desc", metadata={"a": 1, "b": 2}, base_dir=base_dir, session_id=session_id)
        result = _execute(tools, "task_update", {
            "task_id": "1",
            "metadata": {"b": 20, "c": 3},
        }, slug=slug, context=context)
        assert isinstance(result, ToolResult)
        assert result.success
        assert "Updated task #1" in result.data
        t = get_task(slug, "1", base_dir=base_dir, session_id=session_id)
        assert t.metadata == {"a": 1, "b": 20, "c": 3}

    def test_update_subject_and_description(self, tools_and_dir):
        tools, slug, base_dir, context, session_id = tools_and_dir
        create_task(slug, "Old", "Old desc", base_dir=base_dir, session_id=session_id)
        result = _execute(tools, "task_update", {
            "task_id": "1",
            "subject": "New",
            "description": "New desc",
        }, slug=slug, context=context)
        assert isinstance(result, ToolResult)
        assert result.success
        assert "Updated task #1" in result.data
        assert "subject" in result.data
        assert "description" in result.data
        t = get_task(slug, "1", base_dir=base_dir, session_id=session_id)
        assert t.subject == "New"
        assert t.description == "New desc"


# ---------------------------------------------------------------------------
# TestTaskGetTool
# ---------------------------------------------------------------------------


class TestTaskGetTool:
    def test_returns_details(self, tools_and_dir):
        tools, slug, base_dir, context, session_id = tools_and_dir
        create_task(slug, "Fix bug", "Fix the login bug", base_dir=base_dir, session_id=session_id)
        result = _execute(tools, "task_get", {"task_id": "1"}, slug=slug, context=context)
        assert isinstance(result, ToolResult)
        assert result.success
        assert "Task #1" in result.data
        assert "Fix bug" in result.data
        assert "Fix the login bug" in result.data
        assert "pending" in result.data

    def test_not_found(self, tools_and_dir):
        tools, slug, base_dir, context, session_id = tools_and_dir
        result = _execute(tools, "task_get", {"task_id": "999"}, slug=slug, context=context)
        assert isinstance(result, ToolResult)
        assert result.success  # "not found" is ToolResult.ok
        assert "not found" in result.data

    def test_shows_dependencies(self, tools_and_dir):
        tools, slug, base_dir, context, session_id = tools_and_dir
        create_task(slug, "Blocker", "Desc", base_dir=base_dir, session_id=session_id)
        create_task(slug, "Blocked", "Desc", base_dir=base_dir, session_id=session_id)
        block_task(slug, "1", "2", base_dir=base_dir, session_id=session_id)
        result = _execute(tools, "task_get", {"task_id": "2"}, slug=slug, context=context)
        assert isinstance(result, ToolResult)
        assert result.success
        assert "Blocked by" in result.data
        assert "#1" in result.data
        # Also check the blocker task shows "Blocks"
        result2 = _execute(tools, "task_get", {"task_id": "1"}, slug=slug, context=context)
        assert isinstance(result2, ToolResult)
        assert result2.success
        assert "Blocks" in result2.data
        assert "#2" in result2.data

    def test_shows_active_form(self, tools_and_dir):
        tools, slug, base_dir, context, session_id = tools_and_dir
        create_task(slug, "Task", "Desc", active_form="Working", base_dir=base_dir, session_id=session_id)
        result = _execute(tools, "task_get", {"task_id": "1"}, slug=slug, context=context)
        assert isinstance(result, ToolResult)
        assert result.success
        assert "Active form" in result.data
        assert "Working" in result.data

    def test_can_get_internal_task(self, tools_and_dir):
        tools, slug, base_dir, context, session_id = tools_and_dir
        create_task(slug, "Internal", "Desc", metadata={"_internal": True}, base_dir=base_dir, session_id=session_id)
        result = _execute(tools, "task_get", {"task_id": "1"}, slug=slug, context=context)
        assert isinstance(result, ToolResult)
        assert result.success
        # task_get should be able to retrieve internal tasks
        assert "Task #1" in result.data
        assert "Internal" in result.data


# ---------------------------------------------------------------------------
# TestTaskToolDescriptions
# ---------------------------------------------------------------------------


class TestTaskToolDescriptions:
    def test_task_create_description_has_when_to_use(self):
        tools = create_tools()
        desc = tools.tools["task_create"].description
        assert "何时使用" in desc
        assert "何时不使用" in desc
        assert "字段" in desc
        assert "提示" in desc

    def test_task_update_description_has_completion_conditions(self):
        tools = create_tools()
        desc = tools.tools["task_update"].description
        assert "何时使用" in desc
        assert "完成条件" in desc
        assert "可更新字段" in desc
        assert "示例" in desc

    def test_task_list_description_has_output(self):
        tools = create_tools()
        desc = tools.tools["task_list"].description
        assert "何时使用" in desc
        assert "输出" in desc

    def test_task_get_description_has_tips(self):
        tools = create_tools()
        desc = tools.tools["task_get"].description
        assert "何时使用" in desc
        assert "提示" in desc
