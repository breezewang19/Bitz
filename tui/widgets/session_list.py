from __future__ import annotations

from datetime import datetime, timezone, timedelta

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Input, OptionList, Static
from rich.text import Text

from agent.session import SessionStore, SessionMeta

_BJT = timezone(timedelta(hours=8))


def _bjt_time(iso_str: str) -> str:
    """Convert ISO UTC string to Beijing time display."""
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_BJT).strftime("%m-%d %H:%M")
    except Exception:
        return iso_str[:16]


class SessionListScreen(ModalScreen):
    """会话历史列表弹窗"""

    BINDINGS = [
        Binding("escape", "dismiss", "关闭"),
    ]

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
    SessionListScreen #session-buttons {
        height: auto;
        margin-top: 1;
        align: center middle;
    }
    SessionListScreen #session-buttons Button {
        margin: 0 1;
    }
    """

    class Resume(Message):
        def __init__(self, session_id: str) -> None:
            self.session_id = session_id
            super().__init__()

    class Delete(Message):
        def __init__(self, session_id: str) -> None:
            self.session_id = session_id
            super().__init__()

    def __init__(self, store: SessionStore) -> None:
        super().__init__()
        self._store = store
        self._sessions: list[SessionMeta] = store.list_sessions()
        self._filtered: list[SessionMeta] = list(self._sessions)

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("会话历史", classes="session-title")
            yield Input(placeholder="搜索...", id="session-search")
            yield OptionList(id="session-options")
            with Horizontal(id="session-buttons"):
                yield Button("恢复", variant="primary", id="btn-resume")
                yield Button("删除", variant="error", id="btn-delete")

    def on_mount(self) -> None:
        self._populate(self._sessions)
        self.query_one("#session-search", Input).focus()

    def _populate(self, sessions: list[SessionMeta]) -> None:
        self._filtered = sessions
        ol = self.query_one("#session-options", OptionList)
        ol.clear_options()
        for m in sessions:
            label = Text.assemble(
                Text(m.title or "无标题", style="bold cyan"),
                Text(f"  ({m.model})", style="dim"),
                Text(f"  {m.turn_count}轮", style="dim"),
                Text(f"  {_bjt_time(m.updated_at)}", style="dim"),
            )
            ol.add_option(label)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "session-search":
            return
        query = event.value.strip().lower()
        if not query:
            self._populate(self._sessions)
            return
        filtered = [m for m in self._sessions
                    if query in (m.title or "").lower() or query in m.model.lower()]
        self._populate(filtered)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        idx = event.option_index
        if idx < len(self._filtered):
            self.post_message(self.Resume(self._filtered[idx].session_id))
            self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        ol = self.query_one("#session-options", OptionList)
        idx = ol.highlighted
        if idx is None or idx >= len(self._filtered):
            return
        session = self._filtered[idx]
        if event.button.id == "btn-resume":
            self.post_message(self.Resume(session.session_id))
            self.dismiss()
        elif event.button.id == "btn-delete":
            self._store.delete_session(session.session_id)
            self._sessions = [s for s in self._sessions if s.session_id != session.session_id]
            self._filtered.pop(idx)
            ol.remove_option_at_index(idx)
            if not self._sessions:
                self.dismiss()

    def action_dismiss(self) -> None:
        self.dismiss()
