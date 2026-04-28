import pytest
from textual.app import App, ComposeResult
from tui.widgets.input import InputBar


class InputTestApp(App):
    CSS = ""

    def compose(self) -> ComposeResult:
        yield InputBar()


@pytest.mark.asyncio
async def test_inputbar_composes():
    app = InputTestApp()
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        assert bar is not None


@pytest.mark.asyncio
async def test_inputbar_emits_message_submitted():
    submitted = []

    class HandlerApp(App):
        CSS = ""

        def compose(self) -> ComposeResult:
            yield InputBar()

        def on_input_bar_message_submitted(self, event: InputBar.MessageSubmitted) -> None:
            submitted.append(event.text)
            self.exit()

    app = HandlerApp()
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.value = "hello"
        await pilot.press("enter")
        await pilot.pause()

    assert submitted == ["hello"]


@pytest.mark.asyncio
async def test_inputbar_clears_after_submit():
    app = InputTestApp()
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.value = "hello"
        await pilot.press("enter")
        await pilot.pause()
        assert bar._input.value == ""


@pytest.mark.asyncio
async def test_inputbar_navigates_history():
    app = InputTestApp()
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._history = ["first", "second"]
        bar._history_index = 2

        await pilot.press("up")
        await pilot.pause()
        assert bar._input.value == "second"

        await pilot.press("up")
        await pilot.pause()
        assert bar._input.value == "first"

        await pilot.press("down")
        await pilot.pause()
        assert bar._input.value == "second"


@pytest.mark.asyncio
async def test_inputbar_esc_fires_cancel():
    cancelled = []

    class CancelApp(App):
        CSS = ""

        def compose(self) -> ComposeResult:
            yield InputBar()

        def on_input_bar_cancel_requested(self, event: InputBar.CancelRequested) -> None:
            cancelled.append(True)
            self.exit()

    app = CancelApp()
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()

    assert len(cancelled) == 1


@pytest.mark.asyncio
async def test_inputbar_theme_command():
    theme_requested = []

    class ThemeApp(App):
        CSS = ""

        def compose(self) -> ComposeResult:
            yield InputBar()

        def on_input_bar_theme_change_requested(self, event: InputBar.ThemeChangeRequested) -> None:
            theme_requested.append(True)
            self.exit()

    app = ThemeApp()
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.value = "/theme"
        await pilot.press("enter")
        await pilot.pause()

    assert len(theme_requested) == 1
