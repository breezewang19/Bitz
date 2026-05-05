"""Tests for system prompt assembly."""
from agent.prompt import RULES


def test_rules_contains_task_tool_guidance():
    """RULES should mention task_create and task_update."""
    assert "task_create" in RULES
    assert "task_update" in RULES
    assert "in_progress" in RULES
    assert "completed" in RULES
