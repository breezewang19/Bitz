# agent/loop.py
"""Agent 核心循环 - Anthropic 协议"""
import threading

from agent.context import Context
from agent.adapter import LLMAdapter, LLMResponse, LLMError


class Agent:
    """Agent 主循环"""

    def __init__(self, llm_adapter: LLMAdapter, tools, context: Context, max_steps: int = 10):
        self.llm_adapter = llm_adapter
        self.tools = tools
        self.context = context
        self.max_steps = max_steps

    def run(self, user_input: str, cancel_event: threading.Event = None) -> str:
        """核心循环"""
        self.context.add_user(user_input)

        for step in range(self.max_steps):
            messages = self.context.get_messages()
            tools = self.tools.list_for_llm() if hasattr(self.tools, 'list_for_llm') else []

            try:
                response = self.llm_adapter.chat(messages, tools, cancel_event=cancel_event)
            except LLMError as e:
                return f"[LLM Error] {e}"

            if response.stop_reason == "end_turn":
                return response.content

            if response.stop_reason == "tool_use":
                # 添加 assistant 的 tool_use 消息到 context
                self.context.add_assistant_message(response.content)

                # 执行工具并添加结果
                for tool_use in response.content:
                    tool_name = tool_use["name"]
                    tool_args = tool_use["input"]
                    tool_id = tool_use["id"]

                    result = self.tools.execute(tool_name, tool_args)
                    self.context.add_tool_result(tool_id, result)
                continue

        return f"Error: Exceeded max_steps ({self.max_steps})"
