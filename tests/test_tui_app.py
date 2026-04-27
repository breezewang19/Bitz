import pytest
from unittest.mock import MagicMock
from textual.app import App, ComposeResult
from tui.app import BitzApp
from tui.widgets.chat import ChatLog, UserMessage, AssistantMessage, ThinkingIndicator
from tui.widgets.input import InputBar
from tui.widgets.status import StatusBar


@pytest.mark.asyncio
async def test_app_composes_all_widgets():
    mock_agent = MagicMock()
    mock_agent.model = "test"
    app = BitzApp(agent=mock_agent)
    async with app.run_test() as pilot:
        assert app.query_one(ChatLog) is not None
        assert app.query_one(InputBar) is not None
        assert app.query_one(StatusBar) is not None


@pytest.mark.asyncio
async def test_submit_input_calls_agent():
    mock_agent = MagicMock()
    mock_agent.run.return_value = "Test response"
    mock_agent._pending_confirm = None
    app = BitzApp(agent=mock_agent)
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar._input.value = "hello"
        await pilot.press("enter")
        await pilot.pause(delay=0.5)

    mock_agent.run.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_sets_event_when_busy():
    """ESC should cancel only when agent is running (busy state)."""
    mock_agent = MagicMock()
    mock_agent.run.return_value = "ok"
    app = BitzApp(agent=mock_agent)
    async with app.run_test() as pilot:
        bar = app.query_one(InputBar)
        bar.set_busy(True)
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app._cancel_event.is_set()


@pytest.mark.asyncio
async def test_escape_does_not_cancel_when_idle():
    """ESC should not cancel when agent is idle."""
    mock_agent = MagicMock()
    mock_agent.run.return_value = "ok"
    app = BitzApp(agent=mock_agent)
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
        assert not app._cancel_event.is_set()


@pytest.mark.asyncio
async def test_thinking_shows_and_hides():
    mock_agent = MagicMock()
    mock_agent.run.return_value = "Done"
    app = BitzApp(agent=mock_agent)
    async with app.run_test() as pilot:
        chat = app.query_one(ChatLog)
        chat.show_thinking()
        await pilot.pause()
        assert len(chat.query(ThinkingIndicator)) == 1
        chat.hide_thinking()
        await pilot.pause()
        assert len(chat.query(ThinkingIndicator)) == 0
