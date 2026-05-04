"""SessionRestoreBanner TUI 测试"""
import pytest
from textual.app import App, ComposeResult
from tui.widgets.session_banner import SessionRestoreBanner


class BannerTestApp(App):
    CSS = ""

    def compose(self) -> ComposeResult:
        yield SessionRestoreBanner(title="Test Session", turn_count=5)

    def on_session_restore_banner_restore(self, event):
        self._result = "restored"

    def on_session_restore_banner_skip(self, event):
        self._result = "skipped"


@pytest.mark.asyncio
async def test_banner_restore():
    """按 r 触发 Restore 消息"""
    app = BannerTestApp()
    app._result = None
    async with app.run_test() as pilot:
        await pilot.pause()
        banner = app.query_one(SessionRestoreBanner)
        banner.focus()
        await pilot.press("r")
        await pilot.pause()
        assert app._result == "restored"


@pytest.mark.asyncio
async def test_banner_skip():
    """按 Escape 触发 Skip 消息"""
    app = BannerTestApp()
    app._result = None
    async with app.run_test() as pilot:
        await pilot.pause()
        banner = app.query_one(SessionRestoreBanner)
        banner.focus()
        await pilot.press("escape")
        await pilot.pause()
        assert app._result == "skipped"


@pytest.mark.asyncio
async def test_banner_render_content():
    """渲染内容包含标题和轮数"""
    app = BannerTestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        banner = app.query_one(SessionRestoreBanner)
        rendered = banner.render()
        assert "Test Session" in rendered.plain
        assert "5" in rendered.plain
