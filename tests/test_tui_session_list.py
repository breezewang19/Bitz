"""SessionListScreen TUI 测试"""
import pytest
from textual.app import App
from agent.session import SessionStore, SessionMeta


class SessionTestApp(App):
    def __init__(self, store, **kwargs):
        super().__init__(**kwargs)
        self._store = store

    def on_mount(self):
        from tui.widgets.session_list import SessionListScreen
        self.push_screen(SessionListScreen(self._store), self._on_result)

    def _on_result(self, result):
        self.exit(result)


def test_session_list_displays_sessions(tmp_path):
    store = SessionStore(project_dir=str(tmp_path / "proj"))
    s1 = store.create_session(model="model-a")
    store.update_meta(s1, title="First Session")
    s2 = store.create_session(model="model-b")
    store.update_meta(s2, title="Second Session")

    app = SessionTestApp(store=store)
    # Just verify it mounts without error
    async def run():
        async with app.run_test() as pilot:
            await pilot.press("escape")
    import asyncio
    asyncio.run(run())
