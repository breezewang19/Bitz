"""Subagent 集成测试"""
import pytest
from unittest.mock import Mock
from agent.subagent import SubAgent, SubAgentPool
from agent.tools import ToolRegistry


def test_subagent_cannot_spawn():
    """验证 SubAgent 的 tools 中没有 spawn_subagents"""
    mock_adapter = Mock()
    mock_adapter.chat.return_value = Mock(content="完成", stop_reason="end_turn")

    base_tools = ToolRegistry()
    base_tools.register(
        name="bash",
        description="执行命令",
        input_schema={"type": "object"},
        handler=lambda **kwargs: "result"
    )

    # SubAgentPool 只传递 base_tools
    pool = SubAgentPool(mock_adapter, base_tools)

    # 检查 base_tools 中没有 spawn_subagents
    assert "spawn_subagents" not in pool.base_tools.tools

    # 创建 SubAgent
    subagent = SubAgent(
        task="测试",
        llm_adapter=mock_adapter,
        tools=pool.base_tools
    )

    # SubAgent 的 tools 中也没有 spawn_subagents
    assert "spawn_subagents" not in subagent.tools.tools