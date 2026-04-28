from __future__ import annotations

import os

from textual.widget import Widget
from textual.widgets import Static
from rich.text import Text

from tui.theme import COLORS


class StatusBar(Widget):
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
        layout: horizontal;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.model_name: str = ""
        self.step_count: int = 0
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self._label: Static | None = None

    def compose(self):
        self._label = Static(self._render_text())
        yield self._label

    def _format_tokens(self, n: int) -> str:
        if n >= 1000:
            return f"{n / 1000:.1f}k"
        return str(n)

    def _render_text(self) -> Text:
        parts = []
        if self.model_name:
            parts.append(Text(f"  {self.model_name}", style=COLORS["assistant"]))
        parts.append(Text(f"  Step: {self.step_count}", style=COLORS["muted"]))
        # Token 计数
        if self.input_tokens > 0 or self.output_tokens > 0:
            in_str = self._format_tokens(self.input_tokens)
            out_str = self._format_tokens(self.output_tokens)
            parts.append(Text(f"  In:{in_str} Out:{out_str}", style=COLORS["thinking"]))
        # 工作目录
        try:
            cwd = os.getcwd()
            dir_name = os.path.basename(cwd) or cwd
            parts.append(Text(f"  {dir_name}/", style=COLORS["tool"]))
        except Exception:
            pass
        return Text.assemble(*parts)

    def update_model(self, name: str) -> None:
        self.model_name = name
        self._refresh_label()

    def update_steps(self, count: int) -> None:
        self.step_count = count
        self._refresh_label()

    def update_tokens(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self._refresh_label()

    def _refresh_label(self) -> None:
        if self._label is not None:
            self._label.update(self._render_text())
