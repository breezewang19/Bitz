from __future__ import annotations

from textual.screen import ModalScreen
from textual.widgets import OptionList, Static, Input
from textual.containers import Vertical
from textual.message import Message
from textual.binding import Binding
from rich.text import Text

from agent.session import SessionStore, SessionMeta


class SessionListScreen(ModalScreen):
    """会话历史列表弹窗。"""

    DEFAULT_CSS = """
    SessionListScreen {
        align: center middle;
    }
    SessionListScreen > Vertical {
        width: 60;
        height: auto;
        max-height: 24;
        background: $surface;
        border: solid $primary;
        padding: 1 2;
    }
    SessionListScreen .session-title {
        text-align: center;
        margin-bottom: 1;
    }
    SessionListScreen Input {
        margin-bottom: 1;
    }
    SessionListScreen OptionList {
        height: auto;
        max-height: 16;
    }
    """

    class SessionAction(Message):
        def __init__(self, action: str, session_id: str | None) -> None:
            super().__init__()
            self.action = action
            self.session_id = session_id

    def __init__(self, store: SessionStore) -> None:
        super().__init__()
        self._store = store
        self._sessions: list[SessionMeta] = []

    def compose(self):
        with Vertical():
            yield Static("会话历史", classes="session-title")
            yield Input(placeholder="搜索...", id="session-search")
            option_list = OptionList(id="session-options")
            self._sessions = self._store.list_sessions()
            for m in self._sessions:
                label = Text.assemble(
                    Text(m.title or "无标题", style="bold cyan"),
                    Text(f"  ({m.model})", style="dim"),
                    Text(f"  {m.turn_count}轮", style="dim"),
                    Text(f"  {m.updated_at[:16]}", style="dim"),
                )
                option_list.add_option(label)
            yield option_list

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "session-search":
            return
        query = event.value.strip().lower()
        option_list = self.query_one("#session-options", OptionList)
        option_list.clear_options()
        for m in self._sessions:
            if query and query not in (m.title or "").lower() and query not in m.model.lower():
                continue
            label = Text.assemble(
                Text(m.title or "无标题", style="bold cyan"),
                Text(f"  ({m.model})", style="dim"),
                Text(f"  {m.turn_count}轮", style="dim"),
                Text(f"  {m.updated_at[:16]}", style="dim"),
            )
            option_list.add_option(label)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        idx = event.option_index
        if idx < len(self._sessions):
            self.dismiss(("resume", self._sessions[idx].session_id))

    BINDINGS = [
        Binding("d", "delete_selected", "删除"),
        Binding("escape", "close", "关闭"),
    ]

    def action_delete_selected(self) -> None:
        option_list = self.query_one("#session-options", OptionList)
        idx = option_list.highlighted
        if idx is not None and idx < len(self._sessions):
            self.dismiss(("delete", self._sessions[idx].session_id))

    def action_close(self) -> None:
        self.dismiss(None)
