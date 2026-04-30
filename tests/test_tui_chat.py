import pytest
from textual.app import App, ComposeResult
from tui.widgets.chat import (
    ChatLog, UserMessage, AssistantMessage, ThinkingIndicator,
    format_tool_content, SubAgentCard,
)
from tui.widgets.tool_card import ToolCard


class ChatTestApp(App):
    CSS = """
    ChatLog {
        height: 20;
    }
    """

    def compose(self) -> ComposeResult:
        yield ChatLog()
        yield ThinkingIndicator()


@pytest.mark.asyncio
async def test_chatlog_composes():
    app = ChatTestApp()
    async with app.run_test() as pilot:
        chat = app.query_one(ChatLog)
        assert chat is not None


@pytest.mark.asyncio
async def test_add_user_message():
    app = ChatTestApp()
    async with app.run_test() as pilot:
        chat = app.query_one(ChatLog)
        chat.add_message("user", "Hello world")
        await pilot.pause()
        msgs = chat.query(UserMessage)
        assert len(msgs) == 1
        rendered = msgs.first().render()
        assert "> " in rendered.plain
        assert "Hello world" in rendered.plain


@pytest.mark.asyncio
async def test_add_assistant_message():
    app = ChatTestApp()
    async with app.run_test() as pilot:
        chat = app.query_one(ChatLog)
        chat.add_message("assistant", "Hi there")
        await pilot.pause()
        msgs = chat.query(AssistantMessage)
        assert len(msgs) == 1


@pytest.mark.asyncio
async def test_assistant_markdown_render():
    app = ChatTestApp()
    async with app.run_test() as pilot:
        chat = app.query_one(ChatLog)
        chat.add_message("assistant", "# Title\n\n**bold** text\n\n- item1\n- item2")
        await pilot.pause()
        msgs = chat.query(AssistantMessage)
        assert len(msgs) == 1
        from textual.widgets import Markdown as MarkdownWidget
        md = msgs.first().query_one(MarkdownWidget)
        assert md is not None


@pytest.mark.asyncio
async def test_thinking_indicator():
    app = ChatTestApp()
    async with app.run_test() as pilot:
        indicator = app.query_one(ThinkingIndicator)
        indicator.show()
        await pilot.pause()
        rendered = indicator.render()
        assert "Thinking" in rendered.plain


@pytest.mark.asyncio
async def test_thinking_cancel_state():
    app = ChatTestApp()
    async with app.run_test() as pilot:
        indicator = app.query_one(ThinkingIndicator)
        indicator.show()
        await pilot.pause()
        indicator.set_canceling()
        rendered = indicator.render()
        assert "Canceling" in rendered.plain


@pytest.mark.asyncio
async def test_thinking_indicator_hidden_by_default():
    app = ChatTestApp()
    async with app.run_test() as pilot:
        indicator = app.query_one(ThinkingIndicator)
        assert not indicator.has_class("visible")


@pytest.mark.asyncio
async def test_add_tool_message():
    app = ChatTestApp()
    async with app.run_test() as pilot:
        chat = app.query_one(ChatLog)
        chat.add_message("tool", "ls -la", tool_name="bash")
        await pilot.pause()
        cards = chat.query(ToolCard)
        assert len(cards) == 1
        assert cards.first()._tool_name == "bash"


@pytest.mark.asyncio
async def test_format_tool_content():
    assert format_tool_content("bash", {"command": "ls"}) == "ls"
    assert format_tool_content("read_file", {"path": "/tmp/f.py"}) == "/tmp/f.py"
    assert format_tool_content("write_file", {"path": "a.py", "content": "hello"}) == "a.py (5 chars)"
    assert format_tool_content("edit_file", {"path": "b.py"}) == "b.py"
    assert format_tool_content("glob", {"pattern": "*.py"}) == "*.py"
    assert format_tool_content("grep", {"pattern": "foo", "path": "src"}) == "foo in src"
    assert format_tool_content("fetch", {"url": "http://x"}) == "http://x"


@pytest.mark.asyncio
async def test_thinking_elapsed_display():
    app = ChatTestApp()
    async with app.run_test() as pilot:
        indicator = app.query_one(ThinkingIndicator)
        indicator.show()
        await pilot.pause()
        indicator.set_elapsed(3.2)
        rendered = indicator.render()
        assert "3.2s" in rendered.plain


@pytest.mark.asyncio
async def test_thinking_elapsed_over_60s():
    app = ChatTestApp()
    async with app.run_test() as pilot:
        indicator = app.query_one(ThinkingIndicator)
        indicator.show()
        await pilot.pause()
        indicator.set_elapsed(83.0)
        rendered = indicator.render()
        assert "1m 23s" in rendered.plain


@pytest.mark.asyncio
async def test_auto_scroll():
    app = ChatTestApp()
    async with app.run_test() as pilot:
        chat = app.query_one(ChatLog)
        for i in range(50):
            chat.add_message("user", f"Message {i}")
        await pilot.pause()
        assert chat.scroll_y > 0


@pytest.mark.asyncio
async def test_subagent_card_running():
    app = ChatTestApp()
    async with app.run_test() as pilot:
        card = SubAgentCard(task="review code", count=3)
        chat = app.query_one(ChatLog)
        chat.mount(card)
        await pilot.pause()
        rendered = card.render()
        assert "0/3" in rendered.plain
        assert "Running" in rendered.plain


@pytest.mark.asyncio
async def test_subagent_card_with_results():
    from agent.subagent import SubAgentResult
    app = ChatTestApp()
    async with app.run_test() as pilot:
        card = SubAgentCard(task="review code", count=3)
        chat = app.query_one(ChatLog)
        chat.mount(card)
        await pilot.pause()

        card.add_result(SubAgentResult(success=True, output="ok", steps=3, elapsed=5.0))
        card.add_result(SubAgentResult(success=False, output="", error="timeout", steps=0, elapsed=2.0))
        await pilot.pause()

        rendered = card.render()
        assert "2/3" in rendered.plain
        assert "✓" in rendered.plain
        assert "✗" in rendered.plain
