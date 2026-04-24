# agent/builtin_tools.py
"""内置工具定义 - Agent 的核心能力"""
import subprocess
import re
import urllib.request

from agent.tools import ToolRegistry


def create_tools() -> ToolRegistry:
    """创建并注册所有内置工具"""
    tools = ToolRegistry()

    def bash_handler(command: str) -> str:
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=30
            )
            return result.stdout or result.stderr or "(no output)"
        except Exception as e:
            return f"Error: {e}"

    def read_file_handler(path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error: {e}"

    def write_file_handler(path: str, content: str) -> str:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"OK: wrote {len(content)} chars to {path}"
        except Exception as e:
            return f"Error: {e}"

    def edit_file_handler(path: str, old_string: str, new_string: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            count = content.count(old_string)
            if count == 0:
                return f"Error: old_string not found in {path}"
            if count > 1:
                return f"Error: old_string found {count} times in {path}, must be unique"
            content = content.replace(old_string, new_string)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"OK: replaced 1 match in {path}"
        except Exception as e:
            return f"Error: {e}"

    def glob_handler(pattern: str) -> str:
        import glob
        try:
            matches = glob.glob(pattern, recursive=True)
            if not matches:
                return "No files found"
            return "\n".join(matches)
        except Exception as e:
            return f"Error: {e}"

    def grep_handler(pattern: str, path: str = ".", include: str = "") -> str:
        try:
            cmd = ["grep", "-rn", "--color=never", pattern]
            if include:
                cmd.extend(["--include", include])
            cmd.append(path)
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15
            )
            output = result.stdout or result.stderr or "No matches found"
            lines = output.splitlines()
            if len(lines) > 50:
                output = "\n".join(lines[:50]) + f"\n... ({len(lines) - 50} more lines)"
            return output
        except FileNotFoundError:
            return "Error: grep not found on this system"
        except Exception as e:
            return f"Error: {e}"

    def fetch_handler(url: str) -> str:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Bitz/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read(50000).decode("utf-8", errors="replace")
                if resp.headers.get_content_type() and "html" in resp.headers.get_content_type():
                    data = re.sub(r'<script[^>]*>.*?</script>', '', data, flags=re.DOTALL)
                    data = re.sub(r'<style[^>]*>.*?</style>', '', data, flags=re.DOTALL)
                    data = re.sub(r'<[^>]+>', ' ', data)
                    data = re.sub(r'\s+', ' ', data).strip()
                if len(data) > 10000:
                    data = data[:10000] + "\n... (truncated)"
                return data
        except Exception as e:
            return f"Error: {e}"

    tools.register(
        name="bash",
        description="Execute a bash command",
        input_schema={
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"]
        },
        handler=bash_handler
    )

    tools.register(
        name="read_file",
        description="Read file contents",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"]
        },
        handler=read_file_handler
    )

    tools.register(
        name="write_file",
        description="Write content to a file",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["path", "content"]
        },
        handler=write_file_handler
    )

    tools.register(
        name="edit_file",
        description="Replace a unique string in a file. old_string must be unique in the file.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"}
            },
            "required": ["path", "old_string", "new_string"]
        },
        handler=edit_file_handler
    )

    tools.register(
        name="glob",
        description="Search files by pattern (supports **/*.py etc.)",
        input_schema={
            "type": "object",
            "properties": {"pattern": {"type": "string"}},
            "required": ["pattern"]
        },
        handler=glob_handler
    )

    tools.register(
        name="grep",
        description="Search file contents by regex pattern. Optionally filter by file type with include (e.g. '*.py').",
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string", "description": "Directory or file to search in, default '.'"},
                "include": {"type": "string", "description": "File glob filter, e.g. '*.py'"}
            },
            "required": ["pattern"]
        },
        handler=grep_handler
    )

    tools.register(
        name="fetch",
        description="Fetch content from a URL. Strips HTML tags for web pages.",
        input_schema={
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"]
        },
        handler=fetch_handler
    )

    return tools
