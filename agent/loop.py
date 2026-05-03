# agent/loop.py
"""Agent 核心循环 - Anthropic 协议"""
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from agent.context import Context
from agent.adapter import LLMAdapter, LLMResponse, LLMError


class Agent:
    """Agent 主循环"""

    def __init__(self, llm_adapter: LLMAdapter, tools, context: Context, max_steps: int = 10):
        self.llm_adapter = llm_adapter
        self.tools = tools
        self.context = context
        self.max_steps = max_steps
        self._pending_confirms: list = None  # list of (tool_id, tool_name, tool_args, result)
        self._confirmed_results: list = []   # 已确认但未写入上下文的工具结果
        self._on_text: callable = None  # 中间文字输出回调（由 TUI 设置）
        self.auto_confirm: bool = False  # 子 agent 自动确认
        self._step_count: int = 0  # 已执行步数
        self._hit_step_limit: bool = False  # 是否因步数限制退出
        self.permission_mode: str = "auto"  # "auto" | "readonly"

    def run(self, user_input: str | None = None, cancel_event: threading.Event = None,
            confirmed_tools: set = None, skip_add_user: bool = False) -> str:
        """核心循环

        Args:
            user_input: 用户输入
            cancel_event: 取消事件
            confirmed_tools: 已确认的工具调用 ID 集合，用于绕过确认继续执行
            skip_add_user: 跳过添加用户消息（用于确认后继续执行）
        """
        if not skip_add_user and user_input is not None:
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

            if cancel_event and cancel_event.is_set():
                return "[LLM Error] 已中断"

            if response.stop_reason == "end_turn":
                self.context.add_assistant_text(response.content)
                return response.content

            if response.stop_reason == "tool_use":
                # 提取文字块（LLM 的中间思考/说明），输出到 UI
                text_parts = []
                tool_blocks = []
                for block in response.content:
                    if block.get("type") == "text":
                        text_parts.append(block["text"])
                    elif block.get("type") == "tool_use":
                        tool_blocks.append(block)

                if text_parts and self._on_text:
                    self._on_text("\n".join(text_parts))

                pending_tools = []
                confirmed_results = []
                self._step_count += 1

                if len(tool_blocks) == 1:
                    # Single tool: execute inline (backward compat, no thread overhead)
                    tool_use = tool_blocks[0]
                    tool_name = tool_use["name"]
                    tool_args = tool_use["input"]
                    tool_id = tool_use["id"]

                    confirmed = tool_id in confirmed_tools
                    result = self.tools.execute(tool_name, tool_args, confirmed=confirmed, tool_id=tool_id, agent=self, on_event=None)

                    if result.startswith("[CONFIRM_REQUIRED]") and not confirmed:
                        if self.auto_confirm:
                            result = self.tools.execute(tool_name, tool_args, confirmed=True, tool_id=tool_id, on_event=None)
                            confirmed_results.append((tool_id, tool_name, tool_args, result))
                        else:
                            pending_tools.append((tool_id, tool_name, tool_args, result))
                    else:
                        confirmed_results.append((tool_id, tool_name, tool_args, result))
                else:
                    # Multiple tools: execute concurrently
                    tool_id_order = {tu["id"]: i for i, tu in enumerate(tool_blocks)}

                    def _execute_one(tu):
                        tool_name = tu["name"]
                        tool_args = tu["input"]
                        tool_id = tu["id"]
                        confirmed = tool_id in confirmed_tools
                        result = self.tools.execute(tool_name, tool_args, confirmed=confirmed, tool_id=tool_id, agent=self, on_event=None)
                        needs_confirm = result.startswith("[CONFIRM_REQUIRED]") and not confirmed
                        if needs_confirm and self.auto_confirm:
                            result = self.tools.execute(tool_name, tool_args, confirmed=True, tool_id=tool_id, on_event=None)
                            needs_confirm = False
                        return tool_id, tool_name, tool_args, result, needs_confirm

                    with ThreadPoolExecutor(max_workers=min(len(tool_blocks), 4)) as pool:
                        futures = {pool.submit(_execute_one, tu): tu["id"] for tu in tool_blocks}
                        for future in as_completed(futures):
                            tool_id, tool_name, tool_args, result, needs_confirm = future.result()
                            if needs_confirm:
                                pending_tools.append((tool_id, tool_name, tool_args, result))
                            else:
                                confirmed_results.append((tool_id, tool_name, tool_args, result))

                    # Sort by original tool_use order (Anthropic API expects ordered results)
                    confirmed_results.sort(key=lambda r: tool_id_order.get(r[0], 0))
                    pending_tools.sort(key=lambda r: tool_id_order.get(r[0], 0))

                if pending_tools:
                    self._pending_confirms = pending_tools
                    self._pending_response = response.content
                    self._confirmed_results = confirmed_results
                    return pending_tools[0][3]  # return first confirm message

                self.context.add_assistant_message(response.content)
                self.context.add_tool_results(
                    [(tool_id, result) for tool_id, tool_name, tool_args, result in confirmed_results]
                )
                continue

            if response.stop_reason == "max_tokens":
                self.context.add_assistant_text(response.content)
                self.context.add_user("请继续输出，不要重复已说过的内容。")
                continue

        self._hit_step_limit = True
        return f"Error: Exceeded max_steps ({self.max_steps})"

    def confirm_pending(self, confirmed_tools: set) -> tuple:
        """执行所有待确认的工具调用，将所有工具结果写入上下文，返回 (should_continue, result)"""
        if not self._pending_confirms:
            return (False, "No pending confirmation")

        # Save local copy before clearing
        pending = list(self._pending_confirms)
        self._pending_confirms = None

        # Add all pending tool_ids to confirmed_tools
        for tool_id, tool_name, tool_args, result in pending:
            confirmed_tools.add(tool_id)

        response_content = getattr(self, '_pending_response', None)
        if response_content:
            self.context.add_assistant_message(response_content)
            self._pending_response = None
        else:
            # Fallback: construct assistant message from all pending tool_use blocks
            blocks = []
            for tool_id, tool_name, tool_args, _ in pending:
                blocks.append({
                    "type": "tool_use",
                    "id": tool_id,
                    "name": tool_name,
                    "input": tool_args,
                })
            if blocks:
                self.context.add_assistant_message(blocks)

        # Re-execute all pending tools with confirmed=True
        all_results = list(self._confirmed_results)
        for tool_id, tool_name, tool_args, _ in pending:
            result = self.tools.execute(tool_name, tool_args, confirmed=True, tool_id=tool_id)
            all_results.append((tool_id, tool_name, tool_args, result))

        # Sort by original tool_use order
        tool_id_order = {tu["id"]: i for i, tu in enumerate(response_content) if isinstance(tu, dict) and tu.get("type") == "tool_use"}
        if tool_id_order:
            all_results.sort(key=lambda r: tool_id_order.get(r[0], 0))

        self._confirmed_results = []

        self.context.add_tool_results(
            [(tid, res) for tid, tname, targs, res in all_results]
        )
        return (True, all_results[-1][3])