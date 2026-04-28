import pytest
from textual.app import App, ComposeResult
from tui.widgets.status import StatusBar


class StatusTestApp(App):
    CSS = ""

    def compose(self) -> ComposeResult:
        yield StatusBar()


@pytest.mark.asyncio
async def test_statusbar_composes():
    app = StatusTestApp()
    async with app.run_test() as pilot:
        bar = app.query_one(StatusBar)
        assert bar is not None


@pytest.mark.asyncio
async def test_statusbar_default_values():
    app = StatusTestApp()
    async with app.run_test() as pilot:
        bar = app.query_one(StatusBar)
        assert bar.model_name == ""
        assert bar.step_count == 0
        assert bar.input_tokens == 0
        assert bar.output_tokens == 0


@pytest.mark.asyncio
async def test_statusbar_update_model():
    app = StatusTestApp()
    async with app.run_test() as pilot:
        bar = app.query_one(StatusBar)
        bar.update_model("claude-sonnet-4-6")
        await pilot.pause()
        assert bar.model_name == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_statusbar_update_steps():
    app = StatusTestApp()
    async with app.run_test() as pilot:
        bar = app.query_one(StatusBar)
        bar.update_steps(5)
        await pilot.pause()
        assert bar.step_count == 5


@pytest.mark.asyncio
async def test_statusbar_update_tokens():
    app = StatusTestApp()
    async with app.run_test() as pilot:
        bar = app.query_one(StatusBar)
        bar.update_tokens(1500, 856)
        await pilot.pause()
        assert bar.input_tokens == 1500
        assert bar.output_tokens == 856


@pytest.mark.asyncio
async def test_statusbar_format_tokens():
    app = StatusTestApp()
    async with app.run_test() as pilot:
        bar = app.query_one(StatusBar)
        assert bar._format_tokens(500) == "500"
        assert bar._format_tokens(1500) == "1.5k"
        assert bar._format_tokens(1000) == "1.0k"
