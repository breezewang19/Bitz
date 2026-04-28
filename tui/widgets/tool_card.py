from __future__ import annotations

from textual.widgets import Static, Collapsible
from rich.text import Text

from tui.theme import COLORS


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

    ToolCard .tool-output {
        color: $text-muted;
        max-height: 15;
        padding: 0 1;
    }
    """

    class ToolDone(Message):
        def __init__(self, tool_name: str, success: bool) -> None:
            super().__init__()
            self.tool_name = tool_name
            self.success = success

    def __init__(self, tool_name: str, args_summary: str = "") -> None:
        super().__init__()
        self._tool_name = tool_name
        self._args_summary = args_summary[:60]
        self._status = "running"  # running | success | error
        self._output = ""
        self._collapsible: Collapsible | None = None
        self._output_widget: Static | None = None

    def compose(self):
        label = self._make_label()
        self._output_widget = Static("", classes="tool-output")
        self._collapsible = Collapsible(
            self._output_widget,
            title=label,
            collapsed=False,  # 运行中默认展开
        )
        yield self._collapsible

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
