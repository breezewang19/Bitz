# tests/test_loop.py
"""Agent Loop 测试"""
import pytest
from unittest.mock import MagicMock
from agent.loop import Agent
from agent.context import Context
from agent.adapter import LLMResponse


def test_agent_init():
    """测试 Agent 初始化"""
    mock_adapter = MagicMock()
    mock_tools = MagicMock()
    ctx = Context(system_prompt="You are helpful.")

    agent = Agent(
        llm_adapter=mock_adapter,
        tools=mock_tools,
        context=ctx,
        max_steps=5
    )

    assert agent.llm_adapter is mock_adapter
    assert agent.tools is mock_tools
    assert agent.context is ctx
    assert agent.max_steps == 5


def test_agent_run_text_response():
    """测试 Agent 处理文本回复"""
    mock_adapter = MagicMock()
    mock_adapter.chat.return_value = LLMResponse(
        content="Hello, how can I help?",
        stop_reason="end_turn"
    )
    mock_tools = MagicMock()
    ctx = Context(system_prompt="You are helpful.")

    agent = Agent(
        llm_adapter=mock_adapter,
        tools=mock_tools,
        context=ctx,
        max_steps=5
    )

    result = agent.run("What can you do?")
    assert result == "Hello, how can I help?"

    # Check that user message was added to context
    assert len(ctx.messages) == 1
    assert ctx.messages[0]["role"] == "user"
    assert ctx.messages[0]["content"] == "What can you do?"

    # Check that chat was called with correct messages
    mock_adapter.chat.assert_called_once()
    call_args = mock_adapter.chat.call_args
    msgs = call_args[0][0]
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == "You are helpful."
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "What can you do?"


def test_agent_run_tool_call():
    """测试 Agent 处理工具调用"""
    mock_adapter = MagicMock()
    mock_tools = MagicMock()

    # First call returns tool_use, second returns end_turn
    mock_adapter.chat.side_effect = [
        LLMResponse(
            content=[{
                "type": "tool_use",
                "id": "toolu_01",
                "name": "echo",
                "input": {"x": "hello"}
            }],
            stop_reason="tool_use"
        ),
        LLMResponse(
            content="Tool returned: hello",
            stop_reason="end_turn"
        )
    ]

    mock_tools.execute.return_value = "hello"

    ctx = Context(system_prompt="You are helpful.")

    agent = Agent(
        llm_adapter=mock_adapter,
        tools=mock_tools,
        context=ctx,
        max_steps=5
    )

    result = agent.run("Echo back hello")
    assert result == "Tool returned: hello"

    # Check tool was executed
    mock_tools.execute.assert_called_once_with("echo", {"x": "hello"})

    # Check context has user message and tool result
    assert len(ctx.messages) == 2
    assert ctx.messages[0]["role"] == "user"
    assert ctx.messages[1]["role"] == "user"
    assert ctx.messages[1]["tool_use_id"] == "toolu_01"
    assert ctx.messages[1]["content"] == "hello"


def test_agent_run_max_steps_exceeded():
    """测试超过最大步数"""
    mock_adapter = MagicMock()
    mock_adapter.chat.return_value = LLMResponse(
        content=[{"type": "tool_use", "id": "t1", "name": "echo", "input": {}}],
        stop_reason="tool_use"
    )
    mock_tools = MagicMock()
    mock_tools.execute.return_value = "result"

    ctx = Context(system_prompt="You are helpful.")

    agent = Agent(
        llm_adapter=mock_adapter,
        tools=mock_tools,
        context=ctx,
        max_steps=2
    )

    result = agent.run("Do something")
    assert "Error" in result
    assert "max_steps" in result.lower()


def test_agent_run_multiple_tool_calls():
    """测试多次工具调用"""
    mock_adapter = MagicMock()
    mock_adapter.chat.side_effect = [
        LLMResponse(
            content=[{"type": "tool_use", "id": "t1", "name": "echo", "input": {"x": 1}}],
            stop_reason="tool_use"
        ),
        LLMResponse(
            content=[{"type": "tool_use", "id": "t2", "name": "echo", "input": {"x": 2}}],
            stop_reason="tool_use"
        ),
        LLMResponse(content="Final result", stop_reason="end_turn")
    ]
    mock_tools = MagicMock()
    mock_tools.execute.return_value = "done"

    ctx = Context(system_prompt="You are helpful.")

    agent = Agent(
        llm_adapter=mock_adapter,
        tools=mock_tools,
        context=ctx,
        max_steps=5
    )

    result = agent.run("Do multiple things")
    assert result == "Final result"
    assert mock_adapter.chat.call_count == 3
    assert mock_tools.execute.call_count == 2
