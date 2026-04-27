from __future__ import annotations

from textual.widget import Widget
from textual.widgets import Static
from rich.text import Text

from tui.theme import COLORS


class StatusBar(Widget):
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: #282a36;
        color: #6272a4;
        padding: 0 1;
        layout: horizontal;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.model_name: str = ""
        self.step_count: int = 0
        self._label: Static | None = None

    def compose(self):
        self._label = Static(self._render_text())
        yield self._label

    def _render_text(self) -> Text:
        parts = []
        if self.model_name:
            parts.append(Text(f"  {self.model_name}", style=COLORS["assistant"]))
        parts.append(Text(f"  Step: {self.step_count}", style=COLORS["muted"]))
        return Text.assemble(*parts)

    def update_model(self, name: str) -> None:
        self.model_name = name
        self._refresh_label()

    def update_steps(self, count: int) -> None:
        self.step_count = count
        self._refresh_label()

    def _refresh_label(self) -> None:
        if self._label is not None:
            self._label.update(self._render_text())
