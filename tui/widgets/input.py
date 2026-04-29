from __future__ import annotations

from textual.widget import Widget
from textual.widgets import TextArea
from textual.message import Message
from textual.events import Key

from tui.widgets.command_popup import CommandPopup


class MessageInput(TextArea):
    """自定义 TextArea，Enter 发送消息，Shift+Enter 换行。"""

    class Submit(Message):
        """用户按下 Enter 时发送。"""

        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    def on_key(self, event: Key) -> None:
        # Enter 发送，Shift+Enter 换行（TextArea 默认行为）
        # event.key == "enter" 表示普通 Enter，"shift+enter" 表示 Shift+Enter
        if event.key == "enter":
            text = self.text.strip()
            if text:
                self.post_message(self.Submit(text))
            event.prevent_default()
            event.stop()


class InputBar(Widget):
    DEFAULT_CSS = """
    InputBar {
        height: auto;
        min-height: 3;
        max-height: 10;
        background: $surface;
        border-top: solid $panel;
        padding: 0 1;
    }

    InputBar MessageInput {
        background: $background;
        border: none;
        height: auto;
        min-height: 1;
        max-height: 7;
    }
    """

    class MessageSubmitted(Message):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    class CancelRequested(Message):
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
        self._command_popup: CommandPopup | None = None

    def compose(self):
        yield MessageInput(id="chat-input", soft_wrap=True, show_line_numbers=False)

    @property
    def _input(self) -> MessageInput:
        return self.query_one("#chat-input", MessageInput)

    def on_message_input_submit(self, event: MessageInput.Submit) -> None:
        """处理 MessageInput 的 Submit 消息。"""
        text = event.text
        self._history.append(text)
        self._history_index = len(self._history)
        self._input.text = ""
        self._close_command_popup()
        if text.startswith("/"):
            parts = text[1:].split(None, 1)
            command = parts[0] if parts else ""
            args = parts[1] if len(parts) > 1 else ""
            self.post_message(self.CommandSubmitted(command, args))
        else:
            self.post_message(self.MessageSubmitted(text))

    def on_key(self, event: Key) -> None:
        # Tab 补全
        if event.key == "tab" and self._command_popup is not None:
            cmd = self._command_popup.select_highlighted()
            if cmd:
                self._input.text = cmd + " "
                self._close_command_popup()
                self._input.focus()
            event.prevent_default()
            return

        # 上下键：命令弹出列表或历史记录
        if event.key == "up":
            if self._command_popup is not None:
                self._command_popup.move_highlight(-1)
                event.prevent_default()
            elif self._history_index > 0:
                self._navigate_history(-1)
                event.prevent_default()
        elif event.key == "down":
            if self._command_popup is not None:
                self._command_popup.move_highlight(1)
                event.prevent_default()
            else:
                self._navigate_history(1)
                event.prevent_default()
        # Escape：关闭弹出列表或发送取消
        elif event.key == "escape":
            if self._command_popup is not None:
                self._close_command_popup()
                event.prevent_default()
            else:
                self.post_message(self.CancelRequested())
                event.prevent_default()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """输入内容变化时检查是否需要命令补全。"""
        self._check_command_completion()

    def _check_command_completion(self) -> None:
        """检查当前输入是否需要显示命令补全。"""
        text = self._input.text
        if text.startswith("/") and " " not in text:
            prefix = text[1:]  # 去掉 /
            if self._command_popup is None:
                self._command_popup = CommandPopup(prefix=prefix)
                self.mount(self._command_popup)
            else:
                self._command_popup.update_prefix(prefix)
        else:
            self._close_command_popup()

    def _close_command_popup(self) -> None:
        """关闭命令补全弹出列表。"""
        if self._command_popup is not None:
            self._command_popup.remove()
            self._command_popup = None

    def _navigate_history(self, direction: int) -> None:
        if not self._history:
            return

        if direction == -1 and self._history_index == len(self._history):
            self._saved_draft = self._input.text

        new_index = self._history_index + direction
        if new_index < 0 or new_index > len(self._history):
            return

        self._history_index = new_index

        if self._history_index == len(self._history):
            self._input.text = self._saved_draft
        else:
            self._input.text = self._history[self._history_index]

    def set_busy(self, busy: bool) -> None:
        """Toggle between busy and idle states."""
        self._busy = busy
        self._input.disabled = busy
        if not busy:
            self._input.focus()

    def focus_input(self) -> None:
        self._input.focus()
