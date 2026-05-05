# tests/test_tools.py
import pytest
from agent.tools import Tool, ToolRegistry
from agent.tool_result import ToolResult
from agent.execution_context import ExecutionContext


def test_tool_registry_register():
    registry = ToolRegistry()

    def dummy_handler(args: dict, context) -> ToolResult:
        return ToolResult.ok(f"got: {args.get('x', '')}")

    registry.register(
        name="echo",
        description="Echo back the input",
        input_schema={
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "required": ["x"]
        },
        handler=dummy_handler
    )

    assert "echo" in registry.tools
    assert registry.tools["echo"].name == "echo"


def test_tool_registry_execute():
    registry = ToolRegistry()
    registry.register(
        name="echo",
        description="Echo back",
        input_schema={"type": "object", "properties": {"x": {"type": "string"}}},
        handler=lambda args, context: ToolResult.ok(f"got: {args.get('x', '')}")
    )

    result = registry.execute("echo", {"x": "hello"})
    assert isinstance(result, ToolResult)
    assert result.success
    assert result.data == "got: hello"


def test_tool_registry_execute_error():
    """测试调用不存在的工具"""
    registry = ToolRegistry()
    result = registry.execute("nonexistent", {})
    assert isinstance(result, ToolResult)
    assert not result.success
    assert "Unknown tool" in result.error_message


def test_tool_registry_execute_handler_error():
    """测试工具执行出错"""
    registry = ToolRegistry()

    def bad_handler(args: dict, context) -> ToolResult:
        raise ValueError("test error")

    registry.register(
        name="bad",
        description="A bad tool",
        input_schema={"type": "object", "properties": {"x": {"type": "string"}}},
        handler=bad_handler
    )

    result = registry.execute("bad", {"x": "test"})
    assert isinstance(result, ToolResult)
    assert not result.success
    assert "test error" in result.error_message


def test_tool_registry_list_for_llm():
    registry = ToolRegistry()
    registry.register(
        name="echo",
        description="Echo back",
        input_schema={"type": "object", "properties": {"x": {"type": "string"}}},
        handler=lambda args, context: ToolResult.ok(args.get("x", ""))
    )

    tools = registry.list_for_llm()
    assert len(tools) == 1
    assert tools[0]["name"] == "echo"
    assert tools[0]["description"] == "Echo back"
    assert "input_schema" in tools[0]
