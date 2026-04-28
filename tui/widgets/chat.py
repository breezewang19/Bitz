from __future__ import annotations

import shutil
import unicodedata

from textual.widgets import Static
from textual.widgets import Markdown as MarkdownWidget
from textual.message import Message
from textual.containers import VerticalScroll
from rich.text import Text
from rich.console import Console

from tui.theme import COLORS
from tui.widgets.tool_card import ToolCard


def _display_width(s: str) -> int:
    w = 0
    for ch in s:
        if unicodedata.east_asian_width(ch) in ('W', 'F'):
            w += 2
        else:
            w += 1
    return w


def _get_width() -> int:
    try:
        return shutil.get_terminal_size().columns
    except Exception:
        return 80


class UserMessage(Static):
    DEFAULT_CSS = """
    UserMessage {
        background: #1a1a2e;
        color: #50fa7b;
        margin: 0 0 1 0;
        padding: 0 1;
        width: 100%;
    }
    """

    def __init__(self, content: str) -> None:
        super().__init__()
        self._content = content

    def render(self) -> Text:
        return Text.assemble(
            Text("> ", style=f"bold {COLORS['user']}"),
            Text(self._content, style=COLORS['user']),
        )


class AssistantMessage(Static):
    DEFAULT_CSS = """
    AssistantMessage {
        color: $text;
        margin: 0 0 1 0;
        padding: 0 1;
        height: auto;
    }
    """

    def __init__(self, content: str) -> None:
        super().__init__()
        self._content = content

    def compose(self):
        yield MarkdownWidget(self._content)

    def update_content(self, text: str) -> None:
        """更新 Markdown 内容（供流式输出使用）。"""
        try:
            md = self.query_one(MarkdownWidget)
            md.update(text)
        except Exception:
            pass


class ThinkingIndicator(Static):
    DEFAULT_CSS = """
    ThinkingIndicator {
        color: #8be9fd;
        margin: 0 0 1 0;
        padding: 0 1;
    }
    """

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self) -> None:
        super().__init__()
        self._frame = 0
        self._canceling = False
        self._tool_name: str | None = None

    def render(self) -> Text:
        frame = self.SPINNER_FRAMES[self._frame % len(self.SPINNER_FRAMES)]
        if self._canceling:
            return Text.assemble(
                Text(f"{frame} ", style=COLORS["error"]),
                Text("[ESC] Canceling", style=COLORS["error"]),
            )
        if self._tool_name:
            return Text.assemble(
                Text(f"{frame} ", style=COLORS["tool"]),
                Text(f"Running ", style=COLORS["tool"]),
                Text(f"[{self._tool_name}]", style=f"bold {COLORS['tool']}"),
            )
        return Text.assemble(
            Text(f"{frame} ", style=COLORS["thinking"]),
            Text("Thinking", style=COLORS["thinking"]),
        )

    def advance(self) -> None:
        self._frame += 1
        self.refresh()

    def set_canceling(self) -> None:
        self._canceling = True
        self.refresh()

    def set_tool(self, tool_name: str | None) -> None:
        self._tool_name = tool_name
        self.refresh()


class ToolMessage(Static):
    DEFAULT_CSS = """
    ToolMessage {
        color: #bd93f9;
        margin: 0 0 1 0;
        padding: 0 1;
    }
    """

    def __init__(self, tool_name: str, content: str = "") -> None:
        super().__init__()
        self._tool_name = tool_name
        self._content = content

    def render(self) -> Text:
        return Text.assemble(
            Text(f"[{self._tool_name}]", style=f"bold {COLORS['tool']}"),
            Text(f" {self._content}", style=COLORS['tool']),
        )


def format_tool_content(name: str, args: dict | None = None) -> str:
    """Extract display content from tool args, matching original tui_core.py logic."""
    if args is None:
        args = {}
    if name == "bash":
        return args.get('command', '')
    elif name == "read_file":
        return args.get('path', '')
    elif name == "write_file":
        path = args.get('path', '')
        chars = len(args.get('content', ''))
        return f"{path} ({chars} chars)" if path else ''
    elif name == "edit_file":
        return args.get('path', '')
    elif name == "glob":
        return args.get('pattern', '')
    elif name == "grep":
        pattern = args.get('pattern', '')
        path = args.get('path', '.')
        return f"{pattern} in {path}"
    elif name == "fetch":
        return args.get('url', '')
    else:
        return str(args) if args else ''


class ChatLog(VerticalScroll):
    DEFAULT_CSS = """
    ChatLog {
        height: 1fr;
        scrollbar-size: 1 1;
        padding: 0 1;
    }
    """

    class MessageAdded(Message):
        def __init__(self, role: str, content: str) -> None:
            super().__init__()
            self.role = role
            self.content = content

    def __init__(self) -> None:
        super().__init__()
        self._thinking_indicator: ThinkingIndicator | None = None

    def add_message(self, role: str, content: str, tool_name: str = "") -> None:
        # Only hide thinking when assistant speaks — tool calls happen mid-thinking
        if role == "assistant" and self._thinking_indicator is not None:
            self._thinking_indicator.remove()
            self._thinking_indicator = None

        if role == "user":
            msg_widget = UserMessage(content)
        elif role == "assistant":
            msg_widget = AssistantMessage(content)
        elif role == "tool":
            msg_widget = ToolCard(tool_name=tool_name, args_summary=content)
        else:
            msg_widget = Static(content)

        self.mount(msg_widget)
        self.call_after_refresh(self._scroll_to_bottom)
        self.post_message(self.MessageAdded(role, content))

    def show_thinking(self) -> None:
        if self._thinking_indicator is not None:
            return
        self._thinking_indicator = ThinkingIndicator()
        self.mount(self._thinking_indicator)
        self.call_after_refresh(self._scroll_to_bottom)

    def update_thinking(self) -> None:
        if self._thinking_indicator is not None:
            self._thinking_indicator.advance()

    def set_canceling(self) -> None:
        if self._thinking_indicator is not None:
            self._thinking_indicator.set_canceling()

    def set_tool_running(self, tool_name: str | None) -> None:
        if self._thinking_indicator is not None:
            self._thinking_indicator.set_tool(tool_name)

    def hide_thinking(self) -> None:
        if self._thinking_indicator is not None:
            self._thinking_indicator.remove()
            self._thinking_indicator = None

    def _scroll_to_bottom(self) -> None:
        self.scroll_end(animate=False)
