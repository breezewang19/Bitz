# agent/context.py
"""Context 会话上下文管理 - Anthropic 协议"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


class Context:
    """会话上下文"""

    def __init__(self, system_prompt: str = "", max_tokens: int = 16384, keep_last_n: int = 30,
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

    def add_system_reminder(self, text: str) -> None:
        """Add a system reminder as a user message.

        The reminder is stored with a _meta key for internal tracking.
        get_messages() strips _meta before returning messages to the API.
        Intentionally skips _persist(): reminders are ephemeral nudges.
        """
        self.messages.append({
            "role": "user",
            "content": text,
            "_meta": True,
        })
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
        """保持消息数量不超过 keep_last_n，保护首条 user 消息，保证 tool_use/tool_result 配对完整"""
        if len(self.messages) <= self.keep_last_n:
            return

        # Protect the first user message (initial request)
        protected_indices: set[int] = set()
        for i, msg in enumerate(self.messages):
            if msg.get("role") == "user" and isinstance(msg.get("content"), str):
                protected_indices.add(i)
                break

        # Keep the last keep_last_n messages from the tail
        tail_start = len(self.messages) - self.keep_last_n
        tail_indices = set(range(tail_start, len(self.messages)))

        # Combine protected and tail, then rebuild from sorted retained indices
        retained = sorted(protected_indices | tail_indices)
        self.messages = [self.messages[i] for i in retained]

        self._ensure_pair_integrity()

    def _ensure_pair_integrity(self) -> None:
        """确保 tool_use 和 tool_result 配对完整，移除孤立块"""
        # Collect all tool_use IDs and tool_result IDs
        tool_use_ids: set[str] = set()
        tool_result_ids: set[str] = set()
        for msg in self.messages:
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "tool_use":
                            tool_use_ids.add(block.get("id"))
                        elif block.get("type") == "tool_result":
                            tool_result_ids.add(block.get("tool_use_id"))

        # Paired IDs are those that appear on both sides
        paired_ids = tool_use_ids & tool_result_ids

        # Rebuild messages, removing unpaired tool blocks
        new_messages: list[dict] = []
        for msg in self.messages:
            content = msg.get("content", [])
            if isinstance(content, str):
                new_messages.append(msg)
                continue

            if not isinstance(content, list):
                new_messages.append(msg)
                continue

            # Filter out unpaired tool blocks
            filtered_blocks: list[dict] = []
            has_unpaired = False
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "tool_use" and block.get("id") not in paired_ids:
                        has_unpaired = True
                        continue
                    if block.get("type") == "tool_result" and block.get("tool_use_id") not in paired_ids:
                        has_unpaired = True
                        continue
                filtered_blocks.append(block)

            if not filtered_blocks:
                # Message became empty after removing unpaired blocks — skip it
                continue

            if has_unpaired:
                new_messages.append({**msg, "content": filtered_blocks})
            else:
                new_messages.append(msg)

        self.messages = new_messages

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
        """返回完整消息列表（system 作为独立条目），剥离非标准键"""
        msgs = [{"role": "system", "content": self.system_prompt}]
        for msg in self.messages:
            clean = {k: v for k, v in msg.items() if k in ("role", "content")}
            msgs.append(clean)

        if self._active_skill:
            skill = self._active_skill
            if skill.skill_dir:
                skill_section = f"\n\n{skill.summary()}"
            else:
                skill_section = f"\n\n[当前 Skill: {skill.name}]\n{skill.prompt}"
            msgs[0] = {**msgs[0], "content": msgs[0]["content"] + skill_section}

        return msgs
