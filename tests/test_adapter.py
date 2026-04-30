# tests/test_adapter.py
"""Tests for LLMAdapter"""
import threading
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from agent.adapter import LLMAdapter, LLMResponse, LLMError, RetryableError


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


class TestLLMAdapterOpenAI:
    @patch("httpx.post")
    def test_openai_chat_returns_response(self, mock_post):
        """OpenAI 协议 chat() 应返回 LLMResponse"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {"role": "assistant", "content": "Hello from OpenAI!"},
                "finish_reason": "stop",
            }]
        }
        mock_post.return_value = mock_response

        adapter = LLMAdapter(
            api_key="sk-test", model="gpt-4o",
            base_url="https://api.openai.com/v1",
            protocol="openai",
        )
        response = adapter.chat(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
        )
        assert isinstance(response, LLMResponse)
        assert response.content == "Hello from OpenAI!"
        assert response.stop_reason == "end_turn"

    @patch("httpx.post")
    def test_openai_chat_handles_tool_use(self, mock_post):
        """OpenAI 协议应处理 tool_calls 响应"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "bash", "arguments": '{"cmd": "ls"}'},
                    }],
                },
                "finish_reason": "tool_calls",
            }]
        }
        mock_post.return_value = mock_response

        adapter = LLMAdapter(
            api_key="sk-test", model="gpt-4o",
            base_url="https://api.openai.com/v1",
            protocol="openai",
        )
        response = adapter.chat(
            messages=[{"role": "user", "content": "list files"}],
            tools=[{"name": "bash", "description": "run bash", "input_schema": {}}],
        )
        assert response.stop_reason == "tool_use"
        assert len(response.content) == 1
        assert response.content[0]["name"] == "bash"
        assert response.content[0]["id"] == "call_1"


class TestRetryableError:
    """RetryableError 异常类测试"""

    def test_retryable_error_is_exception(self):
        err = RetryableError("timeout")
        assert isinstance(err, Exception)
        assert not isinstance(err, LLMError)

    def test_llm_error_is_exception(self):
        err = LLMError("中断")
        assert isinstance(err, Exception)
        assert not isinstance(err, RetryableError)


class TestRetryLogic:
    """重试逻辑测试"""

    @patch("anthropic.Anthropic")
    def test_timeout_retries(self, mock_anthropic_cls):
        """超时错误应触发重试"""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        # 第一次超时，第二次成功
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "OK"
        mock_message = MagicMock()
        mock_message.content = [text_block]
        mock_message.stop_reason = "end_turn"

        call_count = [0]
        def create_side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RetryableError("API 请求超时 (120s)")
            return mock_message

        mock_client.messages.create.side_effect = create_side_effect

        adapter = LLMAdapter(api_key="test", model="test-model")
        response = adapter.chat(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            max_retries=3,
        )
        assert response.content == "OK"
        assert call_count[0] == 2

    @patch("anthropic.Anthropic")
    def test_timeout_exhausted_raises_llm_error(self, mock_anthropic_cls):
        """超时重试耗尽后应抛 LLMError"""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = RetryableError("API 请求超时")

        adapter = LLMAdapter(api_key="test", model="test-model")
        with pytest.raises(LLMError, match="重试耗尽"):
            adapter.chat(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
                max_retries=2,
            )

    @patch("anthropic.Anthropic")
    def test_rate_limit_retries(self, mock_anthropic_cls):
        """RateLimitError 应触发重试"""
        import anthropic
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "OK"
        mock_message = MagicMock()
        mock_message.content = [text_block]
        mock_message.stop_reason = "end_turn"

        call_count = [0]
        def create_side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise anthropic.RateLimitError(message="rate limited", response=MagicMock(), body=None)
            return mock_message

        mock_client.messages.create.side_effect = create_side_effect

        adapter = LLMAdapter(api_key="test", model="test-model")
        response = adapter.chat(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            max_retries=3,
        )
        assert response.content == "OK"
        assert call_count[0] == 2

    @patch("anthropic.Anthropic")
    def test_internal_server_error_retries(self, mock_anthropic_cls):
        """InternalServerError (5xx) 应触发重试"""
        import anthropic
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "OK"
        mock_message = MagicMock()
        mock_message.content = [text_block]
        mock_message.stop_reason = "end_turn"

        call_count = [0]
        def create_side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise anthropic.InternalServerError(message="500", response=MagicMock(), body=None)
            return mock_message

        mock_client.messages.create.side_effect = create_side_effect

        adapter = LLMAdapter(api_key="test", model="test-model")
        response = adapter.chat(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            max_retries=3,
        )
        assert response.content == "OK"
        assert call_count[0] == 2

    @patch("anthropic.Anthropic")
    def test_api_connection_error_retries(self, mock_anthropic_cls):
        """APIConnectionError 应触发重试"""
        import anthropic
        import httpx
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "OK"
        mock_message = MagicMock()
        mock_message.content = [text_block]
        mock_message.stop_reason = "end_turn"

        call_count = [0]
        def create_side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise anthropic.APIConnectionError(
                    message="connection failed",
                    request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
                )
            return mock_message

        mock_client.messages.create.side_effect = create_side_effect

        adapter = LLMAdapter(api_key="test", model="test-model")
        response = adapter.chat(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            max_retries=3,
        )
        assert response.content == "OK"
        assert call_count[0] == 2

    @patch("anthropic.Anthropic")
    def test_user_cancel_not_retried(self, mock_anthropic_cls):
        """用户中断（LLMError）不应重试"""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = LLMError("已中断")

        adapter = LLMAdapter(api_key="test", model="test-model")
        with pytest.raises(LLMError, match="已中断"):
            adapter.chat(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
                max_retries=5,
            )
        # 只调用了一次，没有重试
        assert mock_client.messages.create.call_count == 1

    @patch("anthropic.Anthropic")
    def test_on_retry_callback_called(self, mock_anthropic_cls):
        """重试时应调用 on_retry 回调"""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "OK"
        mock_message = MagicMock()
        mock_message.content = [text_block]
        mock_message.stop_reason = "end_turn"

        call_count = [0]
        def create_side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise RetryableError("超时")
            return mock_message

        mock_client.messages.create.side_effect = create_side_effect

        retry_calls = []
        def on_retry(err_msg, attempt, max_retries):
            retry_calls.append((err_msg, attempt, max_retries))

        adapter = LLMAdapter(api_key="test", model="test-model", on_retry=on_retry)
        response = adapter.chat(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            max_retries=5,
        )
        assert response.content == "OK"
        assert len(retry_calls) == 2  # 两次超时，两次回调
