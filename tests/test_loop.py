# tests/test_loop.py
import pytest
from unittest.mock import MagicMock, patch
from agent.loop import Agent
from agent.context import Context
from agent.tools import ToolRegistry
from agent.tool_result import ToolResult


def _make_agent(tools=None, max_steps=5):
    llm = MagicMock()
    ctx = Context(session_id="test-session")
    if tools is None:
        tools = ToolRegistry()
    return Agent(llm, tools, ctx, max_steps=max_steps)


def test_agent_init():
    agent = _make_agent()
    assert agent.max_steps == 5
    assert agent.context.session_id == "test-session"
    assert agent._exec_context is not None
    assert agent._exec_context.session_id == "test-session"


def test_agent_step_count():
    agent = _make_agent()
    assert agent._step_count == 0


def test_agent_execute_tool_returns_toolresult():
    """Test that tool execution returns ToolResult."""
    tools = ToolRegistry()
    tools.register(
        name="echo",
        description="Echo",
        input_schema={"type": "object", "properties": {"x": {"type": "string"}}},
        handler=lambda args, context: ToolResult.ok(args.get("x", ""))
    )
    agent = _make_agent(tools=tools)
    result = agent.tools.execute("echo", {"x": "hi"})
    assert isinstance(result, ToolResult)
    assert result.success
    assert result.data == "hi"


def test_agent_execute_unknown_tool():
    """Test that executing unknown tool returns ToolResult.error()."""
    agent = _make_agent()
    result = agent.tools.execute("nonexistent", {})
    assert isinstance(result, ToolResult)
    assert not result.success
    assert "Unknown tool" in result.error_message
