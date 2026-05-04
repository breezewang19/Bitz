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
    assert len(restored_ctx.messages) == 6
    assert restored_ctx.messages[0]["role"] == "user"
    assert restored_ctx.messages[0]["content"] == "What is Python?"
    assert restored_ctx.messages[4]["role"] == "user"
    assert restored_ctx.messages[4]["content"][0]["type"] == "tool_result"

    # 7. Continue conversation in restored context (with persistence)
    restored_ctx.add_user("Thanks!")
    restored_ctx.add_assistant_text("You're welcome!")

    # 8. Load again and verify continuation
    final_ctx, _ = restore_session(store, sid, system_prompt="You are helpful.")
    assert len(final_ctx.messages) == 8
    assert final_ctx.messages[-1]["content"] == "You're welcome!"


def test_no_persist_without_store():
    """Context without session_store should work exactly as before"""
    ctx = Context(system_prompt="test")
    ctx.add_user("hello")
    ctx.add_assistant_text("hi")
    assert len(ctx.messages) == 2


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


def test_persist_error_flag(tmp_path):
    """_persist_error flag is set when store.append_entry raises"""
    store = SessionStore(project_dir=str(tmp_path / "project"), base_dir=tmp_path / "bitz")
    sid = store.create_session(model="test")
    ctx = Context(system_prompt="test", session_id=sid, session_store=store)

    # Normal persist works
    ctx.add_user("hello")
    assert not ctx._persist_error

    # Make the JSONL path unwritable by deleting the directory and making parent read-only
    jsonl_path = store._jsonl_path(sid)
    jsonl_path.unlink()
    # Write a directory where the file should be to cause write failure
    jsonl_path.mkdir(parents=True, exist_ok=True)

    ctx.add_user("this should fail")
    assert ctx._persist_error


def test_new_session_after_restore(tmp_path):
    """After restoring, creating a new session keeps them independent"""
    store = SessionStore(project_dir=str(tmp_path / "project"), base_dir=tmp_path / "bitz")

    # First session
    sid1 = store.create_session(model="model-a")
    ctx1 = Context(system_prompt="test", session_id=sid1, session_store=store)
    ctx1.add_user("first session message")
    store.update_meta(sid1, title="Session 1")

    # Second session
    sid2 = store.create_session(model="model-b")
    ctx2 = Context(system_prompt="test", session_id=sid2, session_store=store)
    ctx2.add_user("second session message")
    store.update_meta(sid2, title="Session 2")

    # Verify independence
    msgs1 = store.load_session(sid1)
    msgs2 = store.load_session(sid2)
    assert len(msgs1) == 1
    assert len(msgs2) == 1
    assert msgs1[0]["content"] == "first session message"
    assert msgs2[0]["content"] == "second session message"

    # Verify list shows both
    sessions = store.list_sessions()
    assert len(sessions) == 2
