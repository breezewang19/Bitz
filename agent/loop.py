# agent/loop.py
"""Agent 核心循环 - Anthropic 协议"""
import threading

from agent.context import Context
from agent.adapter import LLMAdapter, LLMResponse, LLMError, StreamEvent


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
            confirmed_tools: set = None, skip_add_user: bool = False,
            on_text_delta=None) -> str:
        """核心循环（流式模式）

        Args:
            user_input: 用户输入
            cancel_event: 取消事件
            confirmed_tools: 已确认的工具调用 ID 集合，用于绕过确认继续执行
            skip_add_user: 跳过添加用户消息（用于确认后继续执行）
            on_text_delta: 文本增量回调，签名 on_text_delta(text: str)
        """
        if not skip_add_user:
            self.context.add_user(user_input)
        if confirmed_tools is None:
            confirmed_tools = set()

        for step in range(self.max_steps):
            messages = self.context.get_messages()
            tools = self.tools.list_for_llm() if hasattr(self.tools, 'list_for_llm') else []

            try:
                # 流式模式
                full_text = ""
                tool_uses = []
                stop_reason = None

                for event in self.llm_adapter.stream_chat(messages, tools, cancel_event=cancel_event):
                    if event.type == "text_delta":
                        full_text += event.content
                        if on_text_delta:
                            on_text_delta(event.content)
                    elif event.type == "tool_use":
                        tool_uses.append({
                            "type": "tool_use",
                            "id": event.tool_id,
                            "name": event.tool_name,
                            "input": event.tool_input or {},
                        })
                    elif event.type == "stop":
                        stop_reason = event.stop_reason

            except LLMError as e:
                return f"[LLM Error] {e}"

            if stop_reason == "end_turn":
                self.context.add_assistant_text(full_text)
                return full_text

            if stop_reason == "tool_use":
                pending_tools = []
                confirmed_results = []

                for tool_use in tool_uses:
                    tool_name = tool_use["name"]
                    tool_args = tool_use["input"]
                    tool_id = tool_use["id"]

                    confirmed = tool_id in confirmed_tools
                    result = self.tools.execute(tool_name, tool_args, confirmed=confirmed, tool_id=tool_id)

                    if result.startswith("[CONFIRM_REQUIRED]") and not confirmed:
                        pending_tools.append((tool_id, tool_name, tool_args, result))
                    else:
                        confirmed_results.append((tool_id, tool_name, tool_args, result))

                if pending_tools:
                    tool_id, tool_name, tool_args, result = pending_tools[0]
                    self._pending_confirm = (tool_id, tool_name, tool_args, result)
                    self._pending_response = tool_uses
                    self._confirmed_results = confirmed_results
                    return result

                self.context.add_assistant_message(tool_uses)
                self.context.add_tool_results(
                    [(tool_id, result) for tool_id, tool_name, tool_args, result in confirmed_results]
                )
                continue

            if stop_reason == "max_tokens":
                self.context.add_assistant_text(full_text)
                self.context.add_user("请继续输出，不要重复已说过的内容。")
                continue

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
