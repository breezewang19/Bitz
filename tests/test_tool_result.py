# tests/test_tool_result.py
from agent.tool_result import ToolResult

def test_ok_factory():
    r = ToolResult.ok("hello")
    assert r.success is True
    assert r.data == "hello"
    assert r.error_message == ""
    assert r.confirm_required is False

def test_error_factory():
    r = ToolResult.error("something broke")
    assert r.success is False
    assert r.error_message == "something broke"
    assert r.data == ""
    assert r.confirm_required is False

def test_confirm_factory():
    r = ToolResult.confirm("dangerous command: rm -rf")
    assert r.success is False
    assert r.confirm_required is True
    assert r.confirm_message == "dangerous command: rm -rf"

def test_to_api_content_ok():
    r = ToolResult.ok("file contents")
    assert r.to_api_content() == "file contents"

def test_to_api_content_error():
    r = ToolResult.error("not found")
    assert r.to_api_content() == "Error: not found"

def test_to_api_content_confirm():
    r = ToolResult.confirm("dangerous op")
    assert r.to_api_content() == "[CONFIRM_REQUIRED] dangerous op"

def test_to_display_delegates_to_api_content():
    r = ToolResult.ok("data")
    assert r.to_display() == r.to_api_content()

def test_ok_with_metadata():
    r = ToolResult.ok("output", tokens=42)
    assert r.metadata == {"tokens": 42}
