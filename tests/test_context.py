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
    """测试添加工具结果（Anthropic 格式）"""
    ctx = Context(system_prompt="You are helpful.")
    ctx.add_user("What is the weather?")
    ctx.add_tool_result("toolu_01", "Sunny, 25 degrees")
    assert len(ctx.messages) == 2
    assert ctx.messages[1]["role"] == "user"
    # Anthropic 格式：tool_use_id 在 content block 内部
    assert ctx.messages[1]["content"][0]["type"] == "tool_result"
    assert ctx.messages[1]["content"][0]["tool_use_id"] == "toolu_01"
    assert ctx.messages[1]["content"][0]["content"] == "Sunny, 25 degrees"


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


class FakeSessionStore:
    """In-memory fake for testing Context._persist"""
    def __init__(self):
        self.entries = []
        self.session_id = "test-session"

    def append_entry(self, session_id, entry):
        self.entries.append(entry)


def test_context_persist_user():
    store = FakeSessionStore()
    ctx = Context(system_prompt="test", session_id="s1", session_store=store)
    ctx.add_user("hello")
    assert len(store.entries) == 1
    assert store.entries[0]["role"] == "user"
    assert store.entries[0]["content"] == "hello"
    assert "uuid" in store.entries[0]
    assert "timestamp" in store.entries[0]


def test_context_persist_assistant_text():
    store = FakeSessionStore()
    ctx = Context(system_prompt="test", session_id="s1", session_store=store)
    ctx.add_assistant_text("response")
    assert len(store.entries) == 1
    assert store.entries[0]["role"] == "assistant"
    assert store.entries[0]["content"] == "response"


def test_context_persist_assistant_message():
    store = FakeSessionStore()
    ctx = Context(system_prompt="test", session_id="s1", session_store=store)
    content = [{"type": "tool_use", "id": "t1", "name": "bash", "input": {"command": "ls"}}]
    ctx.add_assistant_message(content)
    assert len(store.entries) == 1
    assert store.entries[0]["role"] == "assistant"
    assert store.entries[0]["content"] == content


def test_context_persist_tool_results():
    store = FakeSessionStore()
    ctx = Context(system_prompt="test", session_id="s1", session_store=store)
    ctx.add_tool_results([("t1", "output1"), ("t2", "output2")])
    assert len(store.entries) == 1
    assert store.entries[0]["role"] == "user"
    assert len(store.entries[0]["content"]) == 2
    assert store.entries[0]["content"][0]["tool_use_id"] == "t1"


def test_context_no_persist_without_store():
    ctx = Context(system_prompt="test")
    ctx.add_user("hello")
    # Should not raise — _persist is a no-op when _store is None
    assert len(ctx.messages) == 1


def test_context_add_tool_result_delegates_to_results():
    """add_tool_result (singular) delegates to add_tool_results, so _persist fires once"""
    store = FakeSessionStore()
    ctx = Context(system_prompt="test", session_id="s1", session_store=store)
    ctx.add_tool_result("t1", "output")
    assert len(store.entries) == 1
    assert store.entries[0]["role"] == "user"


def test_context_add_system_reminder():
    """add_system_reminder appends a user message with _meta flag."""
    ctx = Context(system_prompt="test")
    ctx.add_system_reminder("Don't forget to use task tools!")
    assert len(ctx.messages) == 1
    assert ctx.messages[0]["role"] == "user"
    assert ctx.messages[0]["content"] == "Don't forget to use task tools!"
    assert ctx.messages[0].get("_meta") is True


def test_context_get_messages_strips_meta():
    """get_messages strips _meta key before returning to API."""
    ctx = Context(system_prompt="test", keep_last_n=5)
    ctx.add_user("Hello")
    ctx.add_system_reminder("Use task tools!")
    msgs = ctx.get_messages()
    # System prompt + user message + reminder message
    assert len(msgs) == 3
    # Reminder message should NOT have _meta key
    reminder_msg = msgs[2]
    assert reminder_msg["role"] == "user"
    assert reminder_msg["content"] == "Use task tools!"
    assert "_meta" not in reminder_msg


def test_context_add_system_reminder_trims():
    """add_system_reminder calls _trim like other add methods."""
    ctx = Context(system_prompt="test", keep_last_n=2)
    ctx.add_user("Message 1")
    ctx.add_user("Message 2")
    ctx.add_system_reminder("Reminder")
    # After trim, only last 2 messages kept
    assert len(ctx.messages) == 2
    assert ctx.messages[0]["content"] == "Message 2"
    assert ctx.messages[1]["content"] == "Reminder"


def test_context_add_system_reminder_no_persist():
    """add_system_reminder intentionally skips _persist (ephemeral)."""
    store = FakeSessionStore()
    ctx = Context(system_prompt="test", session_id="s1", session_store=store)
    ctx.add_user("hello")
    ctx.add_system_reminder("reminder")
    # Only the user message should be persisted, not the reminder
    assert len(store.entries) == 1
    assert store.entries[0]["content"] == "hello"