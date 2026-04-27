from __future__ import annotations

from textual.widgets import Static
from rich.text import Text

from tui.theme import COLORS


class ConfirmPrompt(Static):
    """Inline confirmation prompt shown in ChatLog, like Claude Code."""

    DEFAULT_CSS = """
    ConfirmPrompt {
        margin: 0 0 1 0;
        padding: 0 1;
        height: auto;
    }
    """

    def __init__(self, tool_name: str, tool_args: str = "") -> None:
        super().__init__()
        self._tool_name = tool_name
        self._tool_args = tool_args
        self._selected = 1  # 0=deny, 1=allow (default allow)

    def render(self) -> Text:
        lines = []
        lines.append(Text.assemble(
            Text(f"  {self._tool_name}", style=f"bold {COLORS['warning']}"),
            Text(" needs permission", style=COLORS["warning"]),
        ))
        if self._tool_args:
            args_display = self._tool_args
            if len(args_display) > 200:
                args_display = args_display[:197] + "..."
            lines.append(Text(f"  {args_display}", style=COLORS["muted"]))

        if self._selected == 0:
            lines.append(Text.assemble(
                Text("  ✗ 拒绝 (n)", style=f"bold {COLORS['error']}"),
                Text("    批准 (y)", style=COLORS["muted"]),
            ))
        else:
            lines.append(Text.assemble(
                Text("    拒绝 (n)", style=COLORS["muted"]),
                Text("  ✓ 批准 (y)", style=f"bold {COLORS['user']}"),
            ))

        return Text("\n").join(lines)

    def select_deny(self) -> None:
        self._selected = 0
        self.refresh()

    def select_allow(self) -> None:
        self._selected = 1
        self.refresh()

    @property
    def selected(self) -> bool:
        return self._selected == 1