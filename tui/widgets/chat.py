from __future__ import annotations

from textual.widgets import Static, Collapsible
from textual.widgets import Markdown as MarkdownWidget
from textual.message import Message
from textual.containers import VerticalScroll
from rich.text import Text

from tui.theme import COLORS
from tui.widgets.tool_card import ToolCard
from tui.widgets.copy_button import CopyButton


class UserMessage(Static):
    DEFAULT_CSS = """
    UserMessage {
        background: #1a1a2e;
        color: #50fa7b;
        margin: 0 0 1 0;
        padding: 0 1;
        width: 100%;
    }
    """

    def __init__(self, content: str) -> None:
        super().__init__()
        self._content = content

    def render(self) -> Text:
        return Text.assemble(
            Text("> ", style=f"bold {COLORS['user']}"),
            Text(self._content, style=COLORS['user']),
        )


class AssistantMessage(Static):
    DEFAULT_CSS = """
    AssistantMessage {
        color: $text;
        margin: 0 0 1 0;
        padding: 0 1;
        height: auto;
    }
    AssistantMessage Markdown {
        height: auto;
        width: 100%;
    }
    AssistantMessage CopyButton {
        dock: right;
        height: 1;
        width: 3;
    }
    """

    def __init__(self, content: str) -> None:
        super().__init__(markup=False)
        self._content = content

    def compose(self):
        yield MarkdownWidget(self._content)
        yield CopyButton(self._content)

    def on_copy_button_copied(self, event: CopyButton.Copied) -> None:
        event.stop()
        self.app.copy_to_clipboard(event.text)
        self.app.notify("已复制到剪贴板", severity="information", timeout=2)

    def update_content(self, text: str) -> None:
        """更新 Markdown 内容。"""
        self._content = text
        try:
            md = self.query_one(MarkdownWidget)
            md.update(text)
        except Exception:
            pass
        try:
            btn = self.query_one(CopyButton)
            btn._copy_text = text
        except Exception:
            pass


