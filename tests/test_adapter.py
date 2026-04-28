# tests/test_adapter.py
"""Tests for LLMAdapter"""
import threading
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from agent.adapter import LLMAdapter, LLMResponse, LLMError


class TestLLMAdapterChat:
    @patch("anthropic.Anthropic")
    def test_chat_returns_response(self, mock_anthropic_cls):
        """chat() should return LLMResponse on success."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"

        mock_message = MagicMock()
        mock_message.content = [text_block]
        mock_message.stop_reason = "end_turn"
        mock_client.messages.create.return_value = mock_message

        adapter = LLMAdapter(api_key="test-key", model="test-model")
        response = adapter.chat(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
        )
        assert isinstance(response, LLMResponse)
        assert response.content == "Hello!"
        assert response.stop_reason == "end_turn"

    @patch("anthropic.Anthropic")
    def test_chat_handles_tool_use(self, mock_anthropic_cls):
        """chat() should handle tool_use stop reason."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "t1"
        tool_block.name = "bash"
        tool_block.input = {"cmd": "ls"}

        mock_message = MagicMock()
        mock_message.content = [tool_block]
        mock_message.stop_reason = "tool_use"
        mock_client.messages.create.return_value = mock_message

        adapter = LLMAdapter(api_key="test-key", model="test-model")
        response = adapter.chat(
            messages=[{"role": "user", "content": "list files"}],
            tools=[{"name": "bash", "description": "run bash", "input_schema": {}}],
        )
        assert response.stop_reason == "tool_use"
        assert len(response.content) == 1
        assert response.content[0]["name"] == "bash"
        assert response.content[0]["id"] == "t1"

    @patch("anthropic.Anthropic")
    def test_chat_raises_on_api_error(self, mock_anthropic_cls):
        """chat() should raise LLMError on API failure."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API error")

        adapter = LLMAdapter(api_key="test-key", model="test-model")
        with pytest.raises(LLMError):
            adapter.chat(messages=[{"role": "user", "content": "hi"}], tools=[])


class TestLLMAdapterCancel:
    @patch("anthropic.Anthropic")
    def test_cancel_event_set_before_call(self, mock_anthropic_cls):
        """cancel_event 已设置时，chat 应立即抛出 LLMError"""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        adapter = LLMAdapter(api_key="test", model="test-model")
        cancel = threading.Event()
        cancel.set()

        with pytest.raises(LLMError, match="已中断"):
            adapter.chat(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
                cancel_event=cancel
            )

    @patch("anthropic.Anthropic")
    def test_cancel_event_set_during_call(self, mock_anthropic_cls):
        """API 调用期间设置 cancel_event，应抛出 LLMError"""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        def slow_create(**kwargs):
            import time
            time.sleep(10)
            return MagicMock()

        mock_client.messages.create.side_effect = slow_create

        adapter = LLMAdapter(api_key="test", model="test-model")
        cancel = threading.Event()

        def set_cancel():
            import time
            time.sleep(0.1)
            cancel.set()

        threading.Thread(target=set_cancel, daemon=True).start()

        with pytest.raises(LLMError, match="已中断"):
            adapter.chat(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
                cancel_event=cancel
            )
