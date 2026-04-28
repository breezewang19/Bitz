from __future__ import annotations

from textual.widget import Widget
from textual.widgets import Input
from textual.message import Message
from textual.events import Key


class InputBar(Widget):
    DEFAULT_CSS = """
    InputBar {
        height: 3;
        background: #282a36;
        border-top: solid #44475a;
        padding: 0 1;
        layout: horizontal;
    }

    InputBar Input {
        background: #1e1e2e;
        border: none;
        width: 1fr;
    }
    """

    class MessageSubmitted(Message):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    class CancelRequested(Message):
        pass

    class ThemeChangeRequested(Message):
        pass

    class CommandSubmitted(Message):
        """斜杠命令消息，当输入以 / 开头时触发。"""

        def __init__(self, command: str, args: str = "") -> None:
            super().__init__()
            self.command = command  # 命令名（不含 /）
            self.args = args        # 命令参数

    def __init__(self) -> None:
        super().__init__()
        self._history: list[str] = []
        self._history_index: int = 0
        self._saved_draft: str = ""
        self._busy: bool = False

    def compose(self):
        yield Input(placeholder="Type your message... (ESC to cancel)", id="chat-input")

    @property
    def _input(self) -> Input:
        return self.query_one("#chat-input", Input)

    def on_key(self, event: Key) -> None:
        if event.key == "enter":
            text = self._input.value.strip()
            if text:
                self._history.append(text)
                self._history_index = len(self._history)
                self._input.value = ""
                if text.startswith("/"):
                    # 斜杠命令：解析命令名和参数
                    parts = text[1:].split(None, 1)
                    command = parts[0] if parts else ""
                    args = parts[1] if len(parts) > 1 else ""
                    # /theme 仍发送 ThemeChangeRequested 以保持向后兼容
                    if command == "theme" and not args:
                        self.post_message(self.ThemeChangeRequested())
                    else:
                        self.post_message(self.CommandSubmitted(command, args))
                else:
                    self.post_message(self.MessageSubmitted(text))
            event.prevent_default()
        elif event.key == "up":
            if self._input.value == "" or self._history_index > 0:
                self._navigate_history(-1)
                event.prevent_default()
        elif event.key == "down":
            self._navigate_history(1)
            event.prevent_default()
        elif event.key == "escape":
            self.post_message(self.CancelRequested())
            event.prevent_default()

    def _navigate_history(self, direction: int) -> None:
        if not self._history:
            return

        if direction == -1 and self._history_index == len(self._history):
            self._saved_draft = self._input.value

        new_index = self._history_index + direction
        if new_index < 0 or new_index > len(self._history):
            return

        self._history_index = new_index

        if self._history_index == len(self._history):
            self._input.value = self._saved_draft
        else:
            self._input.value = self._history[self._history_index]

    def set_busy(self, busy: bool) -> None:
        """Toggle between busy and idle states."""
        self._busy = busy
        self._input.disabled = busy
        self._input.placeholder = "等待中，当前任务未结束..." if busy else "输入消息..."
        if not busy:
            self._input.focus()

    def focus_input(self) -> None:
        self._input.focus()
