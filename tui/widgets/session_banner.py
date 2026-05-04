from __future__ import annotations

from textual.widgets import Static
from textual.message import Message
from textual.binding import Binding
from rich.text import Text


class SessionRestoreBanner(Static):
    """启动时提示恢复上次会话。"""

    can_focus = True

    DEFAULT_CSS = """
    SessionRestoreBanner {
        color: $text-muted;
        margin: 0 1;
        height: 1;
    }
    """

    BINDINGS = [
        Binding("r", "restore", "恢复会话"),
        Binding("escape", "skip", "跳过"),
    ]

    class Restore(Message):
        pass

    class Skip(Message):
        pass

    def __init__(self, title: str, turn_count: int, **kwargs) -> None:
        self._title = title
        self._turn_count = turn_count
        super().__init__(**kwargs)

    def render(self) -> Text:
        return Text.assemble(
            Text("检测到上次会话: ", style="dim"),
            Text(f'"{self._title}" ', style="cyan"),
            Text(f"({self._turn_count}轮) ", style="dim"),
            Text("[r恢复 / Esc跳过]", style="bold"),
        )

    def action_restore(self) -> None:
        self.post_message(self.Restore())
        self.remove()

    def action_skip(self) -> None:
        self.post_message(self.Skip())
        self.remove()
