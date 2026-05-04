from __future__ import annotations

import os

from textual.widget import Widget
from textual.widgets import Static
from rich.text import Text

from tui.theme import COLORS, get_current_theme

_STATUS_ACCENT = {
    "cat-dark": "#7e54c6",
    "cat-light": "#6c47b2",
    "cat-nord": "#5e81ac",
}


def _get_status_color() -> str:
    return _STATUS_ACCENT.get(get_current_theme(), _STATUS_ACCENT["cat-dark"])


class StatusBar(Widget):
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
        layout: horizontal;
    }
    StatusBar #status-left {
        width: 1fr;
    }
    StatusBar #status-right {
        dock: right;
        width: auto;
    }
    """
    SEP = " │ "
    CAT_LOGO = "=^._.^=BITZ"

    def __init__(self) -> None:
        super().__init__()
        self.model_name: str = ""
        self.step_count: int = 0
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.persistence_error: bool = False
        self.task_in_progress: int = 0
        self.task_total: int = 0
        self._left: Static | None = None
        self._right: Static | None = None

    def compose(self):
        self._left = Static(self._render_left(), id="status-left")
        self._right = Static(self._render_right(), id="status-right")
        yield self._left
        yield self._right

    def update_persistence_error(self, has_error: bool) -> None:
        self.persistence_error = has_error
        self._refresh()

    def _format_tokens(self, n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1000:
            return f"{n / 1000:.1f}k"
        return str(n)

    def _render_left(self) -> Text:
        color = _get_status_color()
        parts: list[Text] = []

        if self.model_name:
            parts.append(Text(self.model_name, style=color))

        parts.append(Text(f"Step {self.step_count}", style=color))

        if self.input_tokens > 0 or self.output_tokens > 0:
            parts.append(Text(
                f"↓{self._format_tokens(self.input_tokens)}",
                style=color,
            ))
            parts.append(Text(
                f"↑{self._format_tokens(self.output_tokens)}",
                style=color,
            ))

        if self.task_total > 0:
            parts.append(Text(f"Tasks: {self.task_in_progress}/{self.task_total}", style=color))

        if self.persistence_error:
            parts.append(Text("⚠", style="red"))

        try:
            cwd = os.getcwd()
            dir_name = os.path.basename(cwd) or cwd
            parts.append(Text(dir_name + "/", style=color))
        except Exception:
            pass

        result = Text()
        for i, part in enumerate(parts):
            if i > 0:
                result.append(self.SEP, style=color)
            result.append(part)
        return result

    def _render_right(self) -> Text:
        return Text(self.CAT_LOGO, style=_get_status_color())

    def update_model(self, name: str) -> None:
        self.model_name = name
        self._refresh()

    def update_steps(self, count: int) -> None:
        self.step_count = count
        self._refresh()

    def update_tokens(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self._refresh()

    def update_task_count(self, in_progress: int, total: int) -> None:
        self.task_in_progress = in_progress
        self.task_total = total
        self._refresh()

    def _refresh(self) -> None:
        if self._left is not None:
            self._left.update(self._render_left())
        if self._right is not None:
            self._right.update(self._render_right())
