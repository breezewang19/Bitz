# Session Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add JSONL-based chat session persistence to Bitz's Python agent layer with full TUI integration for session listing, restore, and management.

**Architecture:** New `agent/session.py` module provides `SessionStore` for file I/O. `Context` gets optional `_persist()` calls on each `add_*` method. TUI gets a `SessionListScreen` modal, a `SessionRestoreBanner` widget, and three new slash commands. All persistence is opt-in via `session_store` parameter — subagents and tests are unaffected.

**Tech Stack:** Python 3.10+, stdlib only (json, pathlib, threading, uuid, datetime), Textual for TUI components.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `agent/session.py` | SessionStore, SessionMeta, sanitize_path, restore_session |
| `agent/context.py` | Add session_id, _store, _persist() to Context |
| `tui/widgets/session_list.py` | SessionListScreen modal |
| `tui/widgets/session_banner.py` | SessionRestoreBanner widget |
| `tui/app.py` | Wire session_store, /sessions, /resume, /title commands, restore flow |
| `tui/widgets/status.py` | Add persistence error indicator |
| `tui.py` | Create SessionStore, pass to BitzApp |
| `tests/test_session.py` | Unit tests for SessionStore |
| `tests/test_context.py` | Update existing tests for _persist |

---

### Task 1: SessionStore core — create, append, load

**Files:**
- Create: `agent/session.py`
- Test: `tests/test_session.py`

- [ ] **Step 1: Write failing tests for SessionStore create/append/load**

```python
# tests/test_session.py
"""Session 持久化测试"""
import json
import pytest
from pathlib import Path
from agent.session import SessionStore, SessionMeta, sanitize_path


@pytest.fixture
def store(tmp_path):
    return SessionStore(project_dir=str(tmp_path / "my-project"))


def test_sanitize_path():
    assert sanitize_path("/Users/breeze/projects/Research/Bitz") == \
        "-Users-breeze-projects-Research-Bitz"


def test_create_session(store):
    sid = store.create_session(model="claude-sonnet-4-20250514")
    assert isinstance(sid, str) and len(sid) == 36  # UUID format
    meta = store.get_meta(sid)
    assert meta.model == "claude-sonnet-4-20250514"
    assert meta.session_id == sid
    assert meta.turn_count == 0


def test_append_and_load(store):
    sid = store.create_session(model="test-model")
    store.append_entry(sid, {"role": "user", "content": "hello", "uuid": "u1", "timestamp": "2026-01-01T00:00:00Z"})
    store.append_entry(sid, {"role": "assistant", "content": "hi there", "uuid": "u2", "timestamp": "2026-01-01T00:00:01Z"})
    messages = store.load_session(sid)
    assert len(messages) == 2
    assert messages[0] == {"role": "user", "content": "hello"}
    assert messages[1] == {"role": "assistant", "content": "hi there"}


def test_append_with_tool_use(store):
    sid = store.create_session(model="test-model")
    store.append_entry(sid, {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "Let me check"},
            {"type": "tool_use", "id": "toolu_01", "name": "bash", "input": {"command": "ls"}},
        ],
        "uuid": "u1",
        "timestamp": "2026-01-01T00:00:00Z",
    })
    store.append_entry(sid, {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "toolu_01", "content": "file.txt"}],
        "uuid": "u2",
        "timestamp": "2026-01-01T00:00:01Z",
    })
    messages = store.load_session(sid)
    assert len(messages) == 2
    assert messages[0]["role"] == "assistant"
    assert len(messages[0]["content"]) == 2
    assert messages[1]["role"] == "user"
    assert messages[1]["content"][0]["type"] == "tool_result"


def test_load_session_strips_metadata(store):
    sid = store.create_session(model="test-model")
    store.append_entry(sid, {"role": "user", "content": "hi", "uuid": "abc", "timestamp": "2026-01-01T00:00:00Z"})
    messages = store.load_session(sid)
    assert "uuid" not in messages[0]
    assert "timestamp" not in messages[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_session.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.session'`

- [ ] **Step 3: Implement SessionStore, SessionMeta, sanitize_path**

