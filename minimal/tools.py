"""工具注册与执行 — 5 个内置工具"""
import subprocess
import re
import shlex
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class ToolResult:
    output: str = ""
    is_error: bool = False
    needs_confirm: bool = False
    confirm_message: str = ""

    @staticmethod
    def ok(output: str) -> "ToolResult":
        return ToolResult(output=output)

    @staticmethod
    def error(msg: str) -> "ToolResult":
        return ToolResult(output=msg, is_error=True)

    @staticmethod
    def confirm(message: str) -> "ToolResult":
        return ToolResult(needs_confirm=True, confirm_message=message)


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    handler: Callable
    dangerous: bool = False
    is_readonly: Optional[Callable] = None


MAX_OUTPUT = 30000
HALF_OUTPUT = MAX_OUTPUT // 2

READONLY_COMMANDS = {
    "ls", "cat", "head", "tail", "find", "grep", "git", "echo",
    "pwd", "which", "type", "file", "wc", "diff",
}

_REDIRECT_PATTERN = re.compile(r'[|>;]')
_COMMAND_SUB_PATTERN = re.compile(r'\$\(|`')
_QUOTED_PATTERN = re.compile(r"'[^']*'|\"[^\"]*\"")


def bash_is_readonly(command: str) -> bool:
    try:
        parts = shlex.split(command.strip())
    except ValueError:
        return False
    if not parts:
        return True
    unquoted = _QUOTED_PATTERN.sub('', command)
    if _REDIRECT_PATTERN.search(unquoted) or _COMMAND_SUB_PATTERN.search(unquoted):
        return False
    base = parts[0].rsplit("/", 1)[-1]
    return base in READONLY_COMMANDS


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT:
        return text
    head = text[:HALF_OUTPUT]
    tail = text[-HALF_OUTPUT:]
    omitted = len(text) - len(head) - len(tail)
    return f"{head}\n... [省略 {omitted} 字符] ...\n{tail}"


class ToolRegistry:
    def __init__(self):
        self.tools: dict[str, Tool] = {}

    def register(self, name: str, description: str, input_schema: dict,
                 handler: Callable, dangerous: bool = False,
                 is_readonly: Callable = None) -> None:
        self.tools[name] = Tool(
            name=name, description=description, input_schema=input_schema,
            handler=handler, dangerous=dangerous, is_readonly=is_readonly,
        )

    def get(self, name: str) -> Optional[Tool]:
        return self.tools.get(name)

    def tool_definitions(self) -> list[dict]:
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in self.tools.values()
        ]

    def execute(self, name: str, args: dict, confirmed: bool = False) -> ToolResult:
        tool = self.tools.get(name)
        if tool is None:
            return ToolResult.error(f"Unknown tool '{name}'")

        # 只读命令自动批准
        if tool.dangerous and tool.is_readonly:
            try:
                if name == "bash" and "command" in args and tool.is_readonly(args["command"]):
                    confirmed = True
            except Exception:
                pass

        # 危险操作需要确认
        if tool.dangerous and not confirmed:
            if name == "bash" and "command" in args:
                return ToolResult.confirm(f"执行命令: {args['command']}")
            if name == "write_file" and "path" in args:
                return ToolResult.confirm(f"写入文件: {args['path']}")
            if name == "edit_file":
                return ToolResult.confirm(f"修改文件: {args.get('path', '')}")

        try:
            result = tool.handler(args)
            if isinstance(result, ToolResult):
                return result
            return ToolResult.ok(str(result))
        except Exception as e:
            return ToolResult.error(f"Error executing {name}: {e}")


def create_tools() -> ToolRegistry:
    registry = ToolRegistry()

    def bash_handler(args: dict) -> ToolResult:
        command = args.get("command", "")
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
            output = result.stdout or result.stderr or "(no output)"
            return ToolResult.ok(_truncate(output))
        except Exception as e:
            return ToolResult.error(f"Error: {e}")

    def read_file_handler(args: dict) -> ToolResult:
        path = args.get("path", "")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return ToolResult.ok(_truncate(f.read()))
        except Exception as e:
            return ToolResult.error(f"Error: {e}")

    def write_file_handler(args: dict) -> ToolResult:
        path = args.get("path", "")
        content = args.get("content", "")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return ToolResult.ok(f"OK: wrote {len(content)} chars to {path}")
        except Exception as e:
            return ToolResult.error(f"Error: {e}")

    def edit_file_handler(args: dict) -> ToolResult:
        path = args.get("path", "")
        old_string = args.get("old_string", "")
        new_string = args.get("new_string", "")
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            count = content.count(old_string)
            if count == 0:
                return ToolResult.error(f"old_string not found in {path}")
            if count > 1:
                return ToolResult.error(f"old_string found {count} times in {path}, must be unique")
            content = content.replace(old_string, new_string)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return ToolResult.ok(f"OK: replaced 1 match in {path}")
        except Exception as e:
            return ToolResult.error(f"Error: {e}")

    def glob_handler(args: dict) -> ToolResult:
        import glob as glob_mod
        pattern = args.get("pattern", "")
        try:
            matches = glob_mod.glob(pattern, recursive=True)
            if not matches:
                return ToolResult.ok("No files found")
            return ToolResult.ok("\n".join(matches))
        except Exception as e:
            return ToolResult.error(f"Error: {e}")

    registry.register(
        name="bash",
        description="Execute a bash command. Use for running tests, git operations, and system commands. Prefer read_file/write_file/edit_file for file operations.",
        input_schema={"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
        handler=bash_handler, dangerous=True, is_readonly=bash_is_readonly,
    )
    registry.register(
        name="read_file",
        description="Read the full contents of a file.",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        handler=read_file_handler,
    )
    registry.register(
        name="write_file",
        description="Write content to a file. Creates or overwrites. For small changes, prefer edit_file.",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
        handler=write_file_handler, dangerous=True,
    )
    registry.register(
        name="edit_file",
        description="Replace a unique string in a file. old_string must appear exactly once.",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}, "old_string": {"type": "string"}, "new_string": {"type": "string"}}, "required": ["path", "old_string", "new_string"]},
        handler=edit_file_handler, dangerous=True,
    )
    registry.register(
        name="glob",
        description="Search for files by glob pattern (e.g. **/*.py). Returns matching file paths.",
        input_schema={"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]},
        handler=glob_handler,
    )
    return registry
