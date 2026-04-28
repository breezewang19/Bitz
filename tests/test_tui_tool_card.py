import pytest
from textual.app import App, ComposeResult
from textual.widgets import Collapsible
from tui.widgets.tool_card import ToolCard


class ToolCardTestApp(App):
    CSS = ""

    def compose(self) -> ComposeResult:
        yield ToolCard(tool_name="bash", args_summary="ls -la")


@pytest.mark.asyncio
async def test_tool_card_composes():
    app = ToolCardTestApp()
    async with app.run_test() as pilot:
        card = app.query_one(ToolCard)
        assert card is not None


@pytest.mark.asyncio
async def test_tool_card_initial_running():
    app = ToolCardTestApp()
    async with app.run_test() as pilot:
        card = app.query_one(ToolCard)
        collapsible = card.query_one(Collapsible)
        # 运行中默认展开
        assert collapsible.collapsed is False
        # 标题包含工具名
        assert "bash" in collapsible.title
        assert "⟳" in collapsible.title


@pytest.mark.asyncio
async def test_tool_card_set_success():
    app = ToolCardTestApp()
    async with app.run_test() as pilot:
        card = app.query_one(ToolCard)
        card.set_success("file1.py\nfile2.py")
        await pilot.pause()
        collapsible = card.query_one(Collapsible)
        # 成功后折叠
        assert collapsible.collapsed is True
        assert "✓" in collapsible.title


@pytest.mark.asyncio
async def test_tool_card_set_error():
    app = ToolCardTestApp()
    async with app.run_test() as pilot:
        card = app.query_one(ToolCard)
        card.set_error("command not found")
        await pilot.pause()
        collapsible = card.query_one(Collapsible)
        # 错误后展开
        assert collapsible.collapsed is False
        assert "✗" in collapsible.title


@pytest.mark.asyncio
async def test_tool_card_args_summary_truncated():
    # 测试构造函数截断长参数
    long_args = "a" * 100
    card = ToolCard(tool_name="test", args_summary=long_args)
    # 构造函数应该截断到60字符
    assert len(card._args_summary) <= 60


@pytest.mark.asyncio
async def test_tool_card_set_diff():
    """set_diff 应该显示 diff 内容并展开"""
    app = ToolCardTestApp()
    async with app.run_test() as pilot:
        card = app.query_one(ToolCard)
        diff_text = "--- a/file.py\n+++ b/file.py\n@@ -1,3 +1,3 @@\n-old line\n+new line\n context line\n"
        card.set_diff(diff_text)
        await pilot.pause()
        collapsible = card.query_one(Collapsible)
        # diff 模式下应该展开
        assert collapsible.collapsed is False
        # 状态应该是 success
        assert card._status == "success"
