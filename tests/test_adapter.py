# tests/test_adapter.py
import pytest
import os
from unittest.mock import patch, MagicMock
from agent.adapter import LLMAdapter, LLMResponse


def test_llm_response_dataclass():
    """测试 LLMResponse 数据类"""
    response = LLMResponse(
        content="Hello",
        stop_reason="end_turn"
    )
    assert response.content == "Hello"
    assert response.stop_reason == "end_turn"


def test_llm_adapter_init():
    """测试适配器初始化"""
    adapter = LLMAdapter(
        api_key="test-key",
        base_url="https://api.test.com/v1",
        model="test-model"
    )
    assert adapter.api_key == "test-key"
    assert adapter.model == "test-model"
    assert adapter.base_url == "https://api.test.com/v1"


@patch("agent.adapter.openai")
def test_llm_adapter_chat_with_text_response(mock_openai):
    """测试普通文本回复"""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_message = MagicMock()
    mock_message.content = "Hello, world!"
    mock_message.tool_calls = None
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response
    # openai.OpenAI(...) returns mock_client
    mock_openai.OpenAI.return_value = mock_client

    adapter = LLMAdapter(
        api_key="test-key",
        base_url="https://api.test.com/v1",
        model="test-model"
    )

    response = adapter.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[]
    )

    assert response.content == "Hello, world!"
    assert response.stop_reason == "end_turn"


@patch("agent.adapter.openai")
def test_llm_adapter_chat_with_tool_call(mock_openai):
    """测试工具调用响应"""
    mock_client = MagicMock()
    mock_response = MagicMock()

    # 模拟 tool_use 响应
    mock_tool_call = MagicMock()
    mock_tool_call.id = "toolu_01"
    mock_tool_call.function.name = "echo"
    mock_tool_call.function.arguments = '{"x": "hello"}'

    mock_message = MagicMock()
    mock_message.content = None
    mock_message.tool_calls = [mock_tool_call]
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response
    # openai.OpenAI(...) returns mock_client
    mock_openai.OpenAI.return_value = mock_client

    adapter = LLMAdapter(
        api_key="test-key",
        base_url="https://api.test.com/v1",
        model="test-model"
    )

    response = adapter.chat(
        messages=[{"role": "user", "content": "use echo"}],
        tools=[{"name": "echo", "description": "Echo back", "input_schema": {}}]
    )

    assert response.stop_reason == "tool_use"
    assert isinstance(response.content, list)
    assert len(response.content) == 1
    assert response.content[0]["type"] == "tool_use"
    assert response.content[0]["name"] == "echo"
