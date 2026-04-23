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
        base_url="https://api.test.com",
        model="test-model"
    )
    assert adapter.api_key == "test-key"
    assert adapter.model == "test-model"
    assert adapter.base_url == "https://api.test.com"


@patch("agent.adapter.anthropic")
def test_llm_adapter_chat_with_text_response(mock_anthropic):
    """测试普通文本回复"""
    mock_client = MagicMock()
    mock_response = MagicMock()

    # 模拟文本响应
    mock_text_block = MagicMock()
    mock_text_block.type = "text"
    mock_text_block.text = "Hello, world!"

    mock_response.content = [mock_text_block]
    mock_response.stop_reason = "end_turn"

    mock_client.messages.create.return_value = mock_response
    mock_anthropic.Anthropic.return_value = mock_client

    adapter = LLMAdapter(
        api_key="test-key",
        base_url="https://api.test.com",
        model="test-model"
    )

    response = adapter.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[]
    )

    assert response.content == "Hello, world!"
    assert response.stop_reason == "end_turn"


@patch("agent.adapter.anthropic")
def test_llm_adapter_chat_with_tool_call(mock_anthropic):
    """测试工具调用响应"""
    mock_client = MagicMock()
    mock_response = MagicMock()

    # 模拟 tool_use 响应
    mock_tool_block = MagicMock()
    mock_tool_block.type = "tool_use"
    mock_tool_block.id = "toolu_01"
    mock_tool_block.name = "echo"
    mock_tool_block.input = {"x": "hello"}

    mock_response.content = [mock_tool_block]
    mock_response.stop_reason = "tool_use"

    mock_client.messages.create.return_value = mock_response
    mock_anthropic.Anthropic.return_value = mock_client

    adapter = LLMAdapter(
        api_key="test-key",
        base_url="https://api.test.com",
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
    assert response.content[0]["input"] == {"x": "hello"}
