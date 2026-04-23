"""SubAgent 并行执行测试"""
import pytest
from unittest.mock import Mock, MagicMock
from agent.subagent import SubAgent, SubAgentPool, SubAgentTimeout
from agent.context import Context
from agent.tools import ToolRegistry


class TestSubAgent:
    """SubAgent 单元测试"""

    def test_subagent_has_independent_context(self):
        """SubAgent 应该有独立的 Context"""
        mock_adapter = Mock()
        mock_adapter.chat.return_value = Mock(
            content="test result",
            stop_reason="end_turn"
        )

        tools = ToolRegistry()

        subagent = SubAgent(
            task="测试任务",
            llm_adapter=mock_adapter,
            tools=tools,
            depth=1
        )

        assert isinstance(subagent.context, Context)
        assert subagent.context.system_prompt.endswith("测试任务")

    def test_subagent_depth_is_one_by_default(self):
        """默认 depth=1"""
        mock_adapter = Mock()
        mock_adapter.chat.return_value = Mock(content="", stop_reason="end_turn")

        tools = ToolRegistry()

        subagent = SubAgent(
            task="测试",
            llm_adapter=mock_adapter,
            tools=tools
        )

        assert subagent.depth == 1

    def test_subagent_run_calls_llm(self):
        """run() 应该调用 LLM"""
        mock_adapter = Mock()
        mock_adapter.chat.return_value = Mock(
            content="完成",
            stop_reason="end_turn"
        )

        tools = ToolRegistry()
        subagent = SubAgent(
            task="测试",
            llm_adapter=mock_adapter,
            tools=tools
        )

        result = subagent.run()

        assert result == "完成"
        mock_adapter.chat.assert_called_once()

    def test_subagent_respects_max_steps(self):
        """应该尊重 max_steps 限制"""
        mock_adapter = Mock()
        # 模拟持续返回 tool_use（直到超限）
        mock_adapter.chat.return_value = Mock(
            content=[{"type": "tool_use", "id": "1", "name": "bash", "input": {"command": "ls"}}],
            stop_reason="tool_use"
        )

        tools = ToolRegistry()
        # 注册一个返回空结果的 bash 工具
        tools.register(
            name="bash",
            description="执行命令",
            input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
            handler=lambda command: ""
        )

        subagent = SubAgent(
            task="测试",
            llm_adapter=mock_adapter,
            tools=tools,
            max_steps=2
        )

        result = subagent.run()

        # 2 步后超限，返回错误信息
        assert "超限" in result
        # chat 被调用 2 次
        assert mock_adapter.chat.call_count == 2


class TestSubAgentPool:
    """SubAgentPool 单元测试"""

    def test_spawn_returns_results_list(self):
        """spawn() 应该返回结果列表"""
        mock_adapter = Mock()
        mock_adapter.chat.return_value = Mock(
            content="完成",
            stop_reason="end_turn"
        )

        tools = ToolRegistry()

        pool = SubAgentPool(
            llm_adapter=mock_adapter,
            base_tools=tools,
            max_parallel=5
        )

        tasks = ["任务1", "任务2", "任务3"]
        results = pool.spawn(tasks)

        assert len(results) == 3
        assert all(r is not None for r in results)

    def test_spawn_respects_max_parallel(self):
        """spawn() 应该限制最大并行数"""
        mock_adapter = Mock()
        mock_adapter.chat.side_effect = lambda *args, **kwargs: Mock(
            content="完成",
            stop_reason="end_turn"
        )

        tools = ToolRegistry()

        pool = SubAgentPool(
            llm_adapter=mock_adapter,
            base_tools=tools,
            max_parallel=2
        )

        tasks = ["任务1", "任务2", "任务3", "任务4", "任务5"]
        results = pool.spawn(tasks)

        # 只能并行 2 个
        assert len(results) == 2

    def test_spawn_uses_timeout(self):
        """spawn() 应该使用 pool 的超时设置"""
        mock_adapter = Mock()

        tools = ToolRegistry()

        pool = SubAgentPool(
            llm_adapter=mock_adapter,
            base_tools=tools,
            max_parallel=2,
            timeout=60
        )

        assert pool.timeout == 60

    def test_format_results(self):
        """format_results() 应该正确格式化"""
        mock_adapter = Mock()
        tools = ToolRegistry()

        pool = SubAgentPool(
            llm_adapter=mock_adapter,
            base_tools=tools
        )

        tasks = ["查天气", "写代码"]
        results = ["晴天", "代码完成"]

        formatted = pool.format_results(tasks, results)

        assert "[Task 1] 查天气" in formatted
        assert "[Task 2] 写代码" in formatted
        assert "晴天" in formatted
        assert "代码完成" in formatted

    def test_spawn_empty_tasks(self):
        """spawn() 处理空列表"""
        mock_adapter = Mock()
        tools = ToolRegistry()

        pool = SubAgentPool(
            llm_adapter=mock_adapter,
            base_tools=tools
        )

        results = pool.spawn([])
        assert results == []


class TestSubAgentAntiRecursion:
    """防递归机制测试"""

    def test_base_tools_lacks_spawn_subagents(self):
        """验证 base_tools 中没有 spawn_subagents"""
        tools = ToolRegistry()
        tools.register(
            name="bash",
            description="执行命令",
            input_schema={"type": "object"},
            handler=lambda **kwargs: "result"
        )

        pool = SubAgentPool(
            llm_adapter=Mock(),
            base_tools=tools
        )

        # base_tools 中没有 spawn_subagents
        assert "spawn_subagents" not in pool.base_tools.tools

    def test_subagent_tools_lacks_spawn_subagents(self):
        """验证 SubAgent 的 tools 中没有 spawn_subagents"""
        tools = ToolRegistry()
        tools.register(
            name="bash",
            description="执行命令",
            input_schema={"type": "object"},
            handler=lambda **kwargs: "result"
        )

        subagent = SubAgent(
            task="测试",
            llm_adapter=Mock(),
            tools=tools,
            timeout=30
        )

        # SubAgent 的 tools 中没有 spawn_subagents
        assert "spawn_subagents" not in subagent.tools.tools

    def test_subagent_depth_is_one(self):
        """SubAgent 默认 depth=1"""
        tools = ToolRegistry()
        subagent = SubAgent(
            task="测试",
            llm_adapter=Mock(),
            tools=tools
        )

        assert subagent.depth == 1