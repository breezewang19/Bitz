from __future__ import annotations

from textual.widgets import Static
from textual.message import Message
from rich.text import Text

from tui.theme import COLORS

CAT_BODY = [
    "    /\\_____/\\",
    "   /  o   o  \\",
    "  ( =  ^  y  = )",
    "   \\_____/    ~ Bitz ~",
]

CAT_BLINK = [
    "    /\\_____/\\",
    "   /  -   -  \\",
    "  ( =  ^  y  = )",
    "   \\_____/    ~ Bitz ~",
]

RAINBOW_COLORS = [
    "#ff5555", "#ff5555",
    "#f1fa8c", "#f1fa8c",
    "#50fa7b", "#50fa7b",
    "#8be9fd", "#8be9fd",
    "#6272a4", "#6272a4",
    "#bd93f9", "#bd93f9",
    "#ff5555", "#ff5555",
    "#f1fa8c", "#f1fa8c",
    "#50fa7b", "#50fa7b",
    "#8be9fd", "#8be9fd",
    "#6272a4", "#6272a4",
    "#bd93f9", "#bd93f9",
    "#ff5555", "#ff5555",
]

GOODBYE_TEXT = "Goodbye~"
GOODBYE_COLORS = [
    "#ff5555", "#f1fa8c", "#50fa7b", "#8be9fd",
    "#6272a4", "#bd93f9", "#ff5555", "#f1fa8c", "#50fa7b",
]

WELCOME_TEXT = "Welcome Back Bitz-Cat!"

BORDER_COLOR = COLORS["muted"]


def _colorize_char(ch: str, idx: int, dim: bool = False) -> Text:
    color = RAINBOW_COLORS[idx % len(RAINBOW_COLORS)]
    style = f"dim {color}" if dim else f"bold {color}"
    return Text(ch, style=style)


def _make_border_top(inner_w: int) -> Text:
    return Text(f"  ╭{'─' * inner_w}╮", style=BORDER_COLOR)


def _make_border_bottom(inner_w: int) -> Text:
    return Text(f"  ╰{'─' * inner_w}╯", style=BORDER_COLOR)


def _make_row(content: str, inner_w: int) -> Text:
    pad = inner_w - len(content)
    return Text.assemble(
        Text("  │", style=BORDER_COLOR),
        Text(content),
        Text(" " * max(pad, 0)),
        Text("│", style=BORDER_COLOR),
    )


class BannerWidget(Static):
    DEFAULT_CSS = """
    BannerWidget {
        height: auto;
        margin: 1 0 0 0;
    }
    """

    class BannerDone(Message):
        pass

    def __init__(self, model_name: str = "") -> None:
        super().__init__()
        self._model_name = model_name
        self._lit = 0
        self._max_lit = max(len(line) for line in CAT_BODY)
        self._phase = "cat"
        self._welcome_idx = 0
        self._blink_state = False
        self._blink_count = 0
        max_cat = max(len(line) for line in CAT_BODY)
        welcome_len = len(WELCOME_TEXT)
        self._inner_w = max(max_cat, welcome_len) + 2

    def on_mount(self) -> None:
        self._render_frame()
        self.set_interval(0.08, self._advance)

    def _advance(self) -> None:
        if self._phase == "cat":
            self._lit += 2
            if self._lit > self._max_lit + 2:
                self._phase = "welcome"
            self._render_frame()
        elif self._phase == "welcome":
            self._welcome_idx += 1
            if self._welcome_idx > len(WELCOME_TEXT):
                self._phase = "blink"
            self._render_frame()
        elif self._phase == "blink":
            self._blink_count += 1
            if self._blink_count > 6:
                self._phase = "done"
                self._finish()
                return
            self._blink_state = not self._blink_state
            self._render_frame()

    def _render_frame(self) -> None:
        cat_lines = CAT_BLINK if self._blink_state else CAT_BODY
        dim = self._phase == "cat"
        w = self._inner_w

        lines = []
        lines.append(Text(""))
        lines.append(_make_border_top(w))

        # Top padding
        lines.append(_make_row("", w))

        # Welcome line
        if self._phase in ("welcome", "blink", "done"):
            shown = WELCOME_TEXT[:self._welcome_idx]
            cursor = "▌" if self._phase == "welcome" else ""
            lines.append(_make_row(f" {shown}{cursor}", w))
        else:
            lines.append(_make_row("", w))

        # Spacer between welcome and cat
        lines.append(_make_row("", w))

        # Cat lines
        for cat_line in cat_lines:
            row = Text()
            row.append(Text("  │", style=BORDER_COLOR))
            for i, ch in enumerate(cat_line):
                if dim and i >= self._lit:
                    row.append(_colorize_char(ch, i, dim=True))
                else:
                    row.append(_colorize_char(ch, i, dim=False))
            pad = w - len(cat_line)
            row.append(Text(" " * max(pad, 0)))
            row.append(Text("│", style=BORDER_COLOR))
            lines.append(row)

        # Bottom padding
        lines.append(_make_row("", w))

        lines.append(_make_border_bottom(w))
        lines.append(Text(""))
        lines.append(Text(""))

        self.update(Text("\n").join(lines))

    def _finish(self) -> None:
        w = self._inner_w

        lines = []
        lines.append(Text(""))
        lines.append(_make_border_top(w))
        lines.append(_make_row("", w))
        lines.append(_make_row(f" {WELCOME_TEXT}", w))
        lines.append(_make_row("", w))

        for cat_line in CAT_BODY:
            row = Text()
            row.append(Text("  │", style=BORDER_COLOR))
            for i, ch in enumerate(cat_line):
                row.append(_colorize_char(ch, i, dim=False))
            pad = w - len(cat_line)
            row.append(Text(" " * max(pad, 0)))
            row.append(Text("│", style=BORDER_COLOR))
            lines.append(row)

        lines.append(_make_row("", w))
        lines.append(_make_border_bottom(w))
        lines.append(Text(""))
        lines.append(Text(""))

        self.update(Text("\n").join(lines))
        self.post_message(self.BannerDone())


class GoodbyeWidget(Static):
    DEFAULT_CSS = """
    GoodbyeWidget {
        height: auto;
        margin: 1 0 0 0;
    }
    """

    class GoodbyeDone(Message):
        pass

    def __init__(self) -> None:
        super().__init__()
        self._lit = 0

    def on_mount(self) -> None:
        self._render_frame()
        self.set_interval(0.06, self._advance)

    def _advance(self) -> None:
        self._lit += 1
        if self._lit > len(GOODBYE_TEXT):
            self.post_message(self.GoodbyeDone())
            return
        self._render_frame()

    def _render_frame(self) -> None:
        row = Text("  ")
        for i, ch in enumerate(GOODBYE_TEXT):
            color = GOODBYE_COLORS[i]
            if i < self._lit:
                row.append(Text(ch, style=f"bold {color}"))
            else:
                row.append(Text(ch, style=f"dim {color}"))
        self.update(row)
