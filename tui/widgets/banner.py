from __future__ import annotations

from textual.widgets import Static
from textual.message import Message
from rich.text import Text
from rich.style import Style

from tui.theme import COLORS

CAT_BODY = [
    "    /\\_____/\\",
    "   /  o   o  \\",
    "  ( =  ^  y = )",
    "   \\______/  ~ Bitz ~",
]

CAT_BLINK = [
    "    /\\_____/\\",
    "   /  -   -  \\",
    "  ( =  ^  y = )",
    "   \\______/  ~ Bitz ~",
]

# 同色系渐变：从暗紫到亮紫，低→高亮度
GRADIENT_COLORS = [
    "#3b2070", "#4a2d8a", "#5a3a9e", "#6c47b2",
    "#7e54c6", "#9061d8", "#a270e8", "#b47ef0",
    "#c68cf8", "#d89aff", "#e8a8ff", "#f0b8ff",
    "#c68cf8", "#a270e8", "#7e54c6", "#5a3a9e",
    "#3b2070", "#4a2d8a", "#5a3a9e", "#6c47b2",
    "#7e54c6", "#9061d8", "#a270e8", "#b47ef0",
    "#c68cf8", "#d89aff", "#e8a8ff", "#f0b8ff",
    "#c68cf8", "#a270e8", "#7e54c6", "#5a3a9e",
]

GOODBYE_COLORS = [
    "#6c47b2", "#7e54c6", "#9061d8", "#a270e8",
    "#b47ef0", "#c68cf8", "#d89aff", "#e8a8ff", "#f0b8ff",
]

WELCOME_TEXT = "Welcome Back Bitz-Cat!"
GOODBYE_TEXT = "Goodbye~"
VERSION = "v0.1.0"

BORDER_COLOR = COLORS["muted"]
MODEL_STYLE = Style(color="#9061d8", bold=True)
MODEL_LABEL_STYLE = Style(color="#6c47b2", dim=True)
VERSION_STYLE = Style(color="#6c47b2", dim=True)
VERSION_LABEL_STYLE = Style(color="#5a3a9e", dim=True)


def _colorize_char(ch: str, idx: int, dim: bool = False) -> Text:
    color = GRADIENT_COLORS[idx % len(GRADIENT_COLORS)]
    style = Style(color=color, dim=dim, bold=not dim)
    return Text(ch, style=style)


def _make_border_top(inner_w: int) -> Text:
    return Text(f"╭{'─' * inner_w}╮", style=BORDER_COLOR)


def _make_border_bottom(inner_w: int) -> Text:
    return Text(f"╰{'─' * inner_w}╯", style=BORDER_COLOR)


def _make_row(content: str | Text, inner_w: int, content_len: int = 0) -> Text:
    if isinstance(content, Text):
        actual_len = content_len or len(content.plain)
        pad = inner_w - actual_len
        return Text.assemble(
            Text("│", style=BORDER_COLOR),
            content,
            Text(" " * max(pad, 0)),
            Text("│", style=BORDER_COLOR),
        )
    else:
        pad = inner_w - len(content)
        return Text.assemble(
            Text("│", style=BORDER_COLOR),
            Text(content),
            Text(" " * max(pad, 0)),
            Text("│", style=BORDER_COLOR),
        )


def _make_row_lr(left: str | Text, right: str | Text, inner_w: int,
                 left_len: int = 0, right_len: int = 0) -> Text:
    """左右对齐的一行：left 靠左，right 靠右，右侧留 2 格边距。"""
    l_len = left_len or (len(left.plain) if isinstance(left, Text) else len(left))
    r_len = right_len or (len(right.plain) if isinstance(right, Text) else len(right))
    right_pad = 2
    gap = inner_w - l_len - r_len - right_pad
    return Text.assemble(
        Text("│", style=BORDER_COLOR),
        left,
        Text(" " * max(gap, 1)),
        right,
        Text(" " * right_pad),
        Text("│", style=BORDER_COLOR),
    )


