# agent/tools.py
"""工具注册表 - 管理可用工具及其执行"""
import os
import re
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class Tool:
    """工具定义"""
    name: str
    description: str
    input_schema: dict
    handler: Callable
    dangerous: bool = False  # 是否需要危险操作确认
    is_readonly: Optional[Callable] = None  # 判断参数是否为只读操作
    is_extra_dangerous: Optional[Callable] = None  # 判断参数是否为额外危险操作


# 危险操作模式
DANGEROUS_PATTERNS = [
    (r'^\s*rm\s', "删除文件/目录"),
    (r'^\s*del\s', "删除文件 (Windows)"),
    (r'dd\s+.*of=', "磁盘写入 (dd)"),
    (r'mkfs\s+', "格式化文件系统"),
    (r':\(\)\{\s*:\|\:\&\s*\};:', "Fork 炸弹"),
    (r'curl.*\|.*sh', "远程脚本执行"),
    (r'wget.*\|.*sh', "远程脚本执行"),
    (r'>\s*/dev/sd[a-z]', "直接写入设备"),
    (r'chmod\s+-R\s+777', "777权限设置"),
    (r'chown\s+.*-R', "递归修改所有者"),
    (r'sudo\s+rm\s+-rf\s+/', "危险: 递归删除系统目录"),
]


# Allowlist of readonly bash commands (base command → allowed subcommands or None for all)
_READONLY_BASE_COMMANDS = {
    "ls", "cat", "head", "tail", "less", "more", "wc",
    "grep", "rg", "ag", "ack",
    "find", "locate", "which", "whereis", "type",
    "file", "stat", "du", "df",
    "echo", "printf",  # only if no redirect
    "pwd", "whoami", "id", "uname", "hostname",
    "env", "printenv",  # only reading, no setting
    "test", "[", "[[",
    "true", "false",
    "git",  # subcommand-filtered below
    "gh",   # subcommand-filtered below
    "npm",  # subcommand-filtered below (list, view, etc.)
}

_READONLY_GIT_SUBCOMMANDS = {
    "status", "log", "diff", "show", "branch", "tag", "remote",
    "stash", "blame", "shortlog", "describe", "reflog",
    "ls-files", "ls-remote", "ls-tree",
    "rev-parse", "rev-list",
    "config", "--list",
}

_READONLY_GH_SUBCOMMANDS = {
    "pr", "view", "list", "api",
}

_READONLY_NPM_SUBCOMMANDS = {
    "list", "ls", "view", "info", "outdated",
}

_REDIRECT_PATTERN = re.compile(
    r'[|>`;]'  # pipe, redirect, backtick, semicolon — could chain dangerous commands
)

_COMMAND_SUBSTITUTION_PATTERN = re.compile(
    r'\$\('  # $(...) command substitution
)


def _is_readonly_command(cmd: str) -> bool:
    """Check if a bash command is safe for readonly permission mode."""
    cmd = cmd.strip()
    if not cmd:
        return True

    # Block commands with pipes, redirects, backticks, semicolons, or command substitution
    if _REDIRECT_PATTERN.search(cmd) or _COMMAND_SUBSTITUTION_PATTERN.search(cmd):
        return False

    parts = cmd.split()
    base = parts[0]

    # Handle path-qualified commands (e.g., /usr/bin/git)
    if "/" in base:
        base = base.rsplit("/", 1)[-1]

    if base not in _READONLY_BASE_COMMANDS:
        return False

    # Subcommand filtering for git
    if base == "git" and len(parts) > 1:
        subcmd = parts[1]
        if subcmd.startswith("-"):
            return True  # flags like git --version are safe
        if subcmd not in _READONLY_GIT_SUBCOMMANDS:
            return False

    # Subcommand filtering for gh
    if base == "gh" and len(parts) > 1:
        subcmd = parts[1]
        if subcmd not in _READONLY_GH_SUBCOMMANDS:
            return False

    # Subcommand filtering for npm
    if base == "npm" and len(parts) > 1:
        subcmd = parts[1]
        if subcmd not in _READONLY_NPM_SUBCOMMANDS:
            return False

    return True


