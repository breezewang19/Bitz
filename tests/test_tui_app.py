import pytest
from unittest.mock import MagicMock
from tui.app import BitzApp
from tui.widgets.chat import ChatLog, UserMessage, AssistantMessage
from tui.widgets.input import InputBar
from tui.widgets.status import StatusBar


def make_mock_agent():
    """创建模拟 Agent。"""
    agent = MagicMock()
    agent.tools = MagicMock()
    agent.tools.execute = MagicMock(return_value="ok")
    agent.tools.list_for_llm = MagicMock(return_value=[])
    agent.llm_adapter = MagicMock()
    agent.llm_adapter._last_usage = None
    agent.context = MagicMock()
    agent.context.messages = list(range(20))  # 20 条消息
    agent.context._trim = MagicMock()
    return agent


@pytest.mark.asyncio
async def test_command_help():
    """测试 /help 命令显示帮助信息"""
    agent = make_mock_agent()
    app = BitzApp(agent=agent)
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.text = "/help"
        await pilot.press("enter")
        await pilot.pause(delay=0.3)
        msgs = app.query_one(ChatLog).query(AssistantMessage)
        assert len(msgs) >= 1
        # 验证帮助信息包含关键内容
        last_msg = msgs.last()
        assert "可用命令" in last_msg._content


@pytest.mark.asyncio
async def test_command_clear():
    """测试 /clear 命令清屏"""
    agent = make_mock_agent()
    app = BitzApp(agent=agent)
    async with app.run_test() as pilot:
        chat = app.query_one(ChatLog)
        chat.add_message("user", "测试消息")
        await pilot.pause()
        bar = app.query_one(InputBar)
        bar._input.text = "/clear"
        await pilot.press("enter")
        await pilot.pause(delay=0.3)
        msgs = chat.query(UserMessage)
        assert len(msgs) == 0


@pytest.mark.asyncio
async def test_command_compact():
    """测试 /compact 命令压缩上下文"""
    agent = make_mock_agent()
    agent.context.messages = list(range(20))
    trimmed_messages = list(range(10))
    agent.context._trim = MagicMock()
    agent.context._trim.side_effect = lambda: setattr(agent.context, 'messages', trimmed_messages)
    app = BitzApp(agent=agent)
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.text = "/compact"
        await pilot.press("enter")
        await pilot.pause(delay=0.3)
        agent.context._trim.assert_called_once()
        msgs = app.query_one(ChatLog).query(AssistantMessage)
        assert len(msgs) >= 1
        last_msg = msgs.last()
        assert "上下文已压缩" in last_msg._content


@pytest.mark.asyncio
async def test_command_theme_cycle():
    """测试 /theme 命令循环切换主题"""
    agent = make_mock_agent()
    app = BitzApp(agent=agent)
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.text = "/theme"
        await pilot.press("enter")
        await pilot.pause(delay=0.3)
        # 默认主题是 cat-dark，循环后应切换到下一个
        from tui.theme import THEME_NAMES
        msgs = app.query_one(ChatLog).query(AssistantMessage)
        assert len(msgs) >= 1
        last_msg = msgs.last()
        assert "主题已切换为" in last_msg._content


@pytest.mark.asyncio
async def test_command_theme_with_valid_name():
    """测试 /theme cat-nord 命令切换到指定主题"""
    agent = make_mock_agent()
    app = BitzApp(agent=agent)
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.text = "/theme cat-nord"
        await pilot.press("enter")
        await pilot.pause(delay=0.3)
        assert app.theme == "cat-nord"
        msgs = app.query_one(ChatLog).query(AssistantMessage)
        assert len(msgs) >= 1
        last_msg = msgs.last()
        assert "cat-nord" in last_msg._content


@pytest.mark.asyncio
async def test_command_theme_with_invalid_name():
    """测试 /theme nonexistent 命令显示错误"""
    agent = make_mock_agent()
    app = BitzApp(agent=agent)
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.text = "/theme nonexistent"
        await pilot.press("enter")
        await pilot.pause(delay=0.3)
        msgs = app.query_one(ChatLog).query(AssistantMessage)
        assert len(msgs) >= 1
        last_msg = msgs.last()
        assert "未知主题" in last_msg._content


@pytest.mark.asyncio
async def test_command_unknown():
    """测试未知命令显示错误信息"""
    agent = make_mock_agent()
    app = BitzApp(agent=agent)
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.text = "/unknown"
        await pilot.press("enter")
        await pilot.pause(delay=0.3)
        msgs = app.query_one(ChatLog).query(AssistantMessage)
        assert len(msgs) >= 1
        last_msg = msgs.last()
        assert "未知命令" in last_msg._content