class BannerWidget(Static):
    DEFAULT_CSS = """
    BannerWidget {
        height: auto;
        margin: 1 0 0 0;
        width: 100%;
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

    def _get_inner_w(self) -> int:
        """获取实际可用内容宽度（减去左右边框各 1 列）。"""
        try:
            return self.content_region.width - 2
        except Exception:
            max_cat = max(len(line) for line in CAT_BODY)
            welcome_len = len(WELCOME_TEXT)
            return max(max_cat, welcome_len) + 4

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
        w = self._get_inner_w()

        lines = []
        lines.append(Text(""))
        lines.append(_make_border_top(w))

        # Top padding
        lines.append(_make_row("", w))

        # Welcome line (left) + Model label (right)
        if self._phase in ("welcome", "blink", "done"):
            shown = WELCOME_TEXT[:self._welcome_idx]
            cursor = "▌" if self._phase == "welcome" else ""
            welcome_str = f" {shown}{cursor}"
            welcome_text = Text(welcome_str, style=Style(color="#d89aff", bold=True))
            model_label = Text("Model", style=MODEL_LABEL_STYLE)
            lines.append(_make_row_lr(welcome_text, model_label, w,
                                      left_len=len(welcome_str),
                                      right_len=len("Model")))
        else:
            lines.append(_make_row("", w))

        # Model value (right-aligned)
        model_val = Text(self._model_name, style=MODEL_STYLE)
        lines.append(_make_row_lr(Text(""), model_val, w,
                                  left_len=0, right_len=len(self._model_name)))

        # Version label (right-aligned)
        version_label = Text("Version", style=VERSION_LABEL_STYLE)
        lines.append(_make_row_lr(Text(""), version_label, w,
                                  left_len=0, right_len=len("Version")))

        # Version value (right-aligned)
        version_val = Text(VERSION, style=VERSION_STYLE)
        lines.append(_make_row_lr(Text(""), version_val, w,
                                  left_len=0, right_len=len(VERSION)))

        # Cat lines
        for cat_line in cat_lines:
            row = Text()
            for i, ch in enumerate(cat_line):
                if dim and i >= self._lit:
                    row.append(_colorize_char(ch, i, dim=True))
                else:
                    row.append(_colorize_char(ch, i, dim=False))
            pad = w - len(cat_line)
            row.append(Text(" " * max(pad, 0)))
            lines.append(_make_row(row, w, content_len=len(cat_line) + max(pad, 0)))

        # Bottom padding
        lines.append(_make_row("", w))

        lines.append(_make_border_bottom(w))
        lines.append(Text(""))
        lines.append(Text(""))

        self.update(Text("\n").join(lines))

    def _finish(self) -> None:
        w = self._get_inner_w()

        lines = []
        lines.append(Text(""))
        lines.append(_make_border_top(w))
        lines.append(_make_row("", w))

        # Welcome (left) + Model label (right)
        welcome_text = Text(f" {WELCOME_TEXT}", style=Style(color="#d89aff", bold=True))
        model_label = Text("Model", style=MODEL_LABEL_STYLE)
        lines.append(_make_row_lr(welcome_text, model_label, w,
                                  left_len=len(f" {WELCOME_TEXT}"),
                                  right_len=len("Model")))

        # Model value (right-aligned)
        model_val = Text(self._model_name, style=MODEL_STYLE)
        lines.append(_make_row_lr(Text(""), model_val, w,
                                  left_len=0, right_len=len(self._model_name)))

        # Version label (right-aligned)
        version_label = Text("Version", style=VERSION_LABEL_STYLE)
        lines.append(_make_row_lr(Text(""), version_label, w,
                                  left_len=0, right_len=len("Version")))

        # Version value (right-aligned)
        version_val = Text(VERSION, style=VERSION_STYLE)
        lines.append(_make_row_lr(Text(""), version_val, w,
                                  left_len=0, right_len=len(VERSION)))

        for cat_line in CAT_BODY:
            row = Text()
            for i, ch in enumerate(cat_line):
                row.append(_colorize_char(ch, i, dim=False))
            pad = w - len(cat_line)
            row.append(Text(" " * max(pad, 0)))
            lines.append(_make_row(row, w, content_len=len(cat_line) + max(pad, 0)))

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
        width: 100%;
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
                row.append(Text(ch, style=Style(color=color, bold=True)))
            else:
                row.append(Text(ch, style=Style(color=color, dim=True)))
        self.update(row)