def check_dangerous_bash(command: str) -> Optional[str]:
    """检测危险 bash 命令，返回原因或 None"""
    for pattern, reason in DANGEROUS_PATTERNS:
        if re.search(pattern, command):
            return reason
    return None


def check_dangerous_write(path: str) -> bool:
    """检测写文件是否为危险覆盖操作"""
    return os.path.exists(path)


class ToolRegistry:
    """工具注册表"""

    def __init__(self):
        self.tools: dict[str, Tool] = {}

    def register(self, name: str, description: str,
                 input_schema: dict, handler: Callable,
                 dangerous: bool = False,
                 is_readonly: Callable = None,
                 is_extra_dangerous: Callable = None) -> None:
        """注册一个工具"""
        self.tools[name] = Tool(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=handler,
            dangerous=dangerous,
            is_readonly=is_readonly,
            is_extra_dangerous=is_extra_dangerous
        )

    def execute(self, name: str, args: dict, confirmed: bool = False,
                tool_id: str = None, agent=None, on_event=None) -> str:
        """执行工具，返回结果字符串"""
        # spawn 工具特殊处理
        if name == "spawn":
            return self._execute_spawn(args, agent, on_event=on_event)

        if name not in self.tools:
            return f"Error: Unknown tool '{name}'"

        tool = self.tools[name]

        # Readonly permission mode enforcement
        if hasattr(agent, 'permission_mode') and agent.permission_mode == "readonly":
            if name == "bash" and "command" in args:
                if not _is_readonly_command(args["command"]):
                    return "错误：只读模式下不允许执行此命令"
            elif name in ("write_file", "edit_file"):
                return "错误：只读模式下不允许写入文件"

        # 只读命令自动批准，不需要确认
        if tool.dangerous and tool.is_readonly:
            try:
                if name == "bash" and "command" in args and tool.is_readonly(args["command"]):
                    confirmed = True
            except Exception:
                pass

        # 危险操作需要确认
        if tool.dangerous and not confirmed:
            # 额外危险检测（如 rm -rf, shutdown）
            if tool.is_extra_dangerous:
                try:
                    if name == "bash" and "command" in args and tool.is_extra_dangerous(args["command"]):
                        return f"[CONFIRM_REQUIRED] {tool_id or ''} 危险命令: {args['command']}"
                except Exception:
                    pass
            # bash 危险命令检测
            if name == "bash" and "command" in args:
                reason = check_dangerous_bash(args["command"])
                if reason:
                    return f"[CONFIRM_REQUIRED] {tool_id or ''} {reason}"
            # 写文件覆盖检测
            if name == "write_file" and "path" in args:
                if check_dangerous_write(args["path"]):
                    return f"[CONFIRM_REQUIRED] {tool_id or ''} 覆盖已有文件"
            # edit_file 需要确认
            if name == "edit_file":
                return f"[CONFIRM_REQUIRED] {tool_id or ''} 修改文件内容"

        try:
            result = tool.handler(**args)
            return str(result)
        except Exception as e:
            return f"Error executing {name}: {e}"

    def filter_for_agent(self, agent_def: "AgentDefinition") -> "ToolRegistry":
        """Return a new registry with tools filtered by agent definition's disallowed_tools."""
        from agent.agent_definition import AgentDefinition

        filtered = ToolRegistry()
        for name, tool in self.tools.items():
            if name not in agent_def.disallowed_tools:
                filtered.register(
                    name=name,
                    description=tool.description,
                    input_schema=tool.input_schema,
                    handler=tool.handler,
                    dangerous=tool.dangerous,
                    is_readonly=tool.is_readonly,
                    is_extra_dangerous=tool.is_extra_dangerous,
                )
        return filtered

    def list_for_llm(self) -> list[dict]:
        """返回给 LLM 的工具定义列表"""
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema
            }
            for t in self.tools.values()
        ]

    def _execute_spawn(self, args: dict, agent=None, on_event=None) -> str:
        """执行 spawn 工具"""
        from agent.subagent import SubAgent, SubAgentSpec, run_parallel

        if agent is None:
            return "错误：spawn 需要主 Agent 引用"

        task = args.get("task")
        tasks = args.get("tasks", [])
        context_hint = args.get("context_hint")
        max_steps = args.get("max_steps")
        max_workers = args.get("max_workers", 3)
        agent_type = args.get("agent_type", "general-purpose")
        mode = args.get("mode", "independent")

        if not task and not tasks:
            return "错误：必须提供 task 或 tasks 参数"

        # Build fork messages if mode is fork
        fork_messages = None
        if mode == "fork":
            from agent.fork_message_builder import ForkMessageBuilder
            builder = ForkMessageBuilder()
            parent_ctx = getattr(agent, 'context', None)
            if parent_ctx is not None:
                parent_msgs = parent_ctx.get_messages()
                # The last assistant message is the one containing the spawn tool_use
                # Find the last assistant message in the conversation
                assistant_msg = None
                for msg in reversed(parent_msgs):
                    if msg.get("role") == "assistant" and isinstance(msg.get("content"), list):
                        assistant_msg = msg
                        break
                if assistant_msg is None:
                    return "错误：fork 模式需要父 Agent 的 assistant 消息"

                # Build directives from task or tasks
                directives = [task] if task else tasks
                fork_message_lists = builder.build_forked_messages(parent_msgs, assistant_msg, directives)
                # For single task, use first (and only) fork message list
                # For parallel tasks, each gets its own fork message list
                if task:
                    fork_messages = fork_message_lists[0] if fork_message_lists else None
            else:
                return "错误：fork 模式需要父 Agent 上下文"

        # 单任务
        if task:
            spec = SubAgentSpec(
                task=task,
                context_hint=context_hint,
                max_steps=max_steps,
                agent_type=agent_type,
                mode=mode,
            )
            sub = SubAgent(agent, spec, on_event=on_event, task_index=0, fork_messages=fork_messages)
            if on_event:
                on_event("task_start", 0, task_name=task[:50])
            result = sub.run()
            if result.success:
                token_info = f", {result.tokens} tokens" if result.tokens else ""
                return f"子 Agent [{agent_type}] 完成（{result.steps} 步，{result.elapsed:.1f}s{token_info}）:\n{result.output}"
            else:
                partial = f"\n部分输出:\n{result.output}" if result.output and not result.output.startswith("Error") else ""
                return f"子 Agent [{agent_type}] 未完成: {result.error}{partial}"

        # 并发多任务
        specs = [
            SubAgentSpec(
                task=t,
                context_hint=context_hint,
                max_steps=max_steps,
                agent_type=agent_type,
                mode=mode,
            )
            for t in tasks
        ]

        # For fork mode with multiple tasks, each task gets its own fork_messages
        if mode == "fork" and fork_message_lists:
            if on_event:
                for i, spec in enumerate(specs):
                    on_event("task_start", i, task_name=spec.task[:50])
            results = run_parallel(specs, agent, on_event=on_event, max_workers=max_workers, fork_messages_list=fork_message_lists)
        else:
            if on_event:
                for i, spec in enumerate(specs):
                    on_event("task_start", i, task_name=spec.task[:50])
            results = run_parallel(specs, agent, on_event=on_event, max_workers=max_workers)

        output_parts = []
        for i, r in enumerate(results):
            token_info = f" | {r.tokens} tokens" if r.tokens else ""
            if r.success:
                status = f"✓ 完成 | {r.steps} 步 | {r.elapsed:.1f}s{token_info}"
            else:
                status = f"✗ 未完成: {r.error}"
            output_parts.append(f"### 任务 {i + 1}: {specs[i].task[:50]}\n{status}\n{r.output}")

        return "\n\n---\n\n".join(output_parts)
