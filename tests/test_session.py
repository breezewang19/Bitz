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
