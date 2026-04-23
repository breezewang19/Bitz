# agent/context.py
"""Context 会话上下文管理"""


class Context:
    """会话上下文"""

    def __init__(self, system_prompt: str = "", max_tokens: int = 4096, keep_last_n: int = 10):
        self.system_prompt = system_prompt
        self.messages: list[dict] = []
        self.max_tokens = max_tokens
        self.keep_last_n = keep_last_n

    def add_user(self, content: str) -> None:
        """添加用户消息"""
        self.messages.append({"role": "user", "content": content})
        self._trim()

    def add_tool_result(self, tool_use_id: str, content: str) -> None:
        """添加工具结果（role是user）"""
        self.messages.append({
            "role": "user",
            "tool_use_id": tool_use_id,
            "content": content
        })
        self._trim()

    def _trim(self) -> None:
        """保持消息数量不超过 keep_last_n"""
        if len(self.messages) > self.keep_last_n:
            self.messages = self.messages[-self.keep_last_n:]

    def get_messages(self) -> list[dict]:
        """返回包含 system prompt 的完整消息列表"""
        msgs = [{"role": "system", "content": self.system_prompt}]
        msgs.extend(self.messages)
        return msgs
