# agent/context.py
"""Context 会话上下文管理 - Anthropic 协议"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


class Context:
    """会话上下文"""

    def __init__(self, system_prompt: str = "", max_tokens: int = 16384, keep_last_n: int = 10,
                 session_id: str | None = None, session_store=None):
        self.system_prompt = system_prompt
        self.messages: list[dict] = []
        self.max_tokens = max_tokens
        self.keep_last_n = keep_last_n
        self._active_skill = None
        self.session_id = session_id
        self._store = session_store
        self._persist_error = False

    def add_user(self, content: str) -> None:
        """添加用户消息"""
        msg = {"role": "user", "content": content}
        self.messages.append(msg)
        self._trim()
        self._persist(msg)

    def add_assistant_message(self, content: list) -> None:
        """添加 assistant 消息（包含 tool_use blocks）"""
        msg = {"role": "assistant", "content": content}
        self.messages.append(msg)
        self._trim()
        self._persist(msg)

    def add_assistant_text(self, text: str) -> None:
        """添加 assistant 纯文本消息"""
        msg = {"role": "assistant", "content": text}
        self.messages.append(msg)
        self._trim()
        self._persist(msg)

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
        msg = {"role": "user", "content": blocks}
        self.messages.append(msg)
        self._trim()
        self._persist(msg)

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

    def _persist(self, msg: dict) -> None:
        """持久化消息到 JSONL（当 session_store 存在时）"""
        if self._store is None:
            return
        entry = {**msg, "uuid": str(uuid4()), "timestamp": datetime.now(timezone.utc).isoformat()}
        try:
            self._store.append_entry(self.session_id, entry)
        except Exception:
            self._persist_error = True

    def get_messages(self) -> list[dict]:
        """返回完整消息列表（system 作为独立条目）"""
        msgs = [{"role": "system", "content": self.system_prompt}]
        msgs.extend(self.messages)

        if self._active_skill:
            skill = self._active_skill
            if skill.skill_dir:
                skill_section = f"\n\n{skill.summary()}"
            else:
                skill_section = f"\n\n[当前 Skill: {skill.name}]\n{skill.prompt}"
            msgs[0] = {**msgs[0], "content": msgs[0]["content"] + skill_section}

        return msgs