class ThinkingIndicator(Static):
    DEFAULT_CSS = """
    ThinkingIndicator {
        color: #8be9fd;
        margin: 0 0 0 0;
        padding: 0 1;
        height: 1;
        display: none;
    }
    ThinkingIndicator.visible {
        display: block;
    }
    """

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self) -> None:
        super().__init__()
        self._frame = 0
        self._canceling = False
        self._tool_name: str | None = None
        self._elapsed: float | None = None

    def render(self) -> Text:
        frame = self.SPINNER_FRAMES[self._frame % len(self.SPINNER_FRAMES)]
        parts = []
        if self._canceling:
            parts.append(Text(f"{frame} ", style=COLORS["error"]))
            parts.append(Text("[ESC] Canceling", style=COLORS["error"]))
        elif self._tool_name:
            parts.append(Text(f"{frame} ", style=COLORS["tool"]))
            parts.append(Text(f"Running ", style=COLORS["tool"]))
            parts.append(Text(f"[{self._tool_name}]", style=f"bold {COLORS['tool']}"))
        else:
            parts.append(Text(f"{frame} ", style=COLORS["thinking"]))
            parts.append(Text("Thinking", style=COLORS["thinking"]))
        if self._elapsed is not None:
            parts.append(Text(f" {self._format_elapsed(self._elapsed)}", style=COLORS["muted"]))
        return Text.assemble(*parts)

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        if seconds >= 60:
            m = int(seconds // 60)
            s = int(seconds % 60)
            return f"{m}m {s}s"
        return f"{seconds:.1f}s"

    def set_elapsed(self, seconds: float) -> None:
        self._elapsed = seconds
        self.refresh()

    def advance(self) -> None:
        self._frame += 1
        self.refresh()

    def set_canceling(self) -> None:
        self._canceling = True
        self.refresh()

    def set_tool(self, tool_name: str | None) -> None:
        self._tool_name = tool_name
        self.refresh()

    def show(self) -> None:
        self._canceling = False
        self._tool_name = None
        self._frame = 0
        self.add_class("visible")

    def hide(self) -> None:
        self.remove_class("visible")


def format_tool_content(name: str, args: dict | None = None) -> str:
    """Extract display content from tool args, matching original tui_core.py logic."""
    if args is None:
        args = {}
    if name == "bash":
        return args.get('command', '')
    elif name == "read_file":
        return args.get('path', '')
    elif name == "write_file":
        path = args.get('path', '')
        chars = len(args.get('content', ''))
        return f"{path} ({chars} chars)" if path else ''
    elif name == "edit_file":
        return args.get('path', '')
    elif name == "glob":
        return args.get('pattern', '')
    elif name == "grep":
        pattern = args.get('pattern', '')
        path = args.get('path', '.')
        return f"{pattern} in {path}"
    elif name == "fetch":
        return args.get('url', '')
    else:
        return str(args) if args else ''


class TurnTiming(Static):
    """每轮对话耗时汇总，显示在 assistant 消息下方。"""

    DEFAULT_CSS = """
    TurnTiming {
        color: $text-muted;
        margin: 0 0 1 0;
        padding: 0 1;
        height: auto;
    }
    """

    def __init__(self, seconds: float) -> None:
        super().__init__()
        self._seconds = seconds

    def render(self) -> Text:
        return Text(f"Worked for {self._format_elapsed(self._seconds)}", style=COLORS["muted"])

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        if seconds >= 3600:
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            return f"{h}h {m}m {s}s"
        if seconds >= 60:
            m = int(seconds // 60)
            s = int(seconds % 60)
            return f"{m}m {s}s"
        return f"{seconds:.1f}s"


class ChatLog(VerticalScroll):
    DEFAULT_CSS = """
    ChatLog {
        height: 1fr;
        scrollbar-size: 1 1;
        padding: 0 1;
    }
    """

    class MessageAdded(Message):
        def __init__(self, role: str, content: str) -> None:
            super().__init__()
            self.role = role
            self.content = content

    def __init__(self) -> None:
        super().__init__()

    def add_message(self, role: str, content: str, tool_name: str = "") -> None:
        if role == "user":
            msg_widget = UserMessage(content)
        elif role == "assistant":
            msg_widget = AssistantMessage(content)
        elif role == "tool":
            msg_widget = ToolCard(tool_name=tool_name, args_summary=content)
        else:
            msg_widget = Static(content)

        self.mount(msg_widget)
        self.call_after_refresh(self._scroll_to_bottom)
        self.post_message(self.MessageAdded(role, content))

    def _scroll_to_bottom(self) -> None:
        self.scroll_end(animate=False)


class SubAgentCard(Static):
    """子 Agent 状态卡片，内嵌滚动日志"""
    DEFAULT_CSS = """
    SubAgentCard {
        background: #1a1a2e;
        border: round #6272a4;
        margin: 0 0 1 0;
        padding: 0 1;
        height: auto;
    }
    SubAgentCard Collapsible {
        width: 1fr;
    }

    SubAgentCard Collapsible .collapsible--title {
        text-wrap: wrap;
        width: 1fr;
    }
    SubAgentCard .subagent-header {
        color: #8be9fd;
        padding: 0 0 0 0;
    }
    SubAgentCard .subagent-log {
        color: $text-muted;
        max-height: 12;
        padding: 0 1;
        width: 100%;
        overflow-x: hidden;
    }
    SubAgentCard CopyButton {
        dock: right;
        height: 1;
        width: 3;
    }
    """

    def __init__(self, task: str, count: int = 1, agent_type: str = "general-purpose") -> None:
        super().__init__()
        self._task_desc = task
        self._count = count
        self._agent_type = agent_type
        self._task_summaries: list[dict] = []  # [{name, status, steps, elapsed, error, tokens}]
        self._task_logs: dict[int, Static] = {}  # task_index → log Static
        self._task_copy_btns: dict[int, CopyButton] = {}  # task_index → CopyButton
        self._task_collapse: dict[int, Collapsible] = {}  # task_index → Collapsible
        self._task_log_text: dict[int, str] = {}  # task_index → raw log text for copy
        self._header: Static | None = None
        self._done = 0

    def compose(self):
        self._header = Static(self._render_header(), classes="subagent-header")
        yield self._header

    def _render_header(self) -> Text:
        done = sum(1 for t in self._task_summaries if t["status"] == "done")
        type_name = self._agent_type.replace("-", " ").title()
        return Text.assemble(
            Text(f"{type_name} Agent ({done}/{self._count}): ", style=COLORS["tool"]),
            Text(self._task_desc, style=COLORS["muted"]),
        )

    def add_task(self, task_index: int, task_name: str) -> None:
        """开始一个新任务，创建其 Collapsible + log 区域"""
        log_widget = Static("", classes="subagent-log")
        copy_btn = CopyButton("")
        collapse = Collapsible(log_widget, title=f"◌ {task_name}", collapsed=False)
        self._task_logs[task_index] = log_widget
        self._task_copy_btns[task_index] = copy_btn
        self._task_collapse[task_index] = collapse
        self._task_log_text[task_index] = ""
        self._task_summaries.append({"name": task_name, "status": "running"})
        self.mount(collapse)
        self.mount(copy_btn)

    def append_log(self, task_index: int, line: str) -> None:
        """追加一行日志到指定任务的 log 区域"""
        if task_index in self._task_logs:
            log = self._task_logs[task_index]
            # Track raw text for copy
            raw = self._task_log_text.get(task_index, "")
            self._task_log_text[task_index] = raw + "\n" + line if raw else line
            # Update copy button text
            if task_index in self._task_copy_btns:
                self._task_copy_btns[task_index]._copy_text = self._task_log_text[task_index]
            current = getattr(log, '_content', '') or ''
            if isinstance(current, str):
                display_line = line
                if self._is_compact_terminal() and len(line) > 80:
                    display_line = line[:77] + "..."
                new_content = current + "\n" + display_line if current else display_line
            else:
                new_content = line  # fallback
            log.update(new_content)

    def complete_task(self, task_index: int, success: bool, steps: int, elapsed: float, error: str = "", tokens: int = 0) -> None:
        """标记任务完成，折叠其日志，更新 header"""
        if task_index < len(self._task_summaries):
            self._task_summaries[task_index]["status"] = "done"
            self._task_summaries[task_index]["tokens"] = tokens
            self._done += 1

        if task_index in self._task_collapse:
            is_step_limit = "步数上限" in error or "步数限制" in error
            if success:
                icon = "✓"
            elif is_step_limit:
                icon = "⏱"
            else:
                icon = "✗"
            if success:
                parts = [f"{steps}步", f"{elapsed:.1f}s"]
                if tokens > 0:
                    if tokens >= 1000:
                        parts.append(f"~{tokens/1000:.1f}K tokens")
                    else:
                        parts.append(f"{tokens} tokens")
                summary = " · ".join(parts)
                title = f"{icon} {self._task_summaries[task_index]['name']}  {summary}"
            elif is_step_limit:
                title = f"{icon} {self._task_summaries[task_index]['name']}  步数不足 ({steps}步)"
            else:
                title = f"{icon} {self._task_summaries[task_index]['name']}  {error}"
            self._task_collapse[task_index].title = title
            self._task_collapse[task_index].collapsed = True  # 完成后折叠

        if self._header is not None:
            self._header.update(self._render_header())

    # Keep backward compatibility: add_result still works for old code
    def add_result(self, result) -> None:
        """兼容旧接口：直接添加完成结果"""
        idx = len(self._task_summaries)
        task_name = f"任务{idx + 1}"
        self.add_task(idx, task_name)
        self.complete_task(idx, success=result.success, steps=result.steps, elapsed=result.elapsed, error=result.error or "", tokens=getattr(result, 'tokens', 0))

    def on_copy_button_copied(self, event: CopyButton.Copied) -> None:
        event.stop()
        self.app.copy_to_clipboard(event.text)
        self.app.notify("已复制到剪贴板", severity="information", timeout=2)

    def _is_compact_terminal(self) -> bool:
        """Check if terminal is too small for full display (< 40 rows)."""
        try:
            import shutil
            size = shutil.get_terminal_size()
            return size.lines < 40
        except Exception:
            return False
