# agent/adapter.py
"""LLM 适配器 - Anthropic 协议"""
import json
import time
import threading
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMResponse:
    """LLM 响应"""
    content: str | list
    stop_reason: str


class LLMError(Exception):
    """LLM 请求错误"""
    pass


class LLMAdapter:
    """LLM 适配器（Anthropic 协议）"""

    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com", model: str = "claude-3-5-sonnet-20241022"):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.api_url = f"{base_url}/v1/messages"

    def chat(self, messages: list[dict], tools: list[dict], cancel_event: threading.Event = None, max_retries: int = 3) -> LLMResponse:
        """发送请求到 LLM（Anthropic 协议），带重试"""
        for attempt in range(max_retries):
            try:
                return self._chat_once(messages, tools, cancel_event)
            except LLMError:
                raise
            except Exception as e:
                import anthropic  # 延迟导入
                # 用 hasattr 兼容不同版本 anthropic SDK
                retryable = False
                for cls_name in ('OverloadedError', 'RateLimitError', 'APITimeoutError'):
                    cls = getattr(anthropic, cls_name, None)
                    if cls and isinstance(e, cls):
                        retryable = True
                if isinstance(e, (ConnectionError, TimeoutError, OSError)):
                    retryable = True
                if retryable and attempt < max_retries - 1:
                    wait = 2 ** attempt
                    time.sleep(wait)
                    continue
                # 不可重试的错误
                if hasattr(anthropic, 'APIConnectionError') and isinstance(e, anthropic.APIConnectionError):
                    raise LLMError(f"API 连接失败: {e}")
                if hasattr(anthropic, 'BadRequestError') and isinstance(e, anthropic.BadRequestError):
                    raise LLMError(f"请求参数错误: {e}")
                raise LLMError(f"API 请求失败: {e}")

    def _chat_once(self, messages: list[dict], tools: list[dict], cancel_event: threading.Event = None) -> LLMResponse:
        """单次请求 LLM，支持 cancel_event 打断"""
        import anthropic  # 延迟导入，避免启动时加载 ~3s

        client = anthropic.Anthropic(api_key=self.api_key, base_url=self.base_url)

        # 分离 system prompt 和对话消息
        system_prompt = ""
        conversation_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                conversation_messages.append(msg)

        # 转换为 Anthropic 格式: user/assistant
        anthropic_messages = []
        for msg in conversation_messages:
            role = msg["role"]
            if role == "user":
                anthropic_messages.append({
                    "role": "user",
                    "content": msg["content"]
                })
            elif role == "assistant":
                # 检查是否包含 tool_use
                if isinstance(msg.get("content"), list):
                    anthropic_messages.append({
                        "role": "assistant",
                        "content": msg["content"]
                    })
                else:
                    anthropic_messages.append({
                        "role": "assistant",
                        "content": msg.get("content", "")
                    })

        kwargs = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": 4096,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        if tools:
            # Anthropic 工具格式
            anthropic_tools = []
            for tool in tools:
                anthropic_tools.append({
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("input_schema", {})
                })
            kwargs["tools"] = anthropic_tools

        # 在后台线程执行 API 调用，主线程轮询 cancel_event
        result_holder = [None]
        error_holder = [None]

        def api_call():
            try:
                result_holder[0] = client.messages.create(**kwargs)
            except Exception as e:
                error_holder[0] = e

        api_thread = threading.Thread(target=api_call, daemon=True)
        api_thread.start()

        # 轮询等待，每 100ms 检查一次 cancel_event
        while api_thread.is_alive():
            if cancel_event and cancel_event.is_set():
                api_thread.join(timeout=2)
                raise LLMError("已中断")
            api_thread.join(timeout=0.1)

        if error_holder[0] is not None:
            raise error_holder[0]

        response = result_holder[0]
        stop_reason = response.stop_reason
        if stop_reason == "end_turn":
            # 提取文本内容（跳过 thinking）
            text_content = ""
            for block in response.content:
                if block.type == "text":
                    text_content += block.text
                elif block.type == "thinking":
                    pass
            return LLMResponse(content=text_content, stop_reason="end_turn")

        if stop_reason == "tool_use":
            # 解析工具调用
            blocks = []
            for block in response.content:
                if block.type == "tool_use":
                    blocks.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input
                    })
            return LLMResponse(content=blocks, stop_reason="tool_use")

        # 其他情况（如 max_tokens, thinking_closed）
        text_content = ""
        for block in response.content:
            if block.type == "text":
                text_content += block.text
        return LLMResponse(content=text_content, stop_reason=stop_reason)