from __future__ import annotations

from textual.widgets import Static
from textual.message import Message
from rich.text import Text

from tui.theme import COLORS

# 所有可用命令
COMMANDS = [
    ("/help", "显示帮助信息"),
    ("/clear", "清屏"),
    ("/compact", "压缩上下文"),
    ("/theme [name]", "切换主题"),
]


class CommandPopup(Static):
    """命令补全弹出列表。"""

    DEFAULT_CSS = """
    CommandPopup {
        height: auto;
        max-height: 8;
        background: $surface;
        border: solid $panel;
        padding: 0 1;
        margin: 0 0 0 1;
        width: 30;
    }

    CommandPopup .command-item {
        height: 1;
        padding: 0 1;
    }

    CommandPopup .command-item-highlighted {
        background: $primary-background;
        color: $text;
    }
    """

    class CommandSelected(Message):
        def __init__(self, command: str) -> None:
            super().__init__()
            self.command = command

    def __init__(self, prefix: str = "") -> None:
        super().__init__()
        self._prefix = prefix
        self._highlighted = 0
        self._filtered_commands: list[str] = self._filter(prefix)

    def _filter(self, prefix: str) -> list[str]:
        """根据前缀过滤命令列表。"""
        if not prefix:
            return [cmd.split()[0] for cmd, _ in COMMANDS]
        # 前缀不包含 "/"，所以比较时去掉命令的 "/"
        return [cmd.split()[0] for cmd, _ in COMMANDS if cmd.split()[0][1:].startswith(prefix)]

    def update_prefix(self, prefix: str) -> None:
        """更新前缀并重新过滤。"""
        self._prefix = prefix
        self._filtered_commands = self._filter(prefix)
        self._highlighted = 0
        self.refresh()

    def render(self) -> Text:
        if not self._filtered_commands:
            return Text("  无匹配命令", style=COLORS["muted"])
        lines = []
        for i, cmd in enumerate(self._filtered_commands):
            # 找到对应的描述
            desc = ""
            for c, d in COMMANDS:
                if c.split()[0] == cmd:
                    desc = d
                    break
            if i == self._highlighted:
                lines.append(Text.assemble(
                    Text(f"  {cmd}", style=f"bold {COLORS['tool']}"),
                    Text(f"  {desc}", style=COLORS["muted"]),
                ))
            else:
                lines.append(Text.assemble(
                    Text(f"  {cmd}", style=COLORS["tool"]),
                    Text(f"  {desc}", style=COLORS["muted"]),
                ))
        return Text("\n").join(lines)

    def select_highlighted(self) -> str | None:
        """返回当前高亮的命令。"""
        if self._filtered_commands:
            return self._filtered_commands[self._highlighted]
        return None

    def move_highlight(self, direction: int) -> None:
        """移动高亮（direction: -1=上, 1=下）。"""
        if self._filtered_commands:
            self._highlighted = (self._highlighted + direction) % len(self._filtered_commands)
            self.refresh()
