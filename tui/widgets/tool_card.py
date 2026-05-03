from __future__ import annotations

from textual.widgets import Static, Collapsible
from rich.text import Text
from rich.syntax import Syntax

from tui.theme import COLORS
from tui.widgets.copy_button import CopyButton


class ToolCard(Static):
    """可折叠工具调用卡片，显示工具名、状态图标、参数摘要和结果。"""

    DEFAULT_CSS = """
    ToolCard {
        margin: 0 0 1 0;
        padding: 0 1;
        height: auto;
    }

    ToolCard Collapsible {
        width: 1fr;
    }

    ToolCard Collapsible .collapsible--title {
        text-wrap: wrap;
        width: 1fr;
    }

    ToolCard .tool-output {
        color: $text-muted;
        max-height: 15;
        padding: 0 1;
        width: 100%;
        overflow-x: hidden;
    }

    ToolCard CopyButton {
        dock: right;
        height: 1;
        width: 3;
    }
    """

    def __init__(self, tool_name: str, args_summary: str = "") -> None:
        super().__init__()
        self._tool_name = tool_name
        self._args_summary = args_summary[:60]
        self._status = "running"  # running | success | error
        self._output = ""
        self._collapsible: Collapsible | None = None
        self._output_widget: Static | None = None

    def compose(self):
        yield CopyButton(self._args_summary)
        label = self._make_label()
        self._output_widget = Static("", classes="tool-output")
        self._collapsible = Collapsible(
            self._output_widget,
            title=label,
            collapsed=False,  # 运行中默认展开
        )
        yield self._collapsible

    def on_copy_button_copied(self, event: CopyButton.Copied) -> None:
        event.stop()
        self.app.copy_to_clipboard(event.text)
        self.app.notify("已复制到剪贴板", severity="information", timeout=2)

    def _make_label(self) -> str:
        icons = {"running": "⟳", "success": "✓", "error": "✗"}
        icon = icons.get(self._status, "⟳")
        if self._args_summary:
            return f"{icon} {self._tool_name}: {self._args_summary}"
        return f"{icon} {self._tool_name}"

    def _update_label(self) -> None:
        if self._collapsible is not None:
            self._collapsible.title = self._make_label()

    def set_running(self) -> None:
        self._status = "running"
        self._update_label()
        if self._collapsible is not None:
            self._collapsible.collapsed = False

    def set_success(self, output: str = "") -> None:
        self._status = "success"
        self._output = output
        self._update_label()
        if self._output_widget is not None:
            display = output if len(output) <= 500 else output[:497] + "..."
            self._output_widget.update(display)
        if self._collapsible is not None:
            self._collapsible.collapsed = True

    def set_error(self, output: str = "") -> None:
        self._status = "error"
        self._output = output
        self._update_label()
        if self._output_widget is not None:
            display = output if len(output) <= 500 else output[:497] + "..."
            self._output_widget.update(display)
        if self._collapsible is not None:
            self._collapsible.collapsed = False

    def set_diff(self, diff_text: str) -> None:
        """显示 diff 内容。"""
        self._status = "success"
        self._output = diff_text
        self._update_label()
        if self._output_widget is not None:
            # 用 rich.syntax 渲染 diff
            try:
                syntax = Syntax(diff_text, lexer="diff", theme="monokai")
                self._output_widget.update(syntax)
            except Exception:
                # fallback: 纯文本
                display = diff_text if len(diff_text) <= 500 else diff_text[:497] + "..."
                self._output_widget.update(display)
        if self._collapsible is not None:
            self._collapsible.collapsed = False  # diff 默认展开