```python
# agent/session.py
"""Session 持久化 — JSONL append-only 存储"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def sanitize_path(name: str) -> str:
    s = "".join(c if c.isalnum() else "-" for c in name)
    return s[:200]


@dataclass
class SessionMeta:
    session_id: str
    title: str
    model: str
    project: str
    created_at: str
    updated_at: str
    turn_count: int
    first_prompt: str


class SessionStore:
    def __init__(self, project_dir: str, base_dir: Path | None = None):
        self._base = base_dir or Path.home() / ".bitz" / "sessions"
        self._slug = sanitize_path(project_dir)
        self._dir = self._base / self._slug
        self._lock = threading.Lock()

    def _jsonl_path(self, session_id: str) -> Path:
        return self._dir / f"{session_id}.jsonl"

    def _meta_path(self, session_id: str) -> Path:
        return self._dir / f"{session_id}.meta.json"

    def create_session(self, model: str) -> str:
        session_id = str(uuid4())
        self._dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        meta = SessionMeta(
            session_id=session_id,
            title="",
            model=model,
            project="",
            created_at=now,
            updated_at=now,
            turn_count=0,
            first_prompt="",
        )
        self._write_meta(session_id, meta)
        return session_id

    def append_entry(self, session_id: str, entry: dict) -> None:
        path = self._jsonl_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with self._lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)

    def load_session(self, session_id: str) -> list[dict]:
        path = self._jsonl_path(session_id)
        if not path.exists():
            return []
        messages = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = {k: v for k, v in entry.items() if k in ("role", "content")}
                messages.append(msg)
        return messages

    def get_meta(self, session_id: str) -> SessionMeta:
        path = self._meta_path(session_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        return SessionMeta(**data)

    def update_meta(self, session_id: str, **kwargs) -> None:
        meta = self.get_meta(session_id)
        for k, v in kwargs.items():
            if hasattr(meta, k):
                setattr(meta, k, v)
        meta.updated_at = datetime.now(timezone.utc).isoformat()
        self._write_meta(session_id, meta)

    def _write_meta(self, session_id: str, meta: SessionMeta) -> None:
        path = self._meta_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(meta), ensure_ascii=False, indent=2), encoding="utf-8")

    def list_sessions(self) -> list[SessionMeta]:
        if not self._dir.exists():
            return []
        metas = []
        for p in self._dir.glob("*.meta.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                metas.append(SessionMeta(**data))
            except Exception:
                continue
        metas.sort(key=lambda m: m.updated_at, reverse=True)
        return metas

    def delete_session(self, session_id: str) -> None:
        jsonl = self._jsonl_path(session_id)
        meta = self._meta_path(session_id)
        if jsonl.exists():
            jsonl.unlink()
        if meta.exists():
            meta.unlink()

    def get_latest_session(self) -> SessionMeta | None:
        sessions = self.list_sessions()
        return sessions[0] if sessions else None

    def search_sessions(self, query: str) -> list[tuple[SessionMeta, str]]:
        q = query.lower()
        results = []
        for meta in self.list_sessions():
            path = self._jsonl_path(meta.session_id)
            if not path.exists():
                continue
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if q in line.lower():
                        snippet = line[:200]
                        results.append((meta, snippet))
                        break
        return results


def restore_session(store: SessionStore, session_id: str, system_prompt: str = "") -> tuple[Context, SessionMeta]:
    """Restore a session into a fresh Context."""
    from agent.context import Context

    messages = store.load_session(session_id)
    meta = store.get_meta(session_id)
    context = Context(
        system_prompt=system_prompt,
        session_id=session_id,
        session_store=store,
    )
    context.messages = messages
    return context, meta
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_session.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agent/session.py tests/test_session.py
git commit -m "feat: add SessionStore with JSONL append-only persistence"
```

---

### Task 2: SessionStore — list, delete, search, error handling

**Files:**
- Modify: `agent/session.py`
- Modify: `tests/test_session.py`

- [ ] **Step 1: Write failing tests for list/delete/search/error handling**

