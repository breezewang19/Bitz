# tests/test_loop.py
"""Agent Loop 测试"""
import time
import threading
from unittest.mock import MagicMock

from agent.loop import Agent
from agent.context import Context
from agent.adapter import LLMResponse
from agent.tools import ToolRegistry


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
        content="Hello, how can I help?", stop_reason="end_turn"
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

    assert len(ctx.messages) == 2
    assert ctx.messages[0]["role"] == "user"
    assert ctx.messages[0]["content"] == "What can you do?"
    assert ctx.messages[1]["role"] == "assistant"
    assert ctx.messages[1]["content"] == "Hello, how can I help?"


def test_agent_run_tool_call():
    """测试 Agent 处理工具调用"""
    mock_adapter = MagicMock()
    mock_tools = MagicMock()

    mock_adapter.chat.side_effect = [
        LLMResponse(
            content=[{"type": "tool_use", "id": "toolu_01", "name": "echo", "input": {"x": "hello"}}],
            stop_reason="tool_use",
        ),
        LLMResponse(content="Tool returned: hello", stop_reason="end_turn"),
    ]

    mock_tools.execute.return_value = "hello"

    ctx = Context(system_prompt="You are helpful.")
    agent = Agent(llm_adapter=mock_adapter, tools=mock_tools, context=ctx, max_steps=5)

    result = agent.run("Echo back hello")
    assert result == "Tool returned: hello"

    mock_tools.execute.assert_called_once_with("echo", {"x": "hello"}, confirmed=False, tool_id="toolu_01", agent=agent, on_event=None)

    assert len(ctx.messages) == 4
    assert ctx.messages[0]["role"] == "user"
    assert ctx.messages[1]["role"] == "assistant"
    assert ctx.messages[1]["content"][0]["type"] == "tool_use"
    assert ctx.messages[2]["role"] == "user"
    assert ctx.messages[2]["content"][0]["tool_use_id"] == "toolu_01"
    assert ctx.messages[3]["role"] == "assistant"
    assert ctx.messages[3]["content"] == "Tool returned: hello"


def test_agent_run_max_steps_exceeded():
    """测试超过最大步数"""
    mock_adapter = MagicMock()
    mock_adapter.chat.return_value = LLMResponse(
        content=[{"type": "tool_use", "id": "t1", "name": "echo", "input": {}}],
        stop_reason="tool_use",
    )
    mock_tools = MagicMock()
    mock_tools.execute.return_value = "result"

    ctx = Context(system_prompt="You are helpful.")
    agent = Agent(llm_adapter=mock_adapter, tools=mock_tools, context=ctx, max_steps=2)

    result = agent.run("Do something")
    assert "Error" in result
    assert "max_steps" in result.lower()


def test_agent_run_max_tokens_stop_reason():
    """测试 max_tokens stop_reason 会自动续写"""
    mock_adapter = MagicMock()
    mock_adapter.chat.side_effect = [
        LLMResponse(content="这是一段被截断的回复", stop_reason="max_tokens"),
        LLMResponse(content="续写内容", stop_reason="end_turn"),
    ]
    mock_tools = MagicMock()
    ctx = Context(system_prompt="You are helpful.")
    agent = Agent(llm_adapter=mock_adapter, tools=mock_tools, context=ctx, max_steps=5)

    result = agent.run("写一篇长文")
    assert result == "续写内容"
    assert mock_adapter.chat.call_count == 2
    assert ctx.messages[0]["role"] == "user"
    assert ctx.messages[1]["role"] == "assistant"
    assert ctx.messages[1]["content"] == "这是一段被截断的回复"
    assert ctx.messages[2]["role"] == "user"
    assert "继续" in ctx.messages[2]["content"]


