# tests/test_execution_context.py
from agent.execution_context import ExecutionContext

def test_basic_creation():
    ctx = ExecutionContext(session_id="sess-1")
    assert ctx.session_id == "sess-1"
    assert ctx.task_base_dir is None
    assert ctx.agent is None
    assert ctx.on_event is None
    assert ctx.extra == {}

def test_full_creation():
    def dummy_event(*a, **kw): pass
    class DummyAgent: pass
    agent = DummyAgent()
    ctx = ExecutionContext(
        session_id="sess-2",
        task_base_dir="/tmp/tasks",
        agent=agent,
        on_event=dummy_event,
    )
    assert ctx.session_id == "sess-2"
    assert ctx.task_base_dir == "/tmp/tasks"
    assert ctx.agent is agent
    assert ctx.on_event is dummy_event

def test_extra_kwargs():
    ctx = ExecutionContext(session_id="s", extra={"key": "val"})
    assert ctx.extra["key"] == "val"
