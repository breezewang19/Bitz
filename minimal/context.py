"""消息上下文管理 — Anthropic 协议"""


class Context:
    """会话上下文（纯内存，无持久化）"""

    def __init__(self, system_prompt: str = "", keep_last_n: int = 40):
        self.system_prompt = system_prompt
        self.messages: list[dict] = []
        self.keep_last_n = keep_last_n

    def add_user(self, content: str) -> None:
        msg = {"role": "user", "content": content}
        self.messages.append(msg)
        self._trim()

    def add_assistant_text(self, text: str) -> None:
        msg = {"role": "assistant", "content": text}
        self.messages.append(msg)
        self._trim()

    def add_assistant_message(self, content_blocks: list) -> None:
        msg = {"role": "assistant", "content": content_blocks}
        self.messages.append(msg)
        self._trim()

    def add_tool_results(self, results: list[tuple[str, str, bool]]) -> None:
        """results: [(tool_use_id, content, is_error), ...]"""
        blocks = []
        for tool_id, content, is_error in results:
            block = {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": content,
            }
            if is_error:
                block["is_error"] = True
            blocks.append(block)
        self.messages.append({"role": "user", "content": blocks})
        self._trim()
        self._ensure_pair_integrity()

    def get_messages(self) -> list[dict]:
        msgs = [{"role": "system", "content": self.system_prompt}]
        for msg in self.messages:
            clean = {k: v for k, v in msg.items() if k in ("role", "content")}
            msgs.append(clean)
        return msgs

    def _trim(self) -> None:
        if len(self.messages) <= self.keep_last_n:
            return
        protected = set()
        for i, msg in enumerate(self.messages):
            if msg.get("role") == "user" and isinstance(msg.get("content"), str):
                protected.add(i)
                break
        tail_start = len(self.messages) - self.keep_last_n
        retained = sorted(protected | set(range(tail_start, len(self.messages))))
        self.messages = [self.messages[i] for i in retained]
        self._ensure_pair_integrity()

    def _ensure_pair_integrity(self) -> None:
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
        paired = tool_use_ids & tool_result_ids
        new_messages: list[dict] = []
        for msg in self.messages:
            content = msg.get("content", [])
            if isinstance(content, str):
                new_messages.append(msg)
                continue
            if not isinstance(content, list):
                new_messages.append(msg)
                continue
            filtered: list[dict] = []
            has_unpaired = False
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "tool_use" and block.get("id") not in paired:
                        has_unpaired = True
                        continue
                    if block.get("type") == "tool_result" and block.get("tool_use_id") not in paired:
                        has_unpaired = True
                        continue
                filtered.append(block)
            if not filtered:
                continue
            if has_unpaired:
                new_messages.append({**msg, "content": filtered})
            else:
                new_messages.append(msg)
        self.messages = new_messages
