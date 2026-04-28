import pytest
from textual.app import App, ComposeResult
from tui.widgets.input import InputBar
from tui.widgets.command_popup import CommandPopup


class CommandTestApp(App):
    CSS = ""

    def compose(self) -> ComposeResult:
        yield InputBar()


@pytest.mark.asyncio
async def test_command_popup_shows_on_slash():
    """输入 / 时显示命令补全列表"""
    app = CommandTestApp()
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.text = "/"
        bar._check_command_completion()
        await pilot.pause()
        popups = app.query(CommandPopup)
        assert len(popups) >= 1


@pytest.mark.asyncio
async def test_command_popup_filters():
    """输入 /cl 时只显示匹配的命令"""
    app = CommandTestApp()
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.text = "/cl"
        bar._check_command_completion()
        await pilot.pause()
        popup = app.query_one(CommandPopup)
        commands = popup._filtered_commands
        assert "/clear" in commands
        assert "/help" not in commands
        assert "/theme" not in commands


@pytest.mark.asyncio
async def test_command_popup_tab_completes():
    """Tab 键补全当前匹配的命令"""
    app = CommandTestApp()
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.text = "/cle"
        bar._check_command_completion()
        await pilot.pause()
        await pilot.press("tab")
        await pilot.pause()
        assert bar._input.text == "/clear "


@pytest.mark.asyncio
async def test_command_popup_esc_closes():
    """ESC 关闭命令补全弹出列表"""
    app = CommandTestApp()
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.text = "/"
        bar._check_command_completion()
        await pilot.pause()
        popups = app.query(CommandPopup)
        assert len(popups) >= 1
        await pilot.press("escape")
        await pilot.pause()
        popups = app.query(CommandPopup)
        assert len(popups) == 0
        assert bar._command_popup is None


@pytest.mark.asyncio
async def test_command_popup_arrow_navigation():
    """上下键在补全列表中移动高亮"""
    app = CommandTestApp()
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.text = "/"
        bar._check_command_completion()
        await pilot.pause()
        popup = app.query_one(CommandPopup)
        assert popup._highlighted == 0
        await pilot.press("down")
        await pilot.pause()
        assert popup._highlighted == 1
        await pilot.press("up")
        await pilot.pause()
        assert popup._highlighted == 0
