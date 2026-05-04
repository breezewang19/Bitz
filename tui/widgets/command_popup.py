from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import Static
from textual.message import Message
from rich.text import Text
from rich.style import Style

from tui.theme import COLORS

if TYPE_CHECKING:
    from agent.skills import SkillRegistry

# 基础命令（不含 Skill triggers）
BASE_COMMANDS = [
    ("/help", "显示帮助信息"),
    ("/new", "开始新对话"),
    ("/clear", "清屏"),
    ("/compact", "压缩上下文"),
    ("/theme [name]", "切换主题"),
    ("/models", "模型管理弹窗"),
    ("/sessions", "打开会话历史列表"),
    ("/resume [id]", "恢复指定会话"),
    ("/title <text>", "设置会话标题"),
]

# max-height 8 行 - border(top 1 + bottom 1) = 6 行内容区
# 但需要留 1 行给滚动指示器，所以最多显示 5 条命令
_MAX_ITEMS = 5
_MAX_DESC_LEN = 20


def build_commands(skill_registry: "SkillRegistry | None" = None) -> list[tuple[str, str]]:
    """构建完整命令列表，包含基础命令和 Skill triggers。"""
    commands = list(BASE_COMMANDS)
    if skill_registry is not None:
        for skill in skill_registry.list_all():
            if skill.trigger:
                commands.append((skill.trigger, skill.description))
    return commands


class CommandPopup(Static):
    """命令补全弹出列表，支持虚拟滚动。"""

    DEFAULT_CSS = """
    CommandPopup {
        height: auto;
        max-height: 8;
        background: $surface;
        border: solid $panel;
        padding: 0 1;
        margin: 0 0 0 1;
        width: 50;
        overflow: hidden;
    }
    """

    class CommandSelected(Message):
        def __init__(self, command: str) -> None:
            super().__init__()
            self.command = command

    def __init__(self, prefix: str = "", skill_registry: "SkillRegistry | None" = None) -> None:
        super().__init__()
        self._prefix = prefix
        self._highlighted = 0
        self._scroll_offset = 0
        self._commands = build_commands(skill_registry)
        self._filtered_commands: list[str] = self._filter(prefix)

    def _filter(self, prefix: str) -> list[str]:
        """根据前缀过滤命令列表。"""
        if not prefix:
            return [cmd.split()[0] for cmd, _ in self._commands]
        return [cmd.split()[0] for cmd, _ in self._commands if cmd.split()[0][1:].startswith(prefix)]

    def update_prefix(self, prefix: str) -> None:
        """更新前缀并重新过滤。"""
        self._prefix = prefix
        self._filtered_commands = self._filter(prefix)
        self._highlighted = 0
        self._scroll_offset = 0
        self.refresh()

    def _get_desc(self, cmd: str) -> str:
        """获取命令描述，截断超长描述。"""
        for c, d in self._commands:
            if c.split()[0] == cmd:
                if len(d) > _MAX_DESC_LEN:
                    return d[:_MAX_DESC_LEN - 1] + "…"
                return d
        return ""

    def render(self) -> Text:
        if not self._filtered_commands:
            return Text("  无匹配命令", style=COLORS["muted"])

        total = len(self._filtered_commands)
        if total <= _MAX_ITEMS:
            start, end = 0, total
        else:
            start = self._scroll_offset
            end = start + _MAX_ITEMS

        lines = []
        for i in range(start, end):
            cmd = self._filtered_commands[i]
            desc = self._get_desc(cmd)
            is_hl = (i == self._highlighted)

            if is_hl:
                lines.append(Text.assemble(
                    Text("▸ ", style=Style(color="black", bgcolor="cyan", bold=True)),
                    Text(cmd, style=Style(color="black", bgcolor="cyan", bold=True)),
                    Text(f" {desc}", style=Style(color="black", bgcolor="cyan")),
                ))
            else:
                lines.append(Text.assemble(
                    Text("  ", style=Style()),
                    Text(cmd, style=Style(color=COLORS["tool"], bold=True)),
                    Text(f" {desc}", style=Style(color=COLORS["muted"])),
                ))

        # 底部滚动指示器
        if total > _MAX_ITEMS:
            indicator = f" [{start + 1}-{end}/{total}]"
            lines.append(Text(indicator, style=Style(color=COLORS["muted"], italic=True)))

        result = Text("\n").join(lines)
        result.no_wrap = True
        return result

    def select_highlighted(self) -> str | None:
        """返回当前高亮的命令。"""
        if self._filtered_commands:
            return self._filtered_commands[self._highlighted]
        return None

    def move_highlight(self, direction: int) -> None:
        """移动高亮（direction: -1=上, 1=下），自动滚动。"""
        if not self._filtered_commands:
            return
        total = len(self._filtered_commands)
        self._highlighted = (self._highlighted + direction) % total
        if total <= _MAX_ITEMS:
            self._scroll_offset = 0
            self.refresh()
            return
        if self._highlighted < self._scroll_offset:
            self._scroll_offset = self._highlighted
        elif self._highlighted >= self._scroll_offset + _MAX_ITEMS:
            self._scroll_offset = self._highlighted - _MAX_ITEMS + 1
        self.refresh()
