# agent/builtin_tools.py
"""内置工具定义 - Agent 的核心能力"""
import subprocess
import re
import urllib.request

from agent.tools import ToolRegistry
from agent.tasks import (
    create_task,
    get_task,
    list_tasks,
    update_task,
    delete_task,
    get_project_slug,
    is_blocked,
)

# Module-level base_dir override (used by tests to redirect task storage).
# When None, task functions use their default (~/.bitz/tasks).
_TASK_BASE_DIR = None
_TASK_SESSION_ID = None

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

    # -----------------------------------------------------------------------
    # Task tools
    # -----------------------------------------------------------------------

    def _task_kwargs():
        """Return common kwargs for task CRUD functions (slug, session_id, base_dir)."""
        kw = {"project_slug": get_project_slug()}
        # Inject session_id from the agent's context if available
        if _TASK_SESSION_ID is not None:
            kw["session_id"] = _TASK_SESSION_ID
        if _TASK_BASE_DIR is not None:
            kw["base_dir"] = _TASK_BASE_DIR
        return kw

    def task_create_handler(
        subject: str,
        description: str,
        active_form: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        kw = _task_kwargs()
        task = create_task(
            kw.pop("project_slug"),
            subject,
            description,
            active_form=active_form,
            metadata=metadata,
            **kw,
        )
        return f"Task #{task.id} created successfully: {task.subject}"

    def task_update_handler(
        task_id: str,
        subject: str | None = None,
        description: str | None = None,
        active_form: str | None = None,
        status: str | None = None,
        metadata: dict | None = None,
        add_blocks: list | None = None,
        add_blocked_by: list | None = None,
    ) -> str:
        kw = _task_kwargs()

        # Handle deletion as a special case
        if status == "deleted":
            delete_task(kw.pop("project_slug"), task_id, **kw)
            return f"Deleted task #{task_id}"

        # Build updates dict from non-None params
        updates: dict = {}
        if subject is not None:
            updates["subject"] = subject
        if description is not None:
            updates["description"] = description
        if active_form is not None:
            updates["active_form"] = active_form
        if status is not None:
            updates["status"] = status
        if metadata is not None:
            updates["metadata"] = metadata
        if add_blocks is not None:
            updates["add_blocks"] = add_blocks
        if add_blocked_by is not None:
            updates["add_blocked_by"] = add_blocked_by

        result = update_task(kw.pop("project_slug"), task_id, **updates, **kw)
        if result is None:
            return f"Task #{task_id} not found"

        changed_fields = ", ".join(updates.keys())
        return f"Updated task #{task_id} {changed_fields}"

    def task_list_handler() -> str:
        kw = _task_kwargs()
        all_tasks = list_tasks(kw.pop("project_slug"), **kw)

        # Filter out _internal tasks for display
        visible = [t for t in all_tasks if not t.metadata.get("_internal")]

        if not visible:
            return "No tasks"

        lines = []
        for t in visible:
            line = f"#{t.id} [{t.status.value}] {t.subject}"
            # Check if blocked by any unresolved blockers
            unresolved = []
            for blocker_id in t.blockedBy:
                blocker = next((x for x in all_tasks if x.id == blocker_id), None)
                if blocker is not None and blocker.status.value != "completed":
                    unresolved.append(blocker_id)
            if unresolved:
                line += f" [blocked by {', '.join(f'#{b}' for b in unresolved)}]"
            lines.append(line)

        return "\n".join(lines)

    def task_get_handler(task_id: str) -> str:
        kw = _task_kwargs()
        task = get_task(kw.pop("project_slug"), task_id, **kw)
        if task is None:
            return f"Task #{task_id} not found"

        lines = [
            f"Task #{task.id}: {task.subject}",
            f"Status: {task.status.value}",
        ]
        if task.activeForm:
            lines.append(f"Active form: {task.activeForm}")
        lines.append(f"Description: {task.description}")
        if task.blockedBy:
            lines.append(f"Blocked by: {', '.join(f'#{b}' for b in task.blockedBy)}")
        if task.blocks:
            lines.append(f"Blocks: {', '.join(f'#{b}' for b in task.blocks)}")

        return "\n".join(lines)

    tools.register(
        name="task_create",
        description=(
            "为当前编码会话创建结构化任务列表，帮助跟踪进度、组织复杂任务。\n"
            "\n"
            "## 何时使用\n"
            "- 复杂多步骤任务（3 步以上）\n"
            "- 需要仔细规划或多步操作的任务\n"
            "- 用户给出多个任务（编号或逗号分隔）\n"
            "- 收到新指令后，立即将需求捕获为任务\n"
            "- 开始工作时，先标记为 in_progress\n"
            "\n"
            "## 何时不使用\n"
            "- 单一简单任务\n"
            "- 任务可在 3 步以内轻松完成\n"
            "- 纯对话或信息查询\n"
            "\n"
            "## 字段\n"
            "- subject: 简短的祈使句标题（如\"修复登录流程的认证 bug\"）\n"
            "- description: 详细需求说明\n"
            "- activeForm: 进行中时显示在 spinner 的文本（如\"修复认证 bug\"），省略则显示 subject\n"
            "\n"
            "所有任务创建时状态为 pending。\n"
            "\n"
            "## 提示\n"
            "- 创建后用 task_update 设置依赖关系（blocks/blockedBy）\n"
            "- 先用 task_list 检查，避免创建重复任务"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "Brief title for the task"},
                "description": {"type": "string", "description": "Detailed description of the task"},
                "active_form": {"type": "string", "description": "Present-continuous form shown in spinner (e.g. 'Running tests')"},
                "metadata": {"type": "object", "description": "Arbitrary metadata key-value pairs"},
            },
            "required": ["subject", "description"],
        },
        handler=task_create_handler,
    )

    tools.register(
        name="task_update",
        description=(
            "更新任务列表中的任务。\n"
            "\n"
            "## 何时使用\n"
            "- 开始工作时标记为 in_progress\n"
            "- 完成工作时标记为 completed\n"
            "- 任务不再需要时标记为 deleted\n"
            "- 需求变化时更新描述\n"
            "- 设置任务间依赖关系\n"
            "\n"
            "## 完成条件\n"
            "仅在以下情况标记 completed：\n"
            "- 测试通过\n"
            "- 实现完整\n"
            "- 无未解决错误\n"
            "\n"
            "如果遇到阻塞或无法完成，保持 in_progress 并创建新任务描述阻塞原因。\n"
            "\n"
            "## 可更新字段\n"
            "- status: pending → in_progress → completed；deleted 永久删除\n"
            "- subject/description/activeForm: 更新任务内容\n"
            "- metadata: 合并元数据（设为 null 删除键）\n"
            "- add_blocks: 标记此任务完成后才能开始的任务\n"
            "- add_blocked_by: 标记必须先完成的任务\n"
            "\n"
            "## 示例\n"
            "开始工作：{\"task_id\": \"1\", \"status\": \"in_progress\"}\n"
            "完成工作：{\"task_id\": \"1\", \"status\": \"completed\"}\n"
            "删除任务：{\"task_id\": \"1\", \"status\": \"deleted\"}\n"
            "设置依赖：{\"task_id\": \"2\", \"add_blocked_by\": [\"1\"]}"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "ID of the task to update"},
                "subject": {"type": "string", "description": "New subject"},
                "description": {"type": "string", "description": "New description"},
                "active_form": {"type": "string", "description": "New active form"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed", "deleted"],
                    "description": "New status. 'deleted' removes the task.",
                },
                "metadata": {"type": "object", "description": "Metadata to merge (null values delete keys)"},
                "add_blocks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task IDs that this task blocks",
                },
                "add_blocked_by": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task IDs that block this task",
                },
            },
            "required": ["task_id"],
        },
        handler=task_update_handler,
        dangerous=True,
    )

    tools.register(
        name="task_list",
        description=(
            "列出任务列表中的所有任务。\n"
            "\n"
            "## 何时使用\n"
            "- 查看可用任务（pending 且未被阻塞）\n"
            "- 检查项目整体进度\n"
            "- 寻找被阻塞的任务\n"
            "- 完成一个任务后，查看下一个可用任务\n"
            "- 多个任务可用时，优先按 ID 顺序处理（低 ID 先做）\n"
            "\n"
            "## 输出\n"
            "每条任务显示：#id [状态] 标题，如有未解决的阻塞则显示 [blocked by #id]"
        ),
        input_schema={
            "type": "object",
            "properties": {},
        },
        handler=task_list_handler,
    )

    tools.register(
        name="task_get",
        description=(
            "按 ID 获取任务详情。\n"
            "\n"
            "## 何时使用\n"
            "- 开始工作前获取完整描述和上下文\n"
            "- 理解任务依赖（它阻塞谁、谁阻塞它）\n"
            "- 获取完整需求后再开始工作\n"
            "\n"
            "## 输出\n"
            "- subject: 任务标题\n"
            "- description: 详细需求和上下文\n"
            "- status: pending/in_progress/completed\n"
            "- blocks: 等待此任务完成的任务\n"
            "- blockedBy: 必须先完成的任务\n"
            "\n"
            "## 提示\n"
            "- 获取任务后，先检查 blockedBy 是否为空再开始工作\n"
            "- 用 task_list 查看所有任务概览"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "ID of the task to retrieve"},
            },
            "required": ["task_id"],
        },
        handler=task_get_handler,
    )

    return tools
