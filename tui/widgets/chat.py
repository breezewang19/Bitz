from __future__ import annotations

from textual.widgets import Static
from textual.widgets import Markdown as MarkdownWidget
from textual.message import Message
from textual.containers import VerticalScroll
from rich.text import Text

from tui.theme import COLORS
from tui.widgets.tool_card import ToolCard


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
        self._streaming = False
        self._stream_dirty = False

    def compose(self):
        yield MarkdownWidget(self._content)

    def update_content(self, text: str) -> None:
        """更新 Markdown 内容。"""
        self._content = text
        try:
            md = self.query_one(MarkdownWidget)
            md.update(text)
        except Exception:
            pass

    def start_streaming(self) -> None:
        """进入流式模式。"""
        self._streaming = True
        self._stream_dirty = False

    def append_content(self, text: str) -> None:
        """追加流式文本增量。"""
        self._content += text
        self._stream_dirty = True

    def flush_streaming(self) -> None:
        """刷新流式内容到 Markdown 渲染（由定时器调用）。"""
        if self._streaming and self._stream_dirty:
            self._stream_dirty = False
            try:
                md = self.query_one(MarkdownWidget)
                md.update(self._content)
            except Exception:
                pass

    def finish_streaming(self) -> None:
        """结束流式模式：最终 Markdown 渲染。"""
        self._streaming = False
        self._stream_dirty = False
        try:
            md = self.query_one(MarkdownWidget)
            md.update(self._content)
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
        self._elapsed: float | None = None

    def render(self) -> Text:
        frame = self.SPINNER_FRAMES[self._frame % len(self.SPINNER_FRAMES)]
        parts = []
        if self._canceling:
            parts.append(Text(f"{frame} ", style=COLORS["error"]))
            parts.append(Text("[ESC] Canceling", style=COLORS["error"]))
        elif self._tool_name:
            parts.append(Text(f"{frame} ", style=COLORS["tool"]))
            parts.append(Text(f"Running ", style=COLORS["tool"]))
            parts.append(Text(f"[{self._tool_name}]", style=f"bold {COLORS['tool']}"))
        else:
            parts.append(Text(f"{frame} ", style=COLORS["thinking"]))
            parts.append(Text("Thinking", style=COLORS["thinking"]))
        if self._elapsed is not None:
            parts.append(Text(f" {self._format_elapsed(self._elapsed)}", style=COLORS["muted"]))
        return Text.assemble(*parts)

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        if seconds >= 60:
            m = int(seconds // 60)
            s = int(seconds % 60)
            return f"{m}m {s}s"
        return f"{seconds:.1f}s"

    def set_elapsed(self, seconds: float) -> None:
        self._elapsed = seconds
        self.refresh()

    def advance(self) -> None:
        self._frame += 1
        self.refresh()

    def set_canceling(self) -> None:
        self._canceling = True
        self.refresh()

    def set_tool(self, tool_name: str | None) -> None:
        self._tool_name = tool_name
        self.refresh()


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


class TurnTiming(Static):
    """每轮对话耗时汇总，显示在 assistant 消息下方。"""

    DEFAULT_CSS = """
    TurnTiming {
        color: $text-muted;
        margin: 0 0 1 0;
        padding: 0 1;
        height: auto;
    }
    """

    def __init__(self, seconds: float) -> None:
        super().__init__()
        self._seconds = seconds

    def render(self) -> Text:
        return Text(f"Worked for {self._format_elapsed(self._seconds)}", style=COLORS["muted"])

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        if seconds >= 3600:
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            return f"{h}h {m}m {s}s"
        if seconds >= 60:
            m = int(seconds // 60)
            s = int(seconds % 60)
            return f"{m}m {s}s"
        return f"{seconds:.1f}s"


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
        self._streaming_message: AssistantMessage | None = None

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

    def start_streaming_message(self) -> None:
        """创建空的流式 AssistantMessage。"""
        if self._thinking_indicator is not None:
            self._thinking_indicator.remove()
            self._thinking_indicator = None
        self._streaming_message = AssistantMessage("")
        self._streaming_message.start_streaming()
        self.mount(self._streaming_message)
        self.call_after_refresh(self._scroll_to_bottom)

    def finish_streaming_message(self) -> None:
        """完成流式消息，切换回 Markdown 渲染。"""
        if self._streaming_message is not None:
            if self._streaming_message._content.strip():
                # 有内容：切换回 Markdown 渲染
                self._streaming_message.finish_streaming()
            else:
                # 无内容（错误/取消）：移除空消息
                self._streaming_message.remove()
            self._streaming_message = None

    def _scroll_to_bottom(self) -> None:
        self.scroll_end(animate=False)
