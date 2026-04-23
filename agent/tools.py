# agent/tools.py
"""工具注册表 - 管理可用工具及其执行"""
from dataclasses import dataclass
from typing import Callable


@dataclass
class Tool:
    """工具定义"""
    name: str
    description: str
    input_schema: dict
    handler: Callable


class ToolRegistry:
    """工具注册表"""

    def __init__(self):
        self.tools: dict[str, Tool] = {}

    def register(self, name: str, description: str,
                 input_schema: dict, handler: Callable) -> None:
        """注册一个工具"""
        self.tools[name] = Tool(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=handler
        )

    def execute(self, name: str, args: dict) -> str:
        """执行工具，返回结果字符串"""
        if name not in self.tools:
            return f"Error: Unknown tool '{name}'"

        try:
            result = self.tools[name].handler(**args)
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
