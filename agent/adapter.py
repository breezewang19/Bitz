# agent/adapter.py
"""LLM 适配器 - Anthropic 协议"""
import json
import time
import random
import threading
from dataclasses import dataclass
from typing import Any, Generator


@dataclass
class LLMResponse:
    """LLM 响应"""
    content: str | list
    stop_reason: str


class LLMError(Exception):
    """LLM 请求错误"""
    pass


@dataclass
class StreamEvent:
    """流式事件"""
    type: str  # text_delta | tool_use | stop
    # text_delta 字段
    content: str = ""
    # tool_use 字段
    tool_id: str = ""
    tool_name: str = ""
    tool_input: dict = None
    # stop 字段
    stop_reason: str = ""


class LLMAdapter:
    """LLM 适配器（Anthropic 协议）"""

    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com", model: str = "claude-3-5-sonnet-20241022",
                 on_retry=None):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.api_url = f"{base_url}/v1/messages"
        self._on_retry = on_retry  # callback(err_msg, attempt, max_retries)
        self._last_usage = None  # 最近一次 API 响应的 usage 数据

    def chat(self, messages: list[dict], tools: list[dict], cancel_event: threading.Event = None, max_retries: int = 5) -> LLMResponse:
        """发送请求到 LLM（Anthropic 协议），带重试"""
        if cancel_event and cancel_event.is_set():
            raise LLMError("已中断")
        last_error = None
        for attempt in range(max_retries):
            try:
                return self._chat_once(messages, tools, cancel_event)
            except LLMError:
                raise
            except Exception as e:
                last_error = e
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
                    # 通知 UI 正在重试
                    if self._on_retry:
                        err_type = type(e).__name__
                        try:
                            self._on_retry(f"{err_type}: {str(e).strip()}", attempt + 1, max_retries)
                        except Exception:
                            pass
                    # exponential backoff: 2s, 4s, 8s, 16s, 32s + 20% jitter
                    base_wait = 2 ** (attempt + 1)
                    jitter = base_wait * random.uniform(-0.2, 0.2)
                    wait = max(1, base_wait + jitter)
                    # 尝试从 RateLimitError 中提取 Retry-After header
                    retry_after = self._get_retry_after(e)
                    if retry_after:
                        wait = max(wait, retry_after)
                    self._cancel_aware_sleep(wait, cancel_event)
                    continue
                # 构造详细错误信息
                err_type = type(e).__name__
                err_msg = str(e).strip()
                detail = f"{err_type}: {err_msg}" if err_msg else err_type
                if hasattr(anthropic, 'APIConnectionError') and isinstance(e, anthropic.APIConnectionError):
                    raise LLMError(f"API 连接失败 ({self.base_url}): {detail}\n已重试 {attempt + 1}/{max_retries} 次")
                if hasattr(anthropic, 'BadRequestError') and isinstance(e, anthropic.BadRequestError):
                    raise LLMError(f"请求参数错误: {detail}")
                raise LLMError(f"API 请求失败 ({self.base_url}): {detail}\n已重试 {attempt + 1}/{max_retries} 次")

    def _get_retry_after(self, exc: Exception) -> float | None:
        """从异常中提取 Retry-After header 值（秒）"""
        try:
            headers = getattr(exc, 'response', None)
            if headers and hasattr(headers, 'headers'):
                retry_after = headers.headers.get('retry-after')
                if retry_after:
                    return float(retry_after)
        except (ValueError, TypeError, AttributeError):
            pass
        return None

    def _cancel_aware_sleep(self, seconds: float, cancel_event: threading.Event = None) -> None:
        """分段 sleep，每 0.5s 检查一次 cancel_event"""
        end_time = time.monotonic() + seconds
        while time.monotonic() < end_time:
            if cancel_event and cancel_event.is_set():
                raise LLMError("已中断")
            time.sleep(min(0.5, end_time - time.monotonic()))

    def _chat_once(self, messages: list[dict], tools: list[dict], cancel_event: threading.Event = None, timeout: float = 120.0) -> LLMResponse:
        """单次请求 LLM，支持 cancel_event 打断和整体超时"""
        import anthropic  # 延迟导入，避免启动时加载 ~3s
        import httpx

        client = anthropic.Anthropic(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=10.0)
        )

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
            "max_tokens": 16384,
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
        start_time = time.monotonic()

        def api_call():
            try:
                result_holder[0] = client.messages.create(**kwargs)
            except Exception as e:
                error_holder[0] = e

        api_thread = threading.Thread(target=api_call, daemon=True)
        api_thread.start()

        # 轮询等待，每 100ms 检查一次 cancel_event 和超时
        while api_thread.is_alive():
            if cancel_event and cancel_event.is_set():
                api_thread.join(timeout=2)
                raise LLMError("已中断")
            if time.monotonic() - start_time > timeout + 10:
                # 超过超时 + 10s 宽限期，强制视为超时
                raise LLMError(f"API 请求超时 ({timeout}s)")
            api_thread.join(timeout=0.1)

        if error_holder[0] is not None:
            raise error_holder[0]

        response = result_holder[0]
        # 存储 usage 数据供 TUI 读取
        try:
            self._last_usage = response.usage
        except Exception:
            self._last_usage = None
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

    def stream_chat(self, messages: list[dict], tools: list[dict],
                    cancel_event: threading.Event = None,
                    max_retries: int = 5) -> Generator[StreamEvent, None, None]:
        """流式请求 LLM，yield StreamEvent 生成器。"""
        if cancel_event and cancel_event.is_set():
            raise LLMError("已中断")

        import anthropic
        import httpx

        client = anthropic.Anthropic(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=httpx.Timeout(120.0, connect=10.0)
        )

        # 分离 system prompt 和对话消息（与 _chat_once 相同逻辑）
        system_prompt = ""
        conversation_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                conversation_messages.append(msg)

        anthropic_messages = []
        for msg in conversation_messages:
            role = msg["role"]
            if role == "user":
                anthropic_messages.append({"role": "user", "content": msg["content"]})
            elif role == "assistant":
                if isinstance(msg.get("content"), list):
                    anthropic_messages.append({"role": "assistant", "content": msg["content"]})
                else:
                    anthropic_messages.append({"role": "assistant", "content": msg.get("content", "")})

        kwargs = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": 16384,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            anthropic_tools = []
            for tool in tools:
                anthropic_tools.append({
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("input_schema", {})
                })
            kwargs["tools"] = anthropic_tools

        # 流式请求
        try:
            with client.messages.stream(**kwargs) as stream:
                current_tool_id = None
                current_tool_name = None
                current_tool_input = {}

                for event in stream:
                    if cancel_event and cancel_event.is_set():
                        raise LLMError("已中断")

                    if event.type == "content_block_delta":
                        if hasattr(event, 'delta') and event.delta.type == "text_delta":
                            yield StreamEvent(type="text_delta", content=event.delta.text)
                        elif hasattr(event, 'delta') and event.delta.type == "input_json_delta":
                            # 工具输入的增量 JSON — 累积但不 yield
                            pass

                    elif event.type == "content_block_start":
                        if hasattr(event, 'content_block') and event.content_block.type == "tool_use":
                            current_tool_id = event.content_block.id
                            current_tool_name = event.content_block.name
                            current_tool_input = {}

                    elif event.type == "content_block_stop":
                        if current_tool_id is not None:
                            yield StreamEvent(
                                type="tool_use",
                                tool_id=current_tool_id,
                                tool_name=current_tool_name,
                                tool_input=current_tool_input,
                            )
                            current_tool_id = None
                            current_tool_name = None
                            current_tool_input = {}

                    elif event.type == "message_stop":
                        # 获取最终消息以提取 stop_reason 和 usage
                        try:
                            final = stream.get_final_message()
                            self._last_usage = final.usage
                            yield StreamEvent(type="stop", stop_reason=final.stop_reason)
                        except Exception:
                            yield StreamEvent(type="stop", stop_reason="end_turn")

        except LLMError:
            raise
        except Exception as e:
            # 流式失败，回退到同步重试
            err_type = type(e).__name__
            err_msg = str(e).strip()
            detail = f"{err_type}: {err_msg}" if err_msg else err_type
            raise LLMError(f"流式请求失败: {detail}")