def test_agent_run_multiple_tool_calls_across_steps():
    """测试多次工具调用（跨多步）"""
    mock_adapter = MagicMock()
    mock_adapter.chat.side_effect = [
        LLMResponse(
            content=[{"type": "tool_use", "id": "t1", "name": "echo", "input": {"x": 1}}],
            stop_reason="tool_use",
        ),
        LLMResponse(
            content=[{"type": "tool_use", "id": "t2", "name": "echo", "input": {"x": 2}}],
            stop_reason="tool_use",
        ),
        LLMResponse(content="Final result", stop_reason="end_turn"),
    ]
    mock_tools = MagicMock()
    mock_tools.execute.return_value = "done"

    ctx = Context(system_prompt="You are helpful.")
    agent = Agent(llm_adapter=mock_adapter, tools=mock_tools, context=ctx, max_steps=5)

    result = agent.run("Do multiple things")
    assert result == "Final result"
    assert mock_adapter.chat.call_count == 3
    assert mock_tools.execute.call_count == 2


def test_agent_confirm_pending_with_confirmed_results():
    """测试混合确认场景：部分工具已确认，部分需要确认"""
    mock_adapter = MagicMock()
    mock_tools = MagicMock()

    def execute_side_effect(name, args, confirmed=False, tool_id="", agent=None, on_event=None):
        if name == "echo":
            return "echo result"
        if name == "bash":
            if confirmed:
                return "bash confirmed result"
            return "[CONFIRM_REQUIRED] bash needs confirmation"

    mock_tools.execute.side_effect = execute_side_effect
    mock_tools.list_for_llm.return_value = []

    mock_adapter.chat.return_value = LLMResponse(
        content=[
            {"type": "tool_use", "id": "t1", "name": "echo", "input": {"x": 1}},
            {"type": "tool_use", "id": "t2", "name": "bash", "input": {"cmd": "rm -rf /"}},
        ],
        stop_reason="tool_use",
    )

    ctx = Context(system_prompt="You are helpful.")
    agent = Agent(llm_adapter=mock_adapter, tools=mock_tools, context=ctx, max_steps=5)

    result = agent.run("Run echo and bash")
    assert "[CONFIRM_REQUIRED]" in result

    confirmed_tools = set()
    should_continue, confirm_result = agent.confirm_pending(confirmed_tools)
    assert should_continue is True

    assert len(ctx.messages) == 3
    tool_result_msg = ctx.messages[2]
    assert tool_result_msg["role"] == "user"
    assert len(tool_result_msg["content"]) == 2
    tool_ids = [b["tool_use_id"] for b in tool_result_msg["content"]]
    assert "t1" in tool_ids
    assert "t2" in tool_ids


# --- Parallel execution tests ---

def test_parallel_tools_execute_concurrently():
    """Multiple tool_use blocks should execute concurrently, not serially."""
    ctx = Context(system_prompt="test")
    tools = ToolRegistry()
    execution_times = []
    barrier = threading.Barrier(3, timeout=5)

    def slow_handler(**kwargs):
        execution_times.append(time.monotonic())
        try:
            barrier.wait(timeout=3)
        except threading.BrokenBarrierError:
            pass
        return "result"

    tools.register("slow_tool", "A slow tool", {"type": "object", "properties": {}}, slow_handler)

    llm = MagicMock()
    llm.chat.side_effect = [
        LLMResponse(
            content=[
                {"type": "tool_use", "id": "tu_1", "name": "slow_tool", "input": {}},
                {"type": "tool_use", "id": "tu_2", "name": "slow_tool", "input": {}},
                {"type": "tool_use", "id": "tu_3", "name": "slow_tool", "input": {}},
            ],
            stop_reason="tool_use",
        ),
        LLMResponse(content="done", stop_reason="end_turn"),
    ]

    agent = Agent(llm, tools, ctx, max_steps=5)
    agent.auto_confirm = True
    result = agent.run("hello")

    assert len(execution_times) == 3
    max_gap = max(execution_times) - min(execution_times)
    assert max_gap < 0.5, f"Tools not concurrent: gap={max_gap:.2f}s"


