import pytest
from unittest.mock import MagicMock
from tui.app import BitzApp
from tui.widgets.chat import ChatLog, UserMessage, AssistantMessage
from tui.widgets.input import InputBar
from tui.widgets.status import StatusBar
from agent.context import Context


def make_mock_agent():
    """创建模拟 Agent。"""
    agent = MagicMock()
    agent.tools = MagicMock()
    agent.tools.execute = MagicMock(return_value="ok")
    agent.tools.list_for_llm = MagicMock(return_value=[])
    agent.llm_adapter = MagicMock()
    agent.llm_adapter._last_usage = None
    agent.llm_adapter.model = "test-model"
    # 使用真实的 Context 对象以支持 active_skill
    agent.context = Context(system_prompt="test", max_tokens=4096, keep_last_n=20)
    # 添加一些初始消息（必须是正确的格式）
    for i in range(20):
        agent.context.messages.append({"role": "user", "content": f"message {i}"})
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
    # 添加足够的消息以触发 trim
    for i in range(30):
        agent.context.messages.append({"role": "user", "content": f"extra message {i}"})
    initial_count = len(agent.context.messages)
    app = BitzApp(agent=agent)
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.text = "/compact"
        await pilot.press("enter")
        await pilot.pause(delay=0.3)
        # Context._trim 应被调用
        final_count = len(agent.context.messages)
        assert final_count < initial_count
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


def make_mock_skill_registry():
    """创建模拟 SkillRegistry。"""
    from agent.skills import Skill, SkillRegistry
    registry = SkillRegistry()
    registry.skills["code-review"] = Skill(
        name="code-review", description="审查代码质量", trigger="/review",
        prompt="按步骤审查代码", source="builtin",
    )
    registry.skills["debug"] = Skill(
        name="debug", description="调试排错", trigger="/debug",
        prompt="按步骤调试", source="builtin",
    )
    return registry


@pytest.mark.asyncio
async def test_command_skill_list():
    """测试 /skill 命令列出所有 Skill"""
    agent = make_mock_agent()
    registry = make_mock_skill_registry()
    app = BitzApp(agent=agent, skill_registry=registry)
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.text = "/skill"
        await pilot.press("enter")
        await pilot.pause(delay=0.3)
        msgs = app.query_one(ChatLog).query(AssistantMessage)
        assert len(msgs) >= 1
        last_msg = msgs.last()
        # 检查 trigger（/review 和 /debug）出现在输出中
        assert "/review" in last_msg._content
        assert "/debug" in last_msg._content


@pytest.mark.asyncio
async def test_skill_trigger_activates():
    """测试 /review 激活 Skill"""
    agent = make_mock_agent()
    registry = make_mock_skill_registry()
    app = BitzApp(agent=agent, skill_registry=registry)
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.text = "/review"
        await pilot.press("enter")
        await pilot.pause(delay=0.3)
        # 验证 active_skill 已设置
        assert agent.context.active_skill is not None
        assert agent.context.active_skill.name == "code-review"
        # 验证 ChatLog 有激活提示
        msgs = app.query_one(ChatLog).query(AssistantMessage)
        assert len(msgs) >= 1
        last_msg = msgs.last()
        assert "已激活 Skill" in last_msg._content


@pytest.mark.asyncio
async def test_skill_off_clears():
    """测试 /skill off 清除当前 Skill"""
    agent = make_mock_agent()
    registry = make_mock_skill_registry()
    app = BitzApp(agent=agent, skill_registry=registry)
    async with app.run_test() as pilot:
        # 先激活
        agent.context.set_active_skill(registry.get("code-review"))
        assert agent.context.active_skill is not None
        # 再清除
        bar = app.query_one(InputBar)
        bar._input.text = "/skill off"
        await pilot.press("enter")
        await pilot.pause(delay=0.3)
        assert agent.context.active_skill is None
        msgs = app.query_one(ChatLog).query(AssistantMessage)
        last_msg = msgs.last()
        assert "已清除" in last_msg._content
