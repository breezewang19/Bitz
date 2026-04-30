from __future__ import annotations

from textual.widgets import Button
from textual.message import Message


class CopyButton(Button):
    """右上角小复制按钮"""
    DEFAULT_CSS = """
    CopyButton {
        min-height: 1;
        height: 1;
        width: 3;
        max-width: 3;
        padding: 0;
        border: none;
        background: transparent;
        color: $text-disabled;
    }
    CopyButton:hover {
        background: $surface;
        color: $text;
    }
    CopyButton.copied {
        color: #50fa7b;
    }
    """

    class Copied(Message):
        """复制成功事件"""
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    def __init__(self, text: str) -> None:
        super().__init__("⎘", variant="default")
        self._copy_text = text

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.post_message(self.Copied(self._copy_text))
        self.label = "✓"
        self.add_class("copied")
        self.set_timer(1.5, self._reset_label)

    def _reset_label(self) -> None:
        self.label = "⎘"
        self.remove_class("copied")
