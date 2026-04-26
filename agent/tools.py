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
                tool_id: str = None) -> str:
        """执行工具，返回结果字符串"""
        if name not in self.tools:
            return f"Error: Unknown tool '{name}'"

        tool = self.tools[name]

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
