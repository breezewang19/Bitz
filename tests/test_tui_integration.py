import pytest
from unittest.mock import MagicMock
from tui.app import BitzApp
from tui.widgets.chat import ChatLog, UserMessage, AssistantMessage, ThinkingIndicator
from tui.widgets.input import InputBar
from tui.widgets.status import StatusBar


@pytest.mark.asyncio
async def test_full_conversation_flow():
    """Test: user types -> thinking shows -> agent responds -> message appears"""
    mock_agent = MagicMock()
    mock_agent.run.return_value = "Hello! I'm Bitz."
    mock_agent._pending_confirm = None

    app = BitzApp(agent=mock_agent)
    async with app.run_test() as pilot:
        chat = app.query_one(ChatLog)
        input_bar = app.query_one(InputBar)
        status = app.query_one(StatusBar)

        input_bar._input.value = "Hi there"
        await pilot.press("enter")
        await pilot.pause(delay=0.5)

        user_msgs = chat.query(UserMessage)
        assert len(user_msgs) >= 1

        thinking = chat.query(ThinkingIndicator)
        assert len(thinking) == 0

        assistant_msgs = chat.query(AssistantMessage)
        assert len(assistant_msgs) >= 1

        assert status.step_count == 1


@pytest.mark.asyncio
async def test_cancel_during_agent_run():
    """Test: ESC cancels the agent run"""
    import threading

    mock_agent = MagicMock()

    def slow_run(*args, **kwargs):
        cancel_event = args[1] if len(args) > 1 else kwargs.get("cancel_event")
        if cancel_event:
            cancel_event.wait(timeout=2)
        return "should not appear"

    mock_agent.run.side_effect = slow_run
    mock_agent._pending_confirm = None

    app = BitzApp(agent=mock_agent)
    async with app.run_test() as pilot:
        input_bar = app.query_one(InputBar)
        input_bar._input.value = "long query"
        await pilot.press("enter")
        await pilot.pause(delay=0.2)

        await pilot.press("escape")
        await pilot.pause(delay=0.5)

        assert app._cancel_event.is_set()


@pytest.mark.asyncio
async def test_resize_updates_layout():
    """Test: app handles different terminal sizes without crash"""
    mock_agent = MagicMock()
    mock_agent.run.return_value = "ok"
    mock_agent._pending_confirm = None

    # Test with small terminal size
    app = BitzApp(agent=mock_agent)
    async with app.run_test(size=(80, 24)) as pilot:
        chat = app.query_one(ChatLog)
        assert chat is not None

    # Test with large terminal size
    app2 = BitzApp(agent=mock_agent)
    async with app2.run_test(size=(120, 40)) as pilot:
        chat = app2.query_one(ChatLog)
        assert chat is not None
