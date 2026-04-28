# tests/test_loop.py
"""Agent Loop 测试"""
import pytest
from unittest.mock import MagicMock
from agent.loop import Agent
from agent.context import Context
from agent.adapter import LLMResponse, StreamEvent


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
    mock_adapter.stream_chat.return_value = iter([
        StreamEvent(type="text_delta", content="Hello, how can I help?"),
        StreamEvent(type="stop", stop_reason="end_turn"),
    ])
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

    # Check that user + assistant messages were added to context
    assert len(ctx.messages) == 2
    assert ctx.messages[0]["role"] == "user"
    assert ctx.messages[0]["content"] == "What can you do?"
    assert ctx.messages[1]["role"] == "assistant"
    assert ctx.messages[1]["content"] == "Hello, how can I help?"

    # Check that stream_chat was called with correct messages
    mock_adapter.stream_chat.assert_called_once()
    call_args = mock_adapter.stream_chat.call_args
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
    mock_adapter.stream_chat.side_effect = [
        iter([
            StreamEvent(type="tool_use", tool_id="toolu_01", tool_name="echo", tool_input={"x": "hello"}),
            StreamEvent(type="stop", stop_reason="tool_use"),
        ]),
        iter([
            StreamEvent(type="text_delta", content="Tool returned: hello"),
            StreamEvent(type="stop", stop_reason="end_turn"),
        ])
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
    mock_tools.execute.assert_called_once_with("echo", {"x": "hello"}, confirmed=False, tool_id="toolu_01")

    # Check context: user, assistant tool_use, tool result, assistant end_turn
    assert len(ctx.messages) == 4
    assert ctx.messages[0]["role"] == "user"
    assert ctx.messages[0]["content"] == "Echo back hello"
    # Assistant tool_use message
    assert ctx.messages[1]["role"] == "assistant"
    assert ctx.messages[1]["content"][0]["type"] == "tool_use"
    assert ctx.messages[1]["content"][0]["id"] == "toolu_01"
    # User tool result
    assert ctx.messages[2]["role"] == "user"
    assert ctx.messages[2]["content"][0]["tool_use_id"] == "toolu_01"
    assert ctx.messages[2]["content"][0]["content"] == "hello"
    # Assistant end_turn response
    assert ctx.messages[3]["role"] == "assistant"
    assert ctx.messages[3]["content"] == "Tool returned: hello"


def test_agent_run_max_steps_exceeded():
    """测试超过最大步数"""
    mock_adapter = MagicMock()
    mock_adapter.stream_chat.return_value = iter([
        StreamEvent(type="tool_use", tool_id="t1", tool_name="echo", tool_input={}),
        StreamEvent(type="stop", stop_reason="tool_use"),
    ])
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


def test_agent_run_max_tokens_stop_reason():
    """测试 max_tokens stop_reason 会自动续写"""
    mock_adapter = MagicMock()
    mock_adapter.stream_chat.side_effect = [
        iter([
            StreamEvent(type="text_delta", content="这是一段被截断的回复"),
            StreamEvent(type="stop", stop_reason="max_tokens"),
        ]),
        iter([
            StreamEvent(type="text_delta", content="续写内容"),
            StreamEvent(type="stop", stop_reason="end_turn"),
        ]),
    ]
    mock_tools = MagicMock()
    ctx = Context(system_prompt="You are helpful.")

    agent = Agent(
        llm_adapter=mock_adapter,
        tools=mock_tools,
        context=ctx,
        max_steps=5
    )

    result = agent.run("写一篇长文")
    # 应该续写完成，返回最终内容
    assert result == "续写内容"
    # 调用了两次 LLM：第一次 max_tokens，第二次 end_turn
    assert mock_adapter.stream_chat.call_count == 2
    # 上下文包含：user输入 + assistant部分 + user续写提示 + assistant续写
    assert ctx.messages[0]["role"] == "user"
    assert ctx.messages[1]["role"] == "assistant"
    assert ctx.messages[1]["content"] == "这是一段被截断的回复"
    assert ctx.messages[2]["role"] == "user"
    assert "继续" in ctx.messages[2]["content"]


def test_agent_run_multiple_tool_calls():
    """测试多次工具调用"""
    mock_adapter = MagicMock()
    mock_adapter.stream_chat.side_effect = [
        iter([
            StreamEvent(type="tool_use", tool_id="t1", tool_name="echo", tool_input={"x": 1}),
            StreamEvent(type="stop", stop_reason="tool_use"),
        ]),
        iter([
            StreamEvent(type="tool_use", tool_id="t2", tool_name="echo", tool_input={"x": 2}),
            StreamEvent(type="stop", stop_reason="tool_use"),
        ]),
        iter([
            StreamEvent(type="text_delta", content="Final result"),
            StreamEvent(type="stop", stop_reason="end_turn"),
        ])
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
    assert mock_adapter.stream_chat.call_count == 3
    assert mock_tools.execute.call_count == 2


def test_agent_confirm_pending_with_confirmed_results():
    """测试混合确认场景：部分工具已确认，部分需要确认"""
    mock_adapter = MagicMock()
    mock_tools = MagicMock()

    # LLM 返回两个 tool_use：echo 不需要确认，bash 需要确认
    def execute_side_effect(name, args, confirmed=False, tool_id=""):
        if name == "echo":
            return "echo result"
        if name == "bash":
            if confirmed:
                return "bash confirmed result"
            return "[CONFIRM_REQUIRED] bash needs confirmation"

    mock_tools.execute.side_effect = execute_side_effect
    mock_tools.list_for_llm.return_value = []

    # 第一步：LLM 返回两个 tool_use
    mock_adapter.stream_chat.return_value = iter([
        StreamEvent(type="tool_use", tool_id="t1", tool_name="echo", tool_input={"x": 1}),
        StreamEvent(type="tool_use", tool_id="t2", tool_name="bash", tool_input={"cmd": "rm -rf /"}),
        StreamEvent(type="stop", stop_reason="tool_use"),
    ])

    ctx = Context(system_prompt="You are helpful.")
    agent = Agent(
        llm_adapter=mock_adapter,
        tools=mock_tools,
        context=ctx,
        max_steps=5
    )

    result = agent.run("Run echo and bash")
    assert "[CONFIRM_REQUIRED]" in result

    # 确认 bash 工具
    confirmed_tools = set()
    should_continue, confirm_result = agent.confirm_pending(confirmed_tools)
    assert should_continue is True
    assert confirm_result == "bash confirmed result"

    # 验证上下文：两个 tool_result 都写入了
    # messages: user, assistant(tool_use x2), user(tool_result x2)
    assert len(ctx.messages) == 3
    tool_result_msg = ctx.messages[2]
    assert tool_result_msg["role"] == "user"
    assert len(tool_result_msg["content"]) == 2
    tool_ids = [b["tool_use_id"] for b in tool_result_msg["content"]]
    assert "t1" in tool_ids
    assert "t2" in tool_ids


def test_agent_run_stream_text_response():
    """测试 Agent 流式处理文本回复"""
    mock_adapter = MagicMock()
    mock_adapter.stream_chat.return_value = iter([
        StreamEvent(type="text_delta", content="Hello"),
        StreamEvent(type="text_delta", content=" there"),
        StreamEvent(type="stop", stop_reason="end_turn"),
    ])
    mock_tools = MagicMock()
    ctx = Context(system_prompt="You are helpful.")

    text_deltas = []
    def on_delta(text):
        text_deltas.append(text)

    agent = Agent(
        llm_adapter=mock_adapter,
        tools=mock_tools,
        context=ctx,
        max_steps=5
    )

    result = agent.run("Hi", on_text_delta=on_delta)
    assert result == "Hello there"
    assert text_deltas == ["Hello", " there"]


def test_agent_run_stream_tool_call():
    """测试 Agent 流式处理工具调用"""
    mock_adapter = MagicMock()
    mock_adapter.stream_chat.side_effect = [
        iter([
            StreamEvent(type="tool_use", tool_id="t1", tool_name="echo", tool_input={"x": "hi"}),
            StreamEvent(type="stop", stop_reason="tool_use"),
        ]),
        # 第二轮
        iter([
            StreamEvent(type="text_delta", content="Done"),
            StreamEvent(type="stop", stop_reason="end_turn"),
        ]),
    ]
    mock_tools = MagicMock()
    mock_tools.execute.return_value = "echo result"
    ctx = Context(system_prompt="You are helpful.")

    agent = Agent(
        llm_adapter=mock_adapter,
        tools=mock_tools,
        context=ctx,
        max_steps=5
    )

    result = agent.run("Echo hi")
    assert result == "Done"