def test_parallel_results_order_preserved():
    """Tool results should be written to context in original tool_use order."""
    ctx = Context(system_prompt="test")
    tools = ToolRegistry()

    def ordered_handler(**kwargs):
        time.sleep(0.02)
        return "ok"

    tools.register("tool_a", "Tool A", {"type": "object", "properties": {}}, ordered_handler)

    llm = MagicMock()
    llm.chat.side_effect = [
        LLMResponse(
            content=[
                {"type": "tool_use", "id": "tu_1", "name": "tool_a", "input": {}},
                {"type": "tool_use", "id": "tu_2", "name": "tool_a", "input": {}},
                {"type": "tool_use", "id": "tu_3", "name": "tool_a", "input": {}},
            ],
            stop_reason="tool_use",
        ),
        LLMResponse(content="done", stop_reason="end_turn"),
    ]

    agent = Agent(llm, tools, ctx, max_steps=5)
    agent.auto_confirm = True
    result = agent.run("hello")

    messages = ctx.get_messages()
    for msg in messages:
        if msg.get("role") == "user" and isinstance(msg.get("content"), list):
            tool_results = [b for b in msg["content"] if b.get("type") == "tool_result"]
            if tool_results:
                assert len(tool_results) == 3
                assert tool_results[0]["tool_use_id"] == "tu_1"
                assert tool_results[1]["tool_use_id"] == "tu_2"
                assert tool_results[2]["tool_use_id"] == "tu_3"
                return
    assert False, "No tool_results found in context"


def test_parallel_tools_mixed_confirm():
    """When some tools need confirm and others don't, pending list has correct items."""
    ctx = Context(system_prompt="test")
    tools = ToolRegistry()

    def safe_handler(**kwargs):
        return "safe result"

    def dangerous_handler(**kwargs):
        return "[CONFIRM_REQUIRED] tu_2 dangerous operation"

    tools.register("safe_tool", "A safe tool", {"type": "object", "properties": {}}, safe_handler)
    tools.register("dangerous_tool", "A dangerous tool", {"type": "object", "properties": {}}, dangerous_handler, dangerous=True)

    llm = MagicMock()
    llm.chat.side_effect = [
        LLMResponse(
            content=[
                {"type": "tool_use", "id": "tu_1", "name": "safe_tool", "input": {}},
                {"type": "tool_use", "id": "tu_2", "name": "dangerous_tool", "input": {}},
                {"type": "tool_use", "id": "tu_3", "name": "safe_tool", "input": {}},
            ],
            stop_reason="tool_use",
        ),
    ]

    agent = Agent(llm, tools, ctx, max_steps=5)
    result = agent.run("hello")

    assert agent._pending_confirms is not None
    assert len(agent._pending_confirms) == 1
    assert agent._pending_confirms[0][0] == "tu_2"
    assert len(agent._confirmed_results) == 2
    confirmed_ids = {r[0] for r in agent._confirmed_results}
    assert confirmed_ids == {"tu_1", "tu_3"}


def test_single_tool_no_thread_overhead():
    """Single tool_use should execute inline without ThreadPoolExecutor."""
    ctx = Context(system_prompt="test")
    tools = ToolRegistry()
    call_count = 0

    def handler(**kwargs):
        nonlocal call_count
        call_count += 1
        return "result"

    tools.register("test_tool", "A test tool", {"type": "object", "properties": {}}, handler)

    llm = MagicMock()
    llm.chat.side_effect = [
        LLMResponse(
            content=[{"type": "tool_use", "id": "tu_1", "name": "test_tool", "input": {}}],
            stop_reason="tool_use",
        ),
        LLMResponse(content="done", stop_reason="end_turn"),
    ]

    agent = Agent(llm, tools, ctx, max_steps=5)
    agent.auto_confirm = True
    result = agent.run("hello")
    assert call_count == 1
    assert result == "done"
