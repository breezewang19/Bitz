"""LLM 适配器 — Anthropic 原生协议，带重试"""
import time
import random


class LLMError(Exception):
    pass


class LLMAdapter:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514",
                 base_url: str = "https://api.anthropic.com"):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            import httpx
            self._client = anthropic.Anthropic(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=httpx.Timeout(120.0, connect=10.0),
            )
        return self._client

    def chat(self, messages: list[dict], tools: list[dict] = None,
             max_retries: int = 3) -> tuple[str, list]:
        """调用 LLM，返回 (stop_reason, content_blocks)"""
        import anthropic
        for attempt in range(max_retries):
            try:
                return self._chat_once(messages, tools)
            except LLMError:
                raise
            except (anthropic.RateLimitError,
                    anthropic.InternalServerError,
                    anthropic.APIConnectionError,
                    anthropic.APITimeoutError) as e:
                if attempt < max_retries - 1:
                    base_wait = 2 ** (attempt + 1)
                    jitter = base_wait * random.uniform(-0.2, 0.2)
                    time.sleep(max(1, base_wait + jitter))
                    continue
                raise LLMError(f"重试耗尽 ({max_retries} 次): {e}") from e
            except anthropic.BadRequestError as e:
                raise LLMError(f"请求参数错误: {e}") from e
            except Exception as e:
                raise LLMError(f"API 请求失败: {e}") from e

    def _chat_once(self, messages: list[dict], tools: list[dict] = None) -> tuple[str, list]:
        client = self._get_client()
        system_prompt = ""
        conversation = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                conversation.append(msg)

        kwargs = {
            "model": self.model,
            "messages": conversation,
            "max_tokens": 16384,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = [
                {"name": t["name"], "description": t.get("description", ""),
                 "input_schema": t.get("input_schema", {})}
                for t in tools
            ]

        response = client.messages.create(**kwargs)
        stop_reason = response.stop_reason

        if stop_reason == "end_turn":
            text = "".join(b.text for b in response.content if b.type == "text")
            return "end_turn", [{"type": "text", "text": text}]

        if stop_reason == "tool_use":
            blocks = []
            for b in response.content:
                if b.type == "text":
                    blocks.append({"type": "text", "text": b.text})
                elif b.type == "tool_use":
                    blocks.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
            return "tool_use", blocks

        # max_tokens or other
        text = "".join(b.text for b in response.content if b.type == "text")
        return stop_reason, [{"type": "text", "text": text}]
