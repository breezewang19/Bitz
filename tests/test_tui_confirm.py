import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static
from tui.widgets.confirm import ConfirmPrompt


class ConfirmTestApp(App):
    CSS = ""

    def compose(self) -> ComposeResult:
        yield Static("background")

    def on_mount(self) -> None:
        prompt = ConfirmPrompt(tool_name="bash", tool_args="rm -rf /")
        self.query_one(Static).mount(prompt)


@pytest.mark.asyncio
async def test_confirm_prompt_shows_tool_info():
    app = ConfirmTestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        prompts = app.query(ConfirmPrompt)
        assert len(prompts) == 1
        rendered = prompts.first().render()
        assert "bash" in rendered.plain


@pytest.mark.asyncio
async def test_confirm_prompt_shows_approve_deny():
    app = ConfirmTestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        rendered = app.query_one(ConfirmPrompt).render()
        assert "批准" in rendered.plain or "✓" in rendered.plain
        assert "拒绝" in rendered.plain or "✗" in rendered.plain


@pytest.mark.asyncio
async def test_confirm_prompt_default_allow():
    app = ConfirmTestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        prompt = app.query_one(ConfirmPrompt)
        assert prompt.selected is True


@pytest.mark.asyncio
async def test_confirm_prompt_select_deny():
    app = ConfirmTestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        prompt = app.query_one(ConfirmPrompt)
        prompt.select_deny()
        assert prompt.selected is False


@pytest.mark.asyncio
async def test_confirm_prompt_select_allow():
    app = ConfirmTestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        prompt = app.query_one(ConfirmPrompt)
        prompt.select_deny()
        prompt.select_allow()
        assert prompt.selected is True