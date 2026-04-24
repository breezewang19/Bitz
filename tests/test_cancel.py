# tests/test_cancel.py
"""ESC 取消功能测试"""
import pytest
import threading
import time
from unittest.mock import MagicMock, patch

from agent.adapter import LLMAdapter, LLMResponse, LLMError
from agent.loop import Agent
from agent.context import Context


class TestAdapterCancel:
    """测试 adapter 的 cancel_event 支持"""

    def test_cancel_event_set_before_call(self):
        """cancel_event 已设置时，chat 应立即抛出 LLMError"""
        adapter = LLMAdapter(api_key="test", model="test-model")
        cancel = threading.Event()
        cancel.set()

        with pytest.raises(LLMError, match="已中断"):
            adapter.chat(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
                cancel_event=cancel
            )

    def test_cancel_event_set_during_call(self):
        """API 调用期间设置 cancel_event，应抛出 LLMError"""
        adapter = LLMAdapter(api_key="test", model="test-model")
        cancel = threading.Event()

        # Mock client.messages.create 为长时间阻塞
        with patch.object(adapter, '_chat_once') as mock_chat:
            def slow_call(*args, **kwargs):
                time.sleep(5)
                return LLMResponse(content="done", stop_reason="end_turn")
            mock_chat.side_effect = slow_call

            # 在另一个线程中延迟设置 cancel
            def set_cancel():
                time.sleep(0.3)
                cancel.set()

            threading.Thread(target=set_cancel, daemon=True).start()

            with pytest.raises(LLMError, match="已中断"):
                adapter.chat(
                    messages=[{"role": "user", "content": "hi"}],
                    tools=[],
                    cancel_event=cancel
                )

    def test_no_cancel_event_works_normally(self):
        """不传 cancel_event 时正常工作"""
        mock_adapter = MagicMock()
        mock_adapter.chat.return_value = LLMResponse(
            content="Hello", stop_reason="end_turn"
        )
        # 不传 cancel_event 也能正常调用
        result = mock_adapter.chat(
            messages=[{"role": "user", "content": "hi"}],
            tools=[]
        )
        assert result.content == "Hello"


class TestAgentCancel:
    """测试 Agent 循环的 cancel_event 透传"""

    def test_agent_run_with_cancel_event(self):
        """Agent.run 接受 cancel_event 参数"""
        mock_adapter = MagicMock()
        mock_adapter.chat.return_value = LLMResponse(
            content="Hello", stop_reason="end_turn"
        )
        mock_tools = MagicMock()
        ctx = Context(system_prompt="test")

        agent = Agent(
            llm_adapter=mock_adapter,
            tools=mock_tools,
            context=ctx,
            max_steps=5
        )

        cancel = threading.Event()
        result = agent.run("hi", cancel_event=cancel)
        assert result == "Hello"

        # 验证 cancel_event 被传递给 adapter.chat
        call_kwargs = mock_adapter.chat.call_args[1]
        assert call_kwargs.get('cancel_event') is cancel

    def test_agent_run_cancel_during_request(self):
        """Agent 循环中取消请求，返回 LLMError 信息"""
        mock_adapter = MagicMock()
        mock_adapter.chat.side_effect = LLMError("已中断")
        mock_tools = MagicMock()
        ctx = Context(system_prompt="test")

        agent = Agent(
            llm_adapter=mock_adapter,
            tools=mock_tools,
            context=ctx,
            max_steps=5
        )

        cancel = threading.Event()
        result = agent.run("hi", cancel_event=cancel)
        assert "LLM Error" in result
        assert "已中断" in result

    def test_agent_run_cancel_during_tool_loop(self):
        """工具调用循环中取消请求"""
        mock_adapter = MagicMock()
        mock_tools = MagicMock()

        # 第一次调用返回 tool_use，第二次取消
        mock_adapter.chat.side_effect = [
            LLMResponse(
                content=[{"type": "tool_use", "id": "t1", "name": "echo", "input": {}}],
                stop_reason="tool_use"
            ),
            LLMError("用户按 ESC 取消了请求")
        ]
        mock_tools.execute.return_value = "result"

        ctx = Context(system_prompt="test")
        agent = Agent(
            llm_adapter=mock_adapter,
            tools=mock_tools,
            context=ctx,
            max_steps=5
        )

        cancel = threading.Event()
        result = agent.run("do something", cancel_event=cancel)
        assert "LLM Error" in result

    def test_agent_run_without_cancel_event(self):
        """不传 cancel_event 时正常工作（向后兼容）"""
        mock_adapter = MagicMock()
        mock_adapter.chat.return_value = LLMResponse(
            content="Hello", stop_reason="end_turn"
        )
        mock_tools = MagicMock()
        ctx = Context(system_prompt="test")

        agent = Agent(
            llm_adapter=mock_adapter,
            tools=mock_tools,
            context=ctx,
            max_steps=5
        )

        result = agent.run("hi")
        assert result == "Hello"
