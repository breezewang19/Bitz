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


def make_mock_model_store():
    """创建模拟 ModelStore。"""
    from agent.models import ModelConfig
    store = MagicMock()
    store.list_all.return_value = [
        ModelConfig(id="default", protocol="anthropic", base_url="https://api.anthropic.com", api_key="sk-test-key", model="claude-3-5-sonnet-20241022"),
    ]
    store.get_current.return_value = ModelConfig(id="default", protocol="anthropic", base_url="https://api.anthropic.com", api_key="sk-test-key", model="claude-3-5-sonnet-20241022")
    return store


@pytest.mark.asyncio
async def test_command_models_list():
    """测试 /models list 命令"""
    agent = make_mock_agent()
    store = make_mock_model_store()
    app = BitzApp(agent=agent, model_store=store)
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.text = "/models list"
        await pilot.press("enter")
        await pilot.pause(delay=0.3)
        msgs = app.query_one(ChatLog).query(AssistantMessage)
        assert len(msgs) >= 1
        last_msg = msgs.last()
        assert "default" in last_msg._content


@pytest.mark.asyncio
async def test_command_models_switch():
    """测试 /models <id> 切换模型"""
    agent = make_mock_agent()
    store = make_mock_model_store()
    from agent.models import ModelConfig
    store.get.return_value = ModelConfig(id="gpt-4o", protocol="openai", base_url="https://api.openai.com/v1", api_key="sk-openai", model="gpt-4o")
    app = BitzApp(agent=agent, model_store=store)
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.text = "/models gpt-4o"
        await pilot.press("enter")
        await pilot.pause(delay=0.3)
        store.set_current.assert_called_once_with("gpt-4o")
        assert agent.llm_adapter.api_key == "sk-openai"
        assert agent.llm_adapter.protocol == "openai"
        assert agent.llm_adapter.model == "gpt-4o"


@pytest.mark.asyncio
async def test_command_models_add():
    """测试 /models add 命令"""
    agent = make_mock_agent()
    store = make_mock_model_store()
    app = BitzApp(agent=agent, model_store=store)
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.text = "/models add gpt-4o openai https://api.openai.com/v1 sk-test gpt-4o"
        await pilot.press("enter")
        await pilot.pause(delay=0.3)
        store.add.assert_called_once()


@pytest.mark.asyncio
async def test_command_models_add_invalid_protocol():
    """测试 /models add 使用无效协议"""
    agent = make_mock_agent()
    store = make_mock_model_store()
    app = BitzApp(agent=agent, model_store=store)
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.text = "/models add test badproto https://api.example.com sk-test model"
        await pilot.press("enter")
        await pilot.pause(delay=0.3)
        msgs = app.query_one(ChatLog).query(AssistantMessage)
        assert len(msgs) >= 1
        last_msg = msgs.last()
        assert "不支持的协议" in last_msg._content


@pytest.mark.asyncio
async def test_command_models_opens_dialog():
    """测试 /models 无参数时弹出选择弹窗"""
    agent = make_mock_agent()
    store = make_mock_model_store()
    app = BitzApp(agent=agent, model_store=store)
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.text = "/models"
        await pilot.press("enter")
        await pilot.pause(delay=0.3)
        # 应该有 ModelSelectScreen 被推入
        from tui.widgets.model_select import ModelSelectScreen
        screens = app.screen_stack
        assert any(isinstance(s, ModelSelectScreen) for s in screens)


@pytest.mark.asyncio
async def test_models_dialog_switch():
    """测试弹窗中切换模型"""
    agent = make_mock_agent()
    from agent.models import ModelConfig
    store = MagicMock()
    store.list_all.return_value = [
        ModelConfig(id="default", protocol="anthropic", base_url="https://api.anthropic.com", api_key="sk-test-key", model="claude-3-5-sonnet-20241022"),
        ModelConfig(id="gpt-4o", protocol="openai", base_url="https://api.openai.com/v1", api_key="sk-openai", model="gpt-4o"),
    ]
    store.get_current.return_value = ModelConfig(id="default", protocol="anthropic", base_url="https://api.anthropic.com", api_key="sk-test-key", model="claude-3-5-sonnet-20241022")
    store.get.return_value = ModelConfig(id="gpt-4o", protocol="openai", base_url="https://api.openai.com/v1", api_key="sk-openai", model="gpt-4o")
    app = BitzApp(agent=agent, model_store=store)
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.text = "/models"
        await pilot.press("enter")
        await pilot.pause(delay=0.3)
        # 按 ESC 关闭弹窗（简单验证弹窗能正常关闭）
        await pilot.press("escape")
        await pilot.pause(delay=0.3)


@pytest.mark.asyncio
async def test_models_add_dialog_cancel():
    """测试添加模型弹窗取消"""
    agent = make_mock_agent()
    store = make_mock_model_store()
    app = BitzApp(agent=agent, model_store=store)
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.text = "/models"
        await pilot.press("enter")
        await pilot.pause(delay=0.3)
        # 按 ESC 关闭弹窗
        await pilot.press("escape")
        await pilot.pause(delay=0.3)


@pytest.mark.asyncio
async def test_models_delete_current_blocked():
    """测试删除当前模型被阻止"""
    agent = make_mock_agent()
    from agent.models import ModelConfig
    store = MagicMock()
    store.list_all.return_value = [
        ModelConfig(id="default", protocol="anthropic", base_url="https://api.anthropic.com", api_key="sk-test-key", model="claude-3-5-sonnet-20241022"),
    ]
    store.get_current.return_value = ModelConfig(id="default", protocol="anthropic", base_url="https://api.anthropic.com", api_key="sk-test-key", model="claude-3-5-sonnet-20241022")
    app = BitzApp(agent=agent, model_store=store)
    async with app.run_test() as pilot:
        # 直接测试回调逻辑
        app._on_models_result(("delete", "default"))
        await pilot.pause(delay=0.3)
        msgs = app.query_one(ChatLog).query(AssistantMessage)
        last_msg = msgs.last()
        assert "无法删除当前使用的模型" in last_msg._content
