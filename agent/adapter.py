# agent/adapter.py
"""LLM 适配器 - 封装 OpenAI 兼容 API 调用"""
import json
from dataclasses import dataclass
from typing import Any
import openai


@dataclass
class LLMResponse:
    """LLM 响应"""
    content: str | list
    stop_reason: str


class LLMAdapter:
    """LLM 适配器（OpenAI 兼容协议）"""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        """发送请求到 LLM"""
        client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)

        kwargs = {
            "model": self.model,
            "messages": messages,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        message = choice.message

        tool_calls = getattr(message, 'tool_calls', None)
        if tool_calls:
            blocks = []
            for tc in message.tool_calls:
                blocks.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": json.loads(tc.function.arguments)
                })
            return LLMResponse(content=blocks, stop_reason="tool_use")

        return LLMResponse(content=message.content or "", stop_reason="end_turn")
