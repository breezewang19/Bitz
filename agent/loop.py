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
        self._pending_confirm: tuple = None  # (tool_id, tool_name, tool_args, result)

    def run(self, user_input: str, cancel_event: threading.Event = None,
            confirmed_tools: set = None, skip_add_user: bool = False) -> str:
        """核心循环

        Args:
            user_input: 用户输入
            cancel_event: 取消事件
            confirmed_tools: 已确认的工具调用 ID 集合，用于绕过确认继续执行
            skip_add_user: 跳过添加用户消息（用于确认后继续执行）
        """
        if not skip_add_user:
            self.context.add_user(user_input)
        if confirmed_tools is None:
            confirmed_tools = set()

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
                # 先不添加 assistant 消息，等确认后再添加
                pending_tools = []
                confirmed_results = []

                # 先检查所有工具
                for tool_use in response.content:
                    tool_name = tool_use["name"]
                    tool_args = tool_use["input"]
                    tool_id = tool_use["id"]

                    # 检查是否已确认
                    confirmed = tool_id in confirmed_tools
                    result = self.tools.execute(tool_name, tool_args, confirmed=confirmed, tool_id=tool_id)

                    if result.startswith("[CONFIRM_REQUIRED]") and not confirmed:
                        pending_tools.append((tool_id, tool_name, tool_args, result))
                    else:
                        confirmed_results.append((tool_id, tool_name, tool_args, result))

                # 如果有待确认的工具，返回第一个
                if pending_tools:
                    tool_id, tool_name, tool_args, result = pending_tools[0]
                    self._pending_confirm = (tool_id, tool_name, tool_args, result)
                    return result

                # 所有工具都确认过了，添加 assistant 消息并执行
                self.context.add_assistant_message(response.content)
                for tool_id, tool_name, tool_args, result in confirmed_results:
                    self.context.add_tool_result(tool_id, result)
                continue

        return f"Error: Exceeded max_steps ({self.max_steps})"

    def confirm_pending(self, confirmed_tools: set) -> tuple:
        """执行待确认的工具调用，返回 (should_continue, response)"""
        if self._pending_confirm is None:
            return (False, "No pending confirmation")

        tool_id, tool_name, tool_args, _ = self._pending_confirm
        confirmed_tools.add(tool_id)
        self._pending_confirm = None

        # 先添加 assistant 消息
        # 注意：这里需要重建 tool_use 结构
        self.context.add_assistant_message([{
            "type": "tool_use",
            "id": tool_id,
            "name": tool_name,
            "input": tool_args
        }])

        result = self.tools.execute(tool_name, tool_args, confirmed=True, tool_id=tool_id)
        self.context.add_tool_result(tool_id, result)
        return (True, result)
