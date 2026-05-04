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