```python
# Append to tests/test_session.py

def test_list_sessions(store):
    s1 = store.create_session(model="model-a")
    store.update_meta(s1, title="First")
    s2 = store.create_session(model="model-b")
    store.update_meta(s2, title="Second")
    sessions = store.list_sessions()
    assert len(sessions) == 2
    # Most recent first
    assert sessions[0].title == "Second"
    assert sessions[1].title == "First"


def test_delete_session(store):
    sid = store.create_session(model="test")
    store.append_entry(sid, {"role": "user", "content": "hi", "uuid": "u1", "timestamp": "2026-01-01T00:00:00Z"})
    store.delete_session(sid)
    assert not store._jsonl_path(sid).exists()
    assert not store._meta_path(sid).exists()


def test_search_sessions(store):
    sid = store.create_session(model="test")
    store.append_entry(sid, {"role": "user", "content": "debug the auth module", "uuid": "u1", "timestamp": "2026-01-01T00:00:00Z"})
    store.append_entry(sid, {"role": "assistant", "content": "I'll check the auth code", "uuid": "u2", "timestamp": "2026-01-01T00:00:01Z"})
    results = store.search_sessions("auth")
    assert len(results) == 1
    meta, snippet = results[0]
    assert meta.session_id == sid
    assert "auth" in snippet.lower()


def test_search_no_match(store):
    sid = store.create_session(model="test")
    store.append_entry(sid, {"role": "user", "content": "hello", "uuid": "u1", "timestamp": "2026-01-01T00:00:00Z"})
    results = store.search_sessions("nonexistent")
    assert len(results) == 0


def test_get_latest_session(store):
    s1 = store.create_session(model="model-a")
    store.update_meta(s1, title="Old")
    s2 = store.create_session(model="model-b")
    store.update_meta(s2, title="New")
    latest = store.get_latest_session()
    assert latest is not None
    assert latest.title == "New"


def test_get_latest_session_empty(store):
    assert store.get_latest_session() is None


def test_corrupted_jsonl_line_skipped(store):
    sid = store.create_session(model="test")
    path = store._jsonl_path(sid)
    # Write a valid line, then a corrupted line, then another valid line
    with open(path, "a", encoding="utf-8") as f:
        f.write('{"role":"user","content":"first","uuid":"u1","timestamp":"2026-01-01T00:00:00Z"}\n')
        f.write("THIS IS NOT JSON\n")
        f.write('{"role":"user","content":"third","uuid":"u3","timestamp":"2026-01-01T00:00:02Z"}\n')
    messages = store.load_session(sid)
    assert len(messages) == 2
    assert messages[0]["content"] == "first"
    assert messages[1]["content"] == "third"


def test_corrupted_meta_rebuild(store):
    sid = store.create_session(model="test")
    store.append_entry(sid, {"role": "user", "content": "hello world", "uuid": "u1", "timestamp": "2026-01-01T00:00:00Z"})
    # Corrupt the meta file
    meta_path = store._meta_path(sid)
    meta_path.write_text("NOT JSON", encoding="utf-8")
    with pytest.raises(Exception):
        store.get_meta(sid)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_session.py -v -k "list_sessions or delete_session or search or latest or corrupted"`
Expected: Some tests FAIL (list/delete/search/latest work from Task 1; corrupted tests may fail)

- [ ] **Step 3: Ensure all implementations are correct in agent/session.py**

The implementations from Task 1 already cover list, delete, search, get_latest. Corrupted JSONL line handling is already in `load_session` (the `try/except json.JSONDecodeError: continue` block). The corrupted meta test expects an exception, which is the correct behavior — we don't silently rebuild meta in this task.

- [ ] **Step 4: Run all session tests to verify they pass**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_session.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add agent/session.py tests/test_session.py
git commit -m "test: add SessionStore tests for list, delete, search, error handling"
```

---

### Task 3: Context integration — _persist() on add_* methods

**Files:**
- Modify: `agent/context.py`
- Modify: `tests/test_context.py`

- [ ] **Step 1: Write failing tests for Context._persist**

```python
# Append to tests/test_context.py

class FakeSessionStore:
    """In-memory fake for testing Context._persist"""
    def __init__(self):
        self.entries = []
        self.session_id = "test-session"

    def append_entry(self, session_id, entry):
        self.entries.append(entry)


def test_context_persist_user():
    store = FakeSessionStore()
    ctx = Context(system_prompt="test", session_id="s1", session_store=store)
    ctx.add_user("hello")
    assert len(store.entries) == 1
    assert store.entries[0]["role"] == "user"
    assert store.entries[0]["content"] == "hello"
    assert "uuid" in store.entries[0]
    assert "timestamp" in store.entries[0]


def test_context_persist_assistant_text():
    store = FakeSessionStore()
    ctx = Context(system_prompt="test", session_id="s1", session_store=store)
    ctx.add_assistant_text("response")
    assert len(store.entries) == 1
    assert store.entries[0]["role"] == "assistant"
    assert store.entries[0]["content"] == "response"


def test_context_persist_assistant_message():
    store = FakeSessionStore()
    ctx = Context(system_prompt="test", session_id="s1", session_store=store)
    content = [{"type": "tool_use", "id": "t1", "name": "bash", "input": {"command": "ls"}}]
    ctx.add_assistant_message(content)
    assert len(store.entries) == 1
    assert store.entries[0]["role"] == "assistant"
    assert store.entries[0]["content"] == content


def test_context_persist_tool_results():
    store = FakeSessionStore()
    ctx = Context(system_prompt="test", session_id="s1", session_store=store)
    ctx.add_tool_results([("t1", "output1"), ("t2", "output2")])
    assert len(store.entries) == 1
    assert store.entries[0]["role"] == "user"
    assert len(store.entries[0]["content"]) == 2
    assert store.entries[0]["content"][0]["tool_use_id"] == "t1"


def test_context_no_persist_without_store():
    ctx = Context(system_prompt="test")
    ctx.add_user("hello")
    # Should not raise — _persist is a no-op when _store is None
    assert len(ctx.messages) == 1


