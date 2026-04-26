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
        self._confirmed_results: list = []   # 已确认但未写入上下文的工具结果

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
                self.context.add_assistant_text(response.content)
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
                    self._pending_response = response.content
                    # 保存已确认工具的结果，等 confirm_pending 时一起写入上下文
                    self._confirmed_results = confirmed_results
                    return result

                # 所有工具都确认过了，添加 assistant 消息并执行
                self.context.add_assistant_message(response.content)
                self.context.add_tool_results(
                    [(tool_id, result) for tool_id, tool_name, tool_args, result in confirmed_results]
                )
                continue

            # max_tokens 或其他 stop_reason：记录部分响应并返回
            self.context.add_assistant_text(response.content)
            if response.stop_reason == "max_tokens":
                return f"{response.content}\n\n[输出被截断，已达最大 token 限制]"
            return response.content

        return f"Error: Exceeded max_steps ({self.max_steps})"

    def confirm_pending(self, confirmed_tools: set) -> tuple:
        """执行待确认的工具调用，将所有工具结果写入上下文，返回 (should_continue, result)"""
        if self._pending_confirm is None:
            return (False, "No pending confirmation")

        tool_id, tool_name, tool_args, _ = self._pending_confirm
        confirmed_tools.add(tool_id)
        self._pending_confirm = None

        # 添加完整的 assistant 消息（包含所有 tool_use blocks）
        response_content = getattr(self, '_pending_response', None)
        if response_content:
            self.context.add_assistant_message(response_content)
            self._pending_response = None
        else:
            self.context.add_assistant_message([{
                "type": "tool_use",
                "id": tool_id,
                "name": tool_name,
                "input": tool_args
            }])

        # 执行确认的工具
        result = self.tools.execute(tool_name, tool_args, confirmed=True, tool_id=tool_id)

        # 收集所有工具结果：之前已确认的 + 刚确认的
        all_results = list(self._confirmed_results)
        all_results.append((tool_id, tool_name, tool_args, result))
        self._confirmed_results = []

        self.context.add_tool_results(
            [(tid, res) for tid, tname, targs, res in all_results]
        )
        return (True, result)
