# agent/builtin_tools.py
"""内置工具定义 - Agent 的核心能力"""
import subprocess
import re
import urllib.request

from agent.tools import ToolRegistry

MAX_OUTPUT = 30000
HALF_OUTPUT = MAX_OUTPUT // 2

# spawn 工具定义（供 ToolRegistry._execute_spawn 使用）
SPAWN_TOOL_DEF = {
    "name": "spawn",
    "description": (
        "启动子 Agent 执行任务。\n"
        "\n"
        "可用 Agent 类型：\n"
        "- general-purpose: 通用 Agent，可搜索代码、读写文件，适合复杂多步骤任务\n"
        "- explore: 快速探索代码库，搜索文件和关键词，只读模式\n"
        "- plan: 架构设计 Agent，制定实现计划，只读模式\n"
        "\n"
        "提示词编写指南：\n"
        "- 像对刚进来的聪明同事一样简明扼要地说明任务\n"
        "- 不要写\"根据你的发现修复bug\"——这把综合判断推给了 Agent\n"
        "- 包含文件路径、行号、具体要改什么\n"
        "- 简短的命令式提示词会产生肤浅的结果\n"
        "- 提供足够的上下文让 Agent 能做出判断\n"
        "\n"
        "并行执行：\n"
        "- 当多个任务互相独立时，使用 tasks 参数并行启动多个 Agent\n"
        "- 对于有共享上下文的并行任务，使用 mode='fork' 共享提示缓存"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "单个任务描述。与 tasks 二选一。",
            },
            "tasks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "多个任务描述列表，将并发执行。与 task 二选一。",
            },
            "context_hint": {
                "type": "string",
                "description": "附加上下文信息，会随任务一起传递给子 Agent。",
            },
            "max_steps": {
                "type": "integer",
                "description": "每个子 Agent 最大执行步数，默认 10。",
                "default": 10,
            },
            "max_workers": {
                "type": "integer",
                "description": "最大并发数，默认 3。",
                "default": 3,
            },
            "agent_type": {
                "type": "string",
                "default": "general-purpose",
                "enum": ["general-purpose", "explore", "plan"],
                "description": "子 Agent 类型，决定可用工具和权限。general-purpose: 全部工具; explore: 只读探索; plan: 只读规划。",
            },
            "mode": {
                "type": "string",
                "enum": ["independent", "fork"],
                "default": "independent",
                "description": "执行模式: independent (独立上下文) 或 fork (共享父 prompt cache)。",
            },
        },
    },
}


def _truncate(text: str, limit: int = MAX_OUTPUT) -> str:
    """截断过长文本，保留首尾，中间省略"""
    if len(text) <= limit:
        return text
    head = text[:HALF_OUTPUT]
    tail = text[-HALF_OUTPUT:]
    omitted = len(text) - len(head) - len(tail)
    return f"{head}\n... [省略 {omitted} 字符] ...\n{tail}"


def create_tools() -> ToolRegistry:
    """创建并注册所有内置工具"""
    tools = ToolRegistry()

    # 只读命令白名单：这些命令自动批准，不需要确认
    READONLY_COMMANDS = {
        'ls', 'pwd', 'echo', 'cat', 'head', 'tail', 'wc', 'find', 'which',
        'whoami', 'hostname', 'date', 'uname', 'df', 'du', 'env', 'printenv',
        'git status', 'git log', 'git diff', 'git branch', 'git remote',
        'git show', 'git blame', 'git tag',
    }

    # 额外的危险命令关键词
    DANGEROUS_PATTERNS = [
        'rm -rf', 'rm -r', 'shutdown', 'reboot', 'mkfs', 'dd if=',
        'pip install', 'pip3 install', 'npm install -g',
        'python -c', 'python3 -c',
        'curl | sh', 'curl | bash', 'wget | sh', 'wget | bash',
        '> /dev/sd', 'chmod 777', 'chown',
    ]

    def bash_handler(command: str) -> str:
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=30
            )
            output = result.stdout or result.stderr or "(no output)"
            return _truncate(output)
        except Exception as e:
            return f"Error: {e}"

    def bash_is_readonly(command: str) -> bool:
        """判断命令是否为只读命令"""
        stripped = command.strip()
        # 精确匹配白名单
        if stripped in READONLY_COMMANDS:
            return True
        # 白名单前缀匹配（如 "ls -la", "git log --oneline"）
        first_word = stripped.split()[0] if stripped.split() else ""
        for ro in READONLY_COMMANDS:
            if ro.startswith(first_word) and stripped.startswith(ro):
                return True
        return False

    def bash_is_dangerous(command: str) -> bool:
        """判断命令是否包含危险操作"""
        lower = command.lower()
        return any(p in lower for p in DANGEROUS_PATTERNS)

    def read_file_handler(path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            return _truncate(content)
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

    # SSRF 保护：禁止访问内网地址
    BLOCKED_HOSTS = {
        '169.254.169.254',  # AWS/GCP/Azure 元数据
        'metadata.google.internal',
        'localhost', '127.0.0.1', '0.0.0.0',
        '::1',  # IPv6 localhost
    }

    def fetch_handler(url: str) -> str:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            hostname = parsed.hostname or ""
            if hostname.lower() in BLOCKED_HOSTS or hostname.startswith(('10.', '172.16.', '172.17.', '172.18.', '172.19.', '172.2', '172.3', '192.168.')):
                return "Error: access to internal/private addresses is blocked"
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
        description="Execute a bash command. Use for running tests, installing packages, git operations, and other system commands. Avoid using bash for file reading/writing — prefer read_file/write_file/edit_file instead.",
        input_schema={
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"]
        },
        handler=bash_handler,
        dangerous=True,
        is_readonly=bash_is_readonly,
        is_extra_dangerous=bash_is_dangerous
    )

    tools.register(
        name="read_file",
        description="Read the full contents of a file. Use this to understand code before making changes.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"]
        },
        handler=read_file_handler
    )

    tools.register(
        name="write_file",
        description="Write content to a file, creating it if it doesn't exist or overwriting if it does. Use for creating new files or complete rewrites. For small changes, prefer edit_file.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["path", "content"]
        },
        handler=write_file_handler,
        dangerous=True
    )

    tools.register(
        name="edit_file",
        description="Replace a unique string in a file. old_string must appear exactly once in the file — if it matches multiple times, the operation fails. Use this for targeted edits instead of rewriting entire files.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"}
            },
            "required": ["path", "old_string", "new_string"]
        },
        handler=edit_file_handler,
        dangerous=True
    )

    tools.register(
        name="glob",
        description="Search for files by glob pattern (e.g. **/*.py, src/**/*.ts). Returns matching file paths.",
        input_schema={
            "type": "object",
            "properties": {"pattern": {"type": "string"}},
            "required": ["pattern"]
        },
        handler=glob_handler
    )

    tools.register(
        name="grep",
        description="Search file contents by regex pattern. Returns matching lines with file paths and line numbers. Use include to filter by file type (e.g. '*.py'). Prefer grep over bash grep for searching code.",
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

    # spawn 工具（handler 为占位，实际执行在 ToolRegistry._execute_spawn）
    tools.register(
        name=SPAWN_TOOL_DEF["name"],
        description=SPAWN_TOOL_DEF["description"],
        input_schema=SPAWN_TOOL_DEF["input_schema"],
        handler=lambda **kwargs: "",  # 占位 handler，不会被调用
    )

    return tools
