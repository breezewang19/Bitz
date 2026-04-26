# tests/test_adapter.py
"""Tests for LLMAdapter"""
import threading
from unittest.mock import MagicMock, patch

import pytest
from agent.adapter import LLMAdapter, LLMResponse, LLMError


class TestLLMAdapterChat:
    @patch("anthropic.Anthropic")
    def test_chat_returns_response(self, mock_anthropic_cls):
        """chat() should return LLMResponse on success."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = [MagicMock(type="text", text="Hello!")]
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

        tool_block = MagicMock(type="tool_use", id="t1", name="bash", input={"cmd": "ls"})
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
    def test_cancel_event_stops_chat(self, mock_anthropic_cls):
        """chat() should raise LLMError when cancel_event is set during call."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        # Simulate a long-running create call that we cancel
        def slow_create(**kwargs):
            import time
            time.sleep(10)
            return MagicMock()

        mock_client.messages.create.side_effect = slow_create

        adapter = LLMAdapter(api_key="test-key", model="test-model")
        cancel_event = threading.Event()

        # Set cancel after a short delay
        def set_cancel():
            import time
            time.sleep(0.1)
            cancel_event.set()

        threading.Thread(target=set_cancel, daemon=True).start()

        with pytest.raises(LLMError, match="已中断"):
            adapter.chat(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
                cancel_event=cancel_event,
            )
