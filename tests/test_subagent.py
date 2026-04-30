# tests/test_subagent.py
"""SubAgent 数据类测试"""
import pytest
from unittest.mock import MagicMock
from agent.subagent import SubAgentResult, SubAgentSpec
from agent.loop import Agent
from agent.context import Context
from agent.adapter import LLMAdapter
from agent.tools import ToolRegistry
from agent.subagent import SubAgent


class TestSubAgentResult:
    def test_success_result_defaults(self):
        r = SubAgentResult(success=True, output="done")
        assert r.success is True
        assert r.output == "done"
        assert r.steps == 0
        assert r.elapsed == 0.0
        assert r.error is None

    def test_error_result(self):
        r = SubAgentResult(success=False, output="", error="timeout")
        assert r.success is False
        assert r.error == "timeout"

    def test_full_result(self):
        r = SubAgentResult(success=True, output="ok", steps=5, elapsed=12.3)
        assert r.steps == 5
        assert r.elapsed == 12.3


class TestSubAgentSpec:
    def test_defaults(self):
        spec = SubAgentSpec(task="review code")
        assert spec.task == "review code"
        assert spec.context_hint == ""
        assert spec.max_steps == 10
        assert spec.model is None

    def test_custom_values(self):
        spec = SubAgentSpec(
            task="review",
            context_hint="Rule: check X",
            max_steps=5,
            model="claude-haiku-4-5-20251001",
        )
        assert spec.context_hint == "Rule: check X"
        assert spec.max_steps == 5
        assert spec.model == "claude-haiku-4-5-20251001"


class TestAgentAutoConfirm:
    def test_auto_confirm_default_false(self):
        llm = MagicMock(spec=LLMAdapter)
        ctx = Context(system_prompt="test")
        tools = ToolRegistry()
        agent = Agent(llm_adapter=llm, tools=tools, context=ctx)
        assert agent.auto_confirm is False

    def test_auto_confirm_can_set_true(self):
        llm = MagicMock(spec=LLMAdapter)
        ctx = Context(system_prompt="test")
        tools = ToolRegistry()
        agent = Agent(llm_adapter=llm, tools=tools, context=ctx)
        agent.auto_confirm = True
        assert agent.auto_confirm is True


def _make_parent_agent():
    """创建 mock 父 Agent，模拟真实结构"""
    agent = MagicMock(spec=Agent)
    agent.llm_adapter = MagicMock(spec=LLMAdapter)
    agent.llm_adapter.api_key = "test-key"
    agent.llm_adapter.base_url = "https://api.test.com"
    agent.llm_adapter.model = "test-model"
    agent.llm_adapter.protocol = "anthropic"
    agent.tools = ToolRegistry()
    agent.context = Context(system_prompt="You are a test assistant.")
    agent.context.add_user("parent message that should not leak")
    return agent


class TestSubAgentConstruction:
    def test_inherits_llm_config(self):
        parent = _make_parent_agent()
        spec = SubAgentSpec(task="do something")
        sub = SubAgent(parent, spec)
        assert sub._llm.api_key == "test-key"
        assert sub._llm.model == "test-model"
        assert sub._llm.protocol == "anthropic"

    def test_inherits_custom_model(self):
        parent = _make_parent_agent()
        spec = SubAgentSpec(task="test", model="claude-haiku-4-5-20251001")
        sub = SubAgent(parent, spec)
        assert sub._llm.model == "claude-haiku-4-5-20251001"

    def test_independent_context_no_parent_history(self):
        parent = _make_parent_agent()
        spec = SubAgentSpec(task="sub task")
        sub = SubAgent(parent, spec)
        msgs = sub._context.get_messages()
        user_msgs = [m for m in msgs if m["role"] == "user"]
        assert len(user_msgs) == 1
        assert "sub task" in user_msgs[0]["content"]
        # 父的对话历史不应泄漏
        assert "parent message" not in user_msgs[0]["content"]

    def test_context_hint_injected(self):
        parent = _make_parent_agent()
        spec = SubAgentSpec(task="review", context_hint="Rule: check X")
        sub = SubAgent(parent, spec)
        msgs = sub._context.get_messages()
        user_msgs = [m for m in msgs if m["role"] == "user"]
        assert "Rule: check X" in user_msgs[0]["content"]

    def test_inherits_system_prompt(self):
        parent = _make_parent_agent()
        spec = SubAgentSpec(task="test")
        sub = SubAgent(parent, spec)
        msgs = sub._context.get_messages()
        system_msgs = [m for m in msgs if m["role"] == "system"]
        assert len(system_msgs) == 1
        assert "test assistant" in system_msgs[0]["content"]

    def test_auto_confirm_enabled(self):
        parent = _make_parent_agent()
        spec = SubAgentSpec(task="test")
        sub = SubAgent(parent, spec)
        assert sub._agent.auto_confirm is True

    def test_spawn_removed_from_tools(self):
        """子 agent 不能再 spawn，防递归"""
        parent = _make_parent_agent()
        parent.tools.register("spawn", "spawn sub agents", {"type": "object", "properties": {}}, handler=lambda: "")
        spec = SubAgentSpec(task="test")
        sub = SubAgent(parent, spec)
        assert "spawn" not in sub._tools.tools

    def test_other_tools_preserved(self):
        """除 spawn 外的工具都应保留"""
        parent = _make_parent_agent()
        parent.tools.register("bash", "run command", {"type": "object", "properties": {}}, handler=lambda: "")
        parent.tools.register("read_file", "read file", {"type": "object", "properties": {}}, handler=lambda: "")
        parent.tools.register("spawn", "spawn sub agents", {"type": "object", "properties": {}}, handler=lambda: "")
        spec = SubAgentSpec(task="test")
        sub = SubAgent(parent, spec)
        assert "bash" in sub._tools.tools
        assert "read_file" in sub._tools.tools
        assert "spawn" not in sub._tools.tools
