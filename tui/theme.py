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

BITZ_CSS = """
Screen {
    layout: vertical;
    background: #1e1e2e;
}

ChatLog {
    height: 1fr;
    scrollbar-size: 1 1;
    padding: 0 1;
}

StatusBar {
    height: 1;
    background: #282a36;
    color: #6272a4;
    padding: 0 1;
}

InputBar {
    height: 3;
    background: #282a36;
    border-top: solid #44475a;
    padding: 0 1;
}

InputBar Input {
    background: #1e1e2e;
    border: none;
}
"""
