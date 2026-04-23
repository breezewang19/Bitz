# tests/test_context.py
"""Context 会话上下文测试"""
import pytest
from agent.context import Context


def test_context_init():
    """测试 Context 初始化"""
    ctx = Context(
        system_prompt="You are a helpful assistant.",
        max_tokens=1000,
        keep_last_n=10
    )
    assert ctx.system_prompt == "You are a helpful assistant."
    assert ctx.max_tokens == 1000
    assert ctx.keep_last_n == 10
    assert ctx.messages == []


def test_context_add_user():
    """测试添加用户消息"""
    ctx = Context(system_prompt="You are helpful.")
    ctx.add_user("Hello, who are you?")
    assert len(ctx.messages) == 1
    assert ctx.messages[0]["role"] == "user"
    assert ctx.messages[0]["content"] == "Hello, who are you?"


def test_context_add_tool_result():
    """测试添加工具结果"""
    ctx = Context(system_prompt="You are helpful.")
    ctx.add_user("What is the weather?")
    ctx.add_tool_result("toolu_01", "Sunny, 25 degrees")
    assert len(ctx.messages) == 2
    assert ctx.messages[1]["role"] == "user"
    assert ctx.messages[1]["tool_use_id"] == "toolu_01"
    assert ctx.messages[1]["content"] == "Sunny, 25 degrees"


def test_context_trim():
    """测试消息修剪"""
    ctx = Context(system_prompt="You are helpful.", keep_last_n=3)
    ctx.add_user("Message 1")
    ctx.add_user("Message 2")
    ctx.add_user("Message 3")
    ctx.add_user("Message 4")
    assert len(ctx.messages) == 3
    # The first message should have been trimmed
    assert ctx.messages[0]["content"] == "Message 2"
    assert ctx.messages[1]["content"] == "Message 3"
    assert ctx.messages[2]["content"] == "Message 4"


def test_context_get_messages():
    """测试获取完整消息列表"""
    ctx = Context(system_prompt="You are a helpful assistant.", keep_last_n=5)
    ctx.add_user("Hi")
    ctx.add_user("How are you?")
    msgs = ctx.get_messages()
    # Should include system prompt as first message
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == "You are a helpful assistant."
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "Hi"
    assert msgs[2]["role"] == "user"
    assert msgs[2]["content"] == "How are you?"


def test_context_get_messages_trimmed():
    """测试 get_messages 返回修剪后的消息"""
    ctx = Context(system_prompt="You are helpful.", keep_last_n=2)
    ctx.add_user("Message 1")
    ctx.add_user("Message 2")
    ctx.add_user("Message 3")
    msgs = ctx.get_messages()
    # Should include system prompt + last 2 messages
    assert len(msgs) == 3  # system + 2 trimmed
    assert msgs[0]["role"] == "system"
    assert msgs[1]["content"] == "Message 2"
    assert msgs[2]["content"] == "Message 3"