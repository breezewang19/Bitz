# tests/test_subagent.py
"""SubAgent 数据类测试"""
import pytest
from unittest.mock import MagicMock
from agent.subagent import SubAgentResult, SubAgentSpec
from agent.loop import Agent
from agent.context import Context
from agent.adapter import LLMAdapter
from agent.tools import ToolRegistry


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