def test_context_add_tool_result_delegates_to_results():
    """add_tool_result (singular) delegates to add_tool_results, so _persist fires once"""
    store = FakeSessionStore()
    ctx = Context(system_prompt="test", session_id="s1", session_store=store)
    ctx.add_tool_result("t1", "output")
    assert len(store.entries) == 1
    assert store.entries[0]["role"] == "user"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_context.py -v -k "persist"`
Expected: FAIL — `TypeError: Context.__init__() got an unexpected keyword argument 'session_id'`

- [ ] **Step 3: Modify Context to add session_id, _store, and _persist**

Modify `agent/context.py`:

```python
# agent/context.py
"""Context 会话上下文管理 - Anthropic 协议"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


class Context:
    """会话上下文"""

    def __init__(self, system_prompt: str = "", max_tokens: int = 16384, keep_last_n: int = 10,
                 session_id: str | None = None, session_store=None):
        self.system_prompt = system_prompt
        self.messages: list[dict] = []
        self.max_tokens = max_tokens
        self.keep_last_n = keep_last_n
        self._active_skill = None
        self.session_id = session_id
        self._store = session_store

    def add_user(self, content: str) -> None:
        """添加用户消息"""
        msg = {"role": "user", "content": content}
        self.messages.append(msg)
        self._trim()
        self._persist(msg)

    def add_assistant_message(self, content: list) -> None:
        """添加 assistant 消息（包含 tool_use blocks）"""
        msg = {"role": "assistant", "content": content}
        self.messages.append(msg)
        self._trim()
        self._persist(msg)

    def add_assistant_text(self, text: str) -> None:
        """添加 assistant 纯文本消息"""
        msg = {"role": "assistant", "content": text}
        self.messages.append(msg)
        self._trim()
        self._persist(msg)

    def add_tool_result(self, tool_use_id: str, content: str) -> None:
        """添加单个 tool_result（兼容方法，用于 confirm_pending 等单工具场景）"""
        self.add_tool_results([(tool_use_id, content)])

    def add_tool_results(self, results: list[tuple[str, str]]) -> None:
        """添加多个 tool_result 到一条 user 消息（Anthropic API 要求同轮结果合并）"""
        blocks = []
        for tool_id, result in results:
            blocks.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": result,
            })
        msg = {"role": "user", "content": blocks}
        self.messages.append(msg)
        self._trim()
        self._persist(msg)

    def set_active_skill(self, skill) -> None:
        """设置当前活跃的 Skill"""
        self._active_skill = skill

    def clear_active_skill(self) -> None:
        """清除当前活跃的 Skill"""
        self._active_skill = None

    @property
    def active_skill(self):
        """返回当前活跃的 Skill"""
        return self._active_skill

    def _trim(self) -> None:
        """保持消息数量不超过 keep_last_n，保证 tool_use/tool_result 配对完整"""
        if len(self.messages) <= self.keep_last_n:
            return
        self.messages = self.messages[-self.keep_last_n:]
        while self.messages:
            first = self.messages[0]
            if first["role"] == "user" and isinstance(first.get("content"), list):
                has_tool_result = any(
                    isinstance(b, dict) and b.get("type") == "tool_result"
                    for b in first["content"]
                )
                if has_tool_result:
                    self.messages.pop(0)
                    continue
            break

    def _persist(self, msg: dict) -> None:
        """持久化消息到 JSONL（当 session_store 存在时）"""
        if self._store is None:
            return
        entry = {**msg, "uuid": str(uuid4()), "timestamp": datetime.now(timezone.utc).isoformat()}
        self._store.append_entry(self.session_id, entry)

    def get_messages(self) -> list[dict]:
        """返回完整消息列表（system 作为独立条目）"""
        msgs = [{"role": "system", "content": self.system_prompt}]
        msgs.extend(self.messages)

        if self._active_skill:
            skill = self._active_skill
            if skill.skill_dir:
                skill_section = f"\n\n{skill.summary()}"
            else:
                skill_section = f"\n\n[当前 Skill: {skill.name}]\n{skill.prompt}"
            msgs[0] = {**msgs[0], "content": msgs[0]["content"] + skill_section}

        return msgs
```

- [ ] **Step 4: Run all context tests to verify they pass**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_context.py -v`
Expected: All tests PASS (old + new)

- [ ] **Step 5: Commit**

```bash
git add agent/context.py tests/test_context.py
git commit -m "feat: add _persist() to Context for session persistence"
```

---

### Task 4: Wire SessionStore into app startup

**Files:**
- Modify: `tui.py`
- Modify: `tui/app.py`

- [ ] **Step 1: Modify tui.py to create SessionStore and pass to BitzApp**

In `tui.py`, after creating the `context`, create a `SessionStore` and associate it. The key change: `session_store` is created first, then used to create a session_id, then passed to both Context and BitzApp.

Find the existing block where `context` is created (around the `Context(...)` call) and modify it:

```python
from agent.session import SessionStore

# After existing adapter/model setup, before context creation:
session_store = SessionStore(project_dir=os.getcwd())
session_id = session_store.create_session(model=current.model)

# Modify the existing Context() call to include session_id and session_store:
context = Context(
    system_prompt=build_system_prompt(cwd=os.getcwd(), skill_registry=skill_registry),
    max_tokens=4096,
    keep_last_n=20,
    session_id=session_id,
    session_store=session_store,
)

# Modify the existing BitzApp() call to include session_store:
app = BitzApp(agent=agent, model_store=store, skill_registry=skill_registry, session_store=session_store)
app.run()
```

Note: `current` is the `ModelConfig` object already created in tui.py. `current.model` gives the model string.

- [ ] **Step 2: Modify BitzApp.__init__ to accept session_store**

In `tui/app.py`, update `__init__` — add `session_store=None` parameter and store it:

```python
def __init__(self, agent, model_store=None, skill_registry=None, session_store=None, **kwargs):
    super().__init__(**kwargs)
    self._agent = agent
    self._model_store = model_store
    self._skill_registry = skill_registry or SkillRegistry()
    self._session_store = session_store
    self._original_execute = agent.tools.execute
    # ... rest of __init__ unchanged ...
```

Note: The existing `__init__` already has `model_store=None` and `skill_registry=None` keyword args. Just add `session_store=None` after them.

- [ ] **Step 3: Update action_new_conversation to create new session**

In `tui/app.py`, replace `action_new_conversation`:

```python
def action_new_conversation(self) -> None:
    """清空对话和上下文，开始新对话。"""
    # Finalize old session meta
    if self._session_store and self._agent.context.session_id:
        self._session_store.update_meta(self._agent.context.session_id)

    chat = self.query_one(ChatLog)
    for child in list(chat.children):
        child.remove()

    # Create new session
    if self._session_store:
        model = self._agent.llm_adapter.model
        new_session_id = self._session_store.create_session(model=model)
        self._agent.context.session_id = new_session_id
        self._agent.context._store = self._session_store

    self._agent.context.messages.clear()
    self._agent.context.clear_active_skill()
    self._step_count = 0
    self._total_input_tokens = 0
    self._total_output_tokens = 0
    self._agent.llm_adapter._total_input_tokens = 0
    self._agent.llm_adapter._total_output_tokens = 0
    status = self.query_one(StatusBar)
    status.update_steps(0)
    status.update_tokens(0, 0)
    model_name = self._agent.llm_adapter.model
    chat.mount(BannerWidget(model_name=model_name))
```

- [ ] **Step 4: Update _process_agent_result to update session meta**

In `tui/app.py`, add to `_process_agent_result` after the token update block:

```python
# Update session meta after each turn
if self._session_store and self._agent.context.session_id:
    self._session_store.update_meta(
        self._agent.context.session_id,
        turn_count=self._step_count,
    )
```

- [ ] **Step 5: Set first_prompt in meta on first user message**

In `tui/app.py`, in `on_input_bar_message_submitted`, before `self._run_agent(event.text)`:

```python
# Set first_prompt and title on first user message
if self._session_store and self._agent.context.session_id:
    meta = self._session_store.get_meta(self._agent.context.session_id)
    if not meta.first_prompt:
        prompt_text = event.text[:80]
        self._session_store.update_meta(
            self._agent.context.session_id,
            first_prompt=prompt_text,
            title=prompt_text,
        )
```

- [ ] **Step 6: Add action_quit meta finalization**

In `tui/app.py`, modify `action_quit` to finalize session meta before exiting:

```python
def action_quit(self) -> None:
    if self._exiting:
        return
    # Finalize session meta on quit
    if self._session_store and self._agent.context.session_id:
        self._session_store.update_meta(self._agent.context.session_id)
    self._exiting = True
    chat = self.query_one(ChatLog)
    chat.mount(GoodbyeWidget())
```

- [ ] **Step 7: Populate project field in create_session**

In `tui.py`, after `session_id = session_store.create_session(model=current.model)`, add:

```python
session_store.update_meta(session_id, project=os.getcwd())
```

- [ ] **Step 8: Run existing TUI tests to verify nothing is broken**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_tui_app.py tests/test_tui_integration.py -v`
Expected: All existing tests PASS

- [ ] **Step 9: Commit**

```bash
git add tui.py tui/app.py
git commit -m "feat: wire SessionStore into app startup and new conversation flow"
```

---

### Task 5: SessionListScreen TUI component

**Files:**
- Create: `tui/widgets/session_list.py`
- Test: `tests/test_tui_session_list.py`

- [ ] **Step 1: Write failing test for SessionListScreen**

```python
# tests/test_tui_session_list.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_tui_session_list.py -v`
Expected: FAIL — `ImportError: cannot import name 'SessionListScreen'`

- [ ] **Step 3: Implement SessionListScreen**

```python
# tui/widgets/session_list.py
from __future__ import annotations

from textual.screen import ModalScreen
from textual.widgets import OptionList, Static, Input
from textual.containers import Vertical
from textual.message import Message
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_tui_session_list.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tui/widgets/session_list.py tests/test_tui_session_list.py
git commit -m "feat: add SessionListScreen TUI component"
```

---

### Task 6: SessionRestoreBanner TUI component

**Files:**
- Create: `tui/widgets/session_banner.py`
- Test: `tests/test_tui_session_banner.py`

- [ ] **Step 1: Write failing test for SessionRestoreBanner**

```python
# tests/test_tui_session_banner.py
"""SessionRestoreBanner TUI 测试"""
import pytest
from textual.app import App
from textual.widgets import Static


class BannerTestApp(App):
    def on_mount(self):
        from tui.widgets.session_banner import SessionRestoreBanner
        banner = SessionRestoreBanner(title="Test Session", turn_count=5)
        self.mount(banner)

    def on_session_restore_banner_restore(self, event):
        self.exit("restored")

    def on_session_restore_banner_skip(self, event):
        self.exit("skipped")


def test_banner_renders():
    async def run():
        app = BannerTestApp()
        async with app.run_test() as pilot:
            await pilot.press("r")
    import asyncio
    result = asyncio.run(run())
    assert result == "restored"


def test_banner_skip():
    async def run():
        app = BannerTestApp()
        async with app.run_test() as pilot:
            await pilot.press("escape")
    import asyncio
    result = asyncio.run(run())
    assert result == "skipped"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_tui_session_banner.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement SessionRestoreBanner**

```python
# tui/widgets/session_banner.py
from __future__ import annotations

from textual.widgets import Static
from textual.message import Message
from textual.binding import Binding
from rich.text import Text


class SessionRestoreBanner(Static):
    """启动时提示恢复上次会话。"""

    DEFAULT_CSS = """
    SessionRestoreBanner {
        color: $text-muted;
        margin: 0 1;
        height: 1;
    }
    """

    BINDINGS = [
        Binding("r", "restore", "恢复会话"),
        Binding("escape", "skip", "跳过"),
    ]

    class Restore(Message):
        pass

    class Skip(Message):
        pass

    def __init__(self, title: str, turn_count: int, **kwargs) -> None:
        self._title = title
        self._turn_count = turn_count
        super().__init__(**kwargs)

    def render(self) -> Text:
        return Text.assemble(
            Text("检测到上次会话: ", style="dim"),
            Text(f'"{self._title}" ', style="cyan"),
            Text(f"({self._turn_count}轮) ", style="dim"),
            Text("[r恢复 / Esc跳过]", style="bold"),
        )

    def action_restore(self) -> None:
        self.post_message(self.Restore())
        self.remove()

    def action_skip(self) -> None:
        self.post_message(self.Skip())
        self.remove()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_tui_session_banner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tui/widgets/session_banner.py tests/test_tui_session_banner.py
git commit -m "feat: add SessionRestoreBanner TUI component"
```

---

### Task 7: Wire slash commands and restore flow into BitzApp

**Files:**
- Modify: `tui/app.py`

- [ ] **Step 1: Add /sessions, /resume, /title commands to on_input_bar_command_submitted**

In `tui/app.py`, add to the `elif` chain in `on_input_bar_command_submitted`:

```python
elif command == "sessions":
    if self._session_store:
        from tui.widgets.session_list import SessionListScreen
        self.push_screen(SessionListScreen(self._session_store), self._on_sessions_result)
    else:
        chat.add_message("assistant", "会话管理未启用")
elif command == "resume":
    if self._session_store:
        target_id = args.strip() if args.strip() else None
        if target_id:
            self._do_resume_session(target_id)
        else:
            latest = self._session_store.get_latest_session()
            if latest:
                self._do_resume_session(latest.session_id)
            else:
                chat.add_message("assistant", "没有历史会话可恢复")
    else:
        chat.add_message("assistant", "会话管理未启用")
elif command == "title":
    if args.strip() and self._session_store and self._agent.context.session_id:
        self._session_store.update_meta(
            self._agent.context.session_id,
            title=args.strip(),
        )
        chat.add_message("assistant", f"会话标题已设置为: {args.strip()}")
    else:
        chat.add_message("assistant", "用法: /title <标题文本>")
```

- [ ] **Step 2: Add _on_sessions_result and _do_resume_session methods**

```python
def _on_sessions_result(self, result) -> None:
    if result is None:
        return
    action, session_id = result
    chat = self.query_one(ChatLog)
    if action == "resume":
        self._do_resume_session(session_id)
    elif action == "delete":
        if self._session_store:
            self._session_store.delete_session(session_id)
            chat.add_message("assistant", f"会话 {session_id[:8]}... 已删除")

def _do_resume_session(self, session_id: str) -> None:
    """恢复指定会话。"""
    from agent.session import restore_session
    from agent.prompt import build_system_prompt

    chat = self.query_one(ChatLog)
    if not self._session_store:
        chat.add_message("assistant", "会话管理未启用")
        return

    context, meta = restore_session(
        self._session_store,
        session_id,
        system_prompt=build_system_prompt(cwd=os.getcwd(), skill_registry=self._skill_registry),
    )
    self._agent.context = context

    # Re-render ChatLog
    for child in list(chat.children):
        child.remove()

    for msg in context.messages:
        role = msg["role"]
        content = msg["content"]
        if isinstance(content, list):
            # tool_use / tool_result blocks
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    chat.add_message("tool", block.get("content", "")[:200], tool_name="tool")
                elif isinstance(block, dict) and block.get("type") == "tool_use":
                    chat.add_message("tool", f"{block['name']}: {str(block.get('input', ''))[:80]}", tool_name=block["name"])
                elif isinstance(block, dict) and block.get("type") == "text":
                    chat.add_message("assistant", block["text"])
        elif isinstance(content, str):
            if role == "user":
                chat.add_message("user", content)
            else:
                chat.add_message("assistant", content)

    chat.mount(BannerWidget(model_name=self._agent.llm_adapter.model))
    chat.add_message("assistant", f"已恢复会话: **{meta.title or '无标题'}** ({meta.turn_count}轮)")
```

- [ ] **Step 3: Add startup restore banner in on_mount**

In `tui/app.py`, add to `on_mount` after the existing setup:

```python
# Show restore banner if there are history sessions
if self._session_store:
    latest = self._session_store.get_latest_session()
    if latest and latest.session_id != self._agent.context.session_id:
        from tui.widgets.session_banner import SessionRestoreBanner
        chat = self.query_one(ChatLog)
        chat.mount(SessionRestoreBanner(title=latest.title or "无标题", turn_count=latest.turn_count))
```

And add the banner event handlers:

```python
def on_session_restore_banner_restore(self, event) -> None:
    if self._session_store:
        latest = self._session_store.get_latest_session()
        if latest:
            self._do_resume_session(latest.session_id)

def on_session_restore_banner_skip(self, event) -> None:
    pass  # Banner already removed itself
```

- [ ] **Step 4: Add /sessions and /resume to /help output**

In the help_text string, add:

```python
"| `/sessions` | 打开会话历史列表 |\n"
"| `/resume [id]` | 恢复指定会话（无id时恢复最近的） |\n"
"| `/title <text>` | 设置当前会话标题 |\n"
```

- [ ] **Step 5: Run all TUI tests**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_tui_app.py tests/test_tui_integration.py tests/test_tui_session_list.py tests/test_tui_session_banner.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add tui/app.py
git commit -m "feat: wire /sessions, /resume, /title commands and restore flow into BitzApp"
```

---

### Task 8: Persistence error indicator in StatusBar

**Files:**
- Modify: `tui/widgets/status.py`
- Modify: `tui/app.py`

- [ ] **Step 1: Add persistence_error flag and indicator to StatusBar**

In `tui/widgets/status.py`, add:

```python
def __init__(self):
    super().__init__()
    self.model_name: str = ""
    self.step_count: int = 0
    self.input_tokens: int = 0
    self.output_tokens: int = 0
    self.persistence_error: bool = False
    self._left: Static | None = None
    self._right: Static | None = None
```

In `_render_left`, add after the tokens block:

```python
if self.persistence_error:
    parts.append(Text("⚠", style="red"))
```

Add method:

```python
def update_persistence_error(self, has_error: bool) -> None:
    self.persistence_error = has_error
    self._refresh()
```

- [ ] **Step 2: Wrap _persist in try/except and set error flag**

In `agent/context.py`, modify `_persist`:

```python
def _persist(self, msg: dict) -> None:
    if self._store is None:
        return
    entry = {**msg, "uuid": str(uuid4()), "timestamp": datetime.now(timezone.utc).isoformat()}
    try:
        self._store.append_entry(self.session_id, entry)
    except Exception:
        self._persist_error = True
```

Add `self._persist_error = False` to `__init__`.

- [ ]**Step 3: In BitzApp._process_agent_result, sync error flag to StatusBar**

```python
# Sync persistence error state
if hasattr(self._agent.context, '_persist_error'):
    status = self.query_one(StatusBar)
    status.update_persistence_error(self._agent.context._persist_error)
```

- [ ] **Step 4: Run all tests**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add agent/context.py tui/widgets/status.py tui/app.py
git commit -m "feat: add persistence error indicator in StatusBar"
```

---

### Task 9: Integration test — full round-trip

**Files:**
- Create: `tests/test_session_integration.py`

- [ ] **Step 1: Write integration test for full session lifecycle**

```python
# tests/test_session_integration.py
"""Session 持久化集成测试 — 完整生命周期"""
import pytest
from agent.session import SessionStore, restore_session
from agent.context import Context


def test_full_session_lifecycle(tmp_path):
    """Create session → add messages → persist → restore → continue"""
    store = SessionStore(project_dir=str(tmp_path / "project"), base_dir=tmp_path / "bitz")

    # 1. Create session
    sid = store.create_session(model="test-model")

    # 2. Create context with persistence
    ctx = Context(
        system_prompt="You are helpful.",
        session_id=sid,
        session_store=store,
    )

    # 3. Simulate a conversation
    ctx.add_user("What is Python?")
    ctx.add_assistant_text("Python is a programming language.")
    ctx.add_user("Show me a hello world")
    ctx.add_assistant_message([
        {"type": "text", "text": "Here's a hello world:"},
        {"type": "tool_use", "id": "toolu_01", "name": "bash", "input": {"command": "echo hello"}},
    ])
    ctx.add_tool_results([("toolu_01", "hello")])
    ctx.add_assistant_text("Done!")

    # 4. Update meta
    store.update_meta(sid, turn_count=2, first_prompt="What is Python?", title="What is Python?")

    # 5. Verify meta
    meta = store.get_meta(sid)
    assert meta.turn_count == 2
    assert meta.title == "What is Python?"
    assert meta.first_prompt == "What is Python?"

    # 6. Restore session into new context
    restored_ctx, restored_meta = restore_session(store, sid, system_prompt="You are helpful.")
    assert len(restored_ctx.messages) == 5
    assert restored_ctx.messages[0]["role"] == "user"
    assert restored_ctx.messages[0]["content"] == "What is Python?"
    assert restored_ctx.messages[3]["role"] == "user"
    assert restored_ctx.messages[3]["content"][0]["type"] == "tool_result"

    # 7. Continue conversation in restored context (with persistence)
    restored_ctx.add_user("Thanks!")
    restored_ctx.add_assistant_text("You're welcome!")

    # 8. Load again and verify continuation
    final_ctx, _ = restore_session(store, sid, system_prompt="You are helpful.")
    assert len(final_ctx.messages) == 7
    assert final_ctx.messages[-1]["content"] == "You're welcome!"


def test_no_persist_without_store():
    """Context without session_store should work exactly as before"""
    ctx = Context(system_prompt="test")
    ctx.add_user("hello")
    ctx.add_assistant_text("hi")
    assert len(ctx.messages) == 2
    # No exception, no side effects


def test_session_search_integration(tmp_path):
    store = SessionStore(project_dir=str(tmp_path / "project"), base_dir=tmp_path / "bitz")
    sid = store.create_session(model="test")
    ctx = Context(system_prompt="test", session_id=sid, session_store=store)
    ctx.add_user("debug the authentication module")
    ctx.add_assistant_text("I'll check the auth code")

    results = store.search_sessions("authentication")
    assert len(results) == 1
    meta, snippet = results[0]
    assert meta.session_id == sid
```

- [ ] **Step 2: Run integration test**

Run: `cd /Users/breeze/projects/Research/Bitz && python -m pytest tests/test_session_integration.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_session_integration.py
git commit -m "test: add session persistence integration tests"
```

---

### Task 10: Manual smoke test

**Files:** None (manual testing)

- [ ] **Step 1: Start Bitz TUI, send a message, quit**

Run: `cd /Users/breeze/projects/Research/Bitz && python tui.py`
- Type "hello" and press Enter
- Wait for response
- Press Ctrl+Q to quit

- [ ] **Step 2: Restart Bitz, verify restore banner appears**

Run: `cd /Users/breeze/projects/Research/Bitz && python tui.py`
- Verify SessionRestoreBanner shows with the previous session title
- Press Enter to restore
- Verify chat history is rendered
- Send a new message, verify it works

- [ ] **Step 3: Test /sessions command**

- Type `/sessions` — verify modal opens with session list
- Press Escape to close

- [ ] **Step 4: Test /title command**

- Type `/title My Test Session`
- Verify confirmation message appears

- [ ] **Step 5: Test /new command**

- Type `/new` — verify old session is finalized and new empty session starts
- Verify ChatLog is cleared

- [ ] **Step 6: Verify JSONL files on disk**

Run: `ls -la ~/.bitz/sessions/*/`
- Verify .jsonl and .meta.json files exist
- Run: `cat ~/.bitz/sessions/*/*.jsonl | head -5` — verify content is valid JSONL