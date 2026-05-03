import os
from textual.theme import Theme

# Per-theme color palettes — each key matches a semantic role used across all widgets.
# Keys: user, assistant, thinking, tool, error, warning, muted, background, surface, border
_THEME_COLORS = {
    "cat-dark": {
        "user": "#50fa7b",
        "assistant": "#f8f8f2",
        "thinking": "#8be9fd",
        "tool": "#bd93f9",
        "error": "#ff5555",
        "warning": "#f1fa8c",
        "muted": "#6272a4",
        "background": "#1e1e2e",
        "surface": "#282a36",
        "border": "#44475a",
    },
    "cat-light": {
        "user": "#4e9a06",
        "assistant": "#2e3436",
        "thinking": "#0087bd",
        "tool": "#6c3ec1",
        "error": "#cc0000",
        "warning": "#c4a000",
        "muted": "#888a85",
        "background": "#fafafa",
        "surface": "#eeeeec",
        "border": "#d3d7cf",
    },
    "cat-nord": {
        "user": "#a3be8c",
        "assistant": "#d8dee9",
        "thinking": "#88c0d0",
        "tool": "#81a1c1",
        "error": "#bf616a",
        "warning": "#ebcb8b",
        "muted": "#636e7b",
        "background": "#2e3440",
        "surface": "#3b4252",
        "border": "#434c5e",
    },
}

# Active color dict — defaults to cat-dark, updated on theme change
COLORS = dict(_THEME_COLORS["cat-dark"])

# Current theme name for lookup
_current_theme = "cat-dark"


def set_theme_colors(theme_name: str) -> None:
    """Update COLORS dict to match the given theme."""
    global _current_theme
    colors = _THEME_COLORS.get(theme_name)
    if colors:
        COLORS.update(colors)
        _current_theme = theme_name


def get_current_theme() -> str:
    return _current_theme


# Textual 原生主题定义
BITZ_THEMES = [
    Theme(
        name="cat-dark",
        primary="#bd93f9",
        secondary="#8be9fd",
        warning="#f1fa8c",
        error="#ff5555",
        success="#50fa7b",
        accent="#ff79c6",
        foreground="#f8f8f2",
        background="#1e1e2e",
        surface="#282a36",
        panel="#44475a",
        dark=True,
        variables={
            "user": "#50fa7b",
            "thinking": "#8be9fd",
            "tool": "#bd93f9",
            "border": "#44475a",
        },
    ),
    Theme(
        name="cat-light",
        primary="#6c3ec1",
        secondary="#0087bd",
        warning="#c4a000",
        error="#cc0000",
        success="#4e9a06",
        accent="#c56cf0",
        foreground="#2e3436",
        background="#fafafa",
        surface="#eeeeec",
        panel="#d3d7cf",
        dark=False,
        variables={
            "user": "#4e9a06",
            "thinking": "#0087bd",
            "tool": "#6c3ec1",
            "border": "#d3d7cf",
        },
    ),
    Theme(
        name="cat-nord",
        primary="#81a1c1",
        secondary="#88c0d0",
        warning="#ebcb8b",
        error="#bf616a",
        success="#a3be8c",
        accent="#b48ead",
        foreground="#d8dee9",
        background="#2e3440",
        surface="#3b4252",
        panel="#434c5e",
        dark=True,
        variables={
            "user": "#a3be8c",
            "thinking": "#88c0d0",
            "tool": "#81a1c1",
            "border": "#434c5e",
        },
    ),
]

# 主题名列表（用于循环切换）
THEME_NAMES = [t.name for t in BITZ_THEMES]


def detect_theme() -> str:
    """根据 COLORFGBG 环境变量自动检测终端明暗，返回默认主题名。"""
    colorfgbg = os.environ.get("COLORFGBG", "")
    if colorfgbg and ";" in colorfgbg:
        fg = colorfgbg.split(";")[0]
        if fg in ("0", "15", "7"):
            return "cat-dark"
    return "cat-dark"


BITZ_CSS = """
Screen {
    layout: vertical;
    background: $background;
}

ChatLog {
    height: 1fr;
    scrollbar-size: 1 1;
    padding: 0 1;
}

StatusBar {
    height: 1;
    background: $surface;
    color: $text-muted;
    padding: 0 1;
}

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