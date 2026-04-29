# agent/context.py
"""Context 会话上下文管理 - Anthropic 协议"""


class Context:
    """会话上下文"""

    def __init__(self, system_prompt: str = "", max_tokens: int = 16384, keep_last_n: int = 10):
        self.system_prompt = system_prompt
        self.messages: list[dict] = []
        self.max_tokens = max_tokens
        self.keep_last_n = keep_last_n
        self._active_skill = None

    def add_user(self, content: str) -> None:
        """添加用户消息"""
        self.messages.append({"role": "user", "content": content})
        self._trim()

    def add_assistant_message(self, content: list) -> None:
        """添加 assistant 消息（包含 tool_use blocks）"""
        self.messages.append({"role": "assistant", "content": content})
        self._trim()

    def add_assistant_text(self, text: str) -> None:
        """添加 assistant 纯文本消息"""
        self.messages.append({"role": "assistant", "content": text})
        self._trim()

    def add_tool_result(self, tool_use_id: str, content: str) -> None:
        """添加单个 tool_result（兼容方法，用于 confirm_pending 等单工具场景）"""
        self.add_tool_results([(tool_use_id, content)])

    def add_tool_results(self, results: list[tuple[str, str]]) -> None:
        """添加多个 tool_result 到一条 user 消息（Anthropic API 要求同轮结果合并）"""
        blocks = []
        for tool_id, result in results:
            blocks.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": result,
            })
        self.messages.append({"role": "user", "content": blocks})
        self._trim()

    def set_active_skill(self, skill) -> None:
        """设置当前活跃的 Skill"""
        self._active_skill = skill

    def clear_active_skill(self) -> None:
        """清除当前活跃的 Skill"""
        self._active_skill = None

    @property
    def active_skill(self):
        """返回当前活跃的 Skill"""
        return self._active_skill

    def _trim(self) -> None:
        """保持消息数量不超过 keep_last_n，保证 tool_use/tool_result 配对完整"""
        if len(self.messages) <= self.keep_last_n:
            return
        self.messages = self.messages[-self.keep_last_n:]
        # 确保 tool_result 有对应的 tool_use：如果第一条消息是 tool_result，
        # 说明对应的 assistant tool_use 消息被裁掉了，必须一起移除
        while self.messages:
            first = self.messages[0]
            if first["role"] == "user" and isinstance(first.get("content"), list):
                has_tool_result = any(
                    isinstance(b, dict) and b.get("type") == "tool_result"
                    for b in first["content"]
                )
                if has_tool_result:
                    self.messages.pop(0)
                    continue
            break

    def get_messages(self) -> list[dict]:
        """返回完整消息列表（system 作为独立条目）"""
        msgs = [{"role": "system", "content": self.system_prompt}]
        msgs.extend(self.messages)

        # 动态拼接 Skill prompt 到 system 消息
        if self._active_skill:
            skill_section = f"\n\n[当前 Skill: {self._active_skill.name}]\n{self._active_skill.prompt}"
            msgs[0] = {**msgs[0], "content": msgs[0]["content"] + skill_section}

        return msgs