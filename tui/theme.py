import os
from textual.theme import Theme

# 语义色常量（供非 Textual 组件如 banner 使用）
COLORS = {
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
}

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
    # 常见暗色终端前景色: 0 (黑), 15 (白在暗底)
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
