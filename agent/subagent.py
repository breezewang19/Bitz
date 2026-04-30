# agent/subagent.py
"""SubAgent — 子 Agent 执行器，支持并发和上下文隔离"""
from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from agent.adapter import LLMAdapter, LLMError
from agent.context import Context
from agent.loop import Agent
from agent.tools import ToolRegistry


def _format_args_summary(name: str, args: dict) -> str:
    """Extract display summary from tool args (simplified, avoids tui import)."""
    if name == "bash":
        return args.get('command', '')
    elif name == "read_file":
        return args.get('path', '')
    elif name == "write_file":
        path = args.get('path', '')
        chars = len(args.get('content', ''))
        return f"{path} ({chars} chars)" if path else ''
    elif name == "edit_file":
        return args.get('path', '')
    elif name == "glob":
        return args.get('pattern', '')
    elif name == "grep":
        pattern = args.get('pattern', '')
        path = args.get('path', '.')
        return f"{pattern} in {path}"
    elif name == "fetch":
        return args.get('url', '')
    else:
        return str(args) if args else ''


@dataclass
class SubAgentResult:
    """子 Agent 执行结果"""
    success: bool
    output: str
    steps: int = 0
    elapsed: float = 0.0
    error: str | None = None


@dataclass
class SubAgentSpec:
    """子 Agent 任务规格"""
    task: str
    context_hint: str = ""
    max_steps: int = 10
    model: str | None = None


class SubAgent:
    """子 Agent — 继承父配置，独立上下文，一次性执行"""

    def __init__(
        self,
        parent_agent,
        spec: SubAgentSpec,
        on_status: Callable[[str, str], None] | None = None,
        on_event: Callable | None = None,
        task_index: int = 0,
    ) -> None:
        self._spec = spec
        self._on_status = on_status
        self._on_event = on_event
        self._task_index = task_index
        self._task_id = str(id(self))

        # 继承父的 LLM 配置
        parent_llm = parent_agent.llm_adapter
        model = spec.model or parent_llm.model
        self._llm = LLMAdapter(
            api_key=parent_llm.api_key,
            base_url=parent_llm.base_url,
            model=model,
            protocol=parent_llm.protocol,
        )

        # 继承父的工具池（去掉 spawn 防递归）
        self._tools = ToolRegistry()
        for name, tool in parent_agent.tools.tools.items():
            if name != "spawn":
                self._tools.tools[name] = tool

        # 独立上下文：仅含 system prompt + 任务消息
        parent_ctx = parent_agent.context
        self._context = Context(system_prompt=parent_ctx.system_prompt)

        # 任务消息
        task_content = spec.task
        if spec.context_hint:
            task_content = f"{spec.task}\n\n---\n参考上下文:\n{spec.context_hint}"
        self._context.add_user(task_content)

        # 创建独立 Agent
        self._agent = Agent(
            llm_adapter=self._llm,
            tools=self._tools,
            context=self._context,
            max_steps=spec.max_steps,
        )
        self._agent.auto_confirm = True

        # 注入 _on_text 回调
        if self._on_event:
            idx = self._task_index
            def _on_text(text):
                self._on_event("text", idx, text=text)
            self._agent._on_text = _on_text

        # 注入工具执行日志
        if self._on_event:
            original_execute = self._tools.execute
            idx = self._task_index

            def logged_execute(name, args, confirmed=False, tool_id=None, agent=None, on_event=None):
                args_summary = _format_args_summary(name, args if isinstance(args, dict) else {})
                self._on_event("tool_start", idx, tool_name=name, args_summary=args_summary)
                result = original_execute(name, args, confirmed=confirmed, tool_id=tool_id, agent=agent, on_event=on_event)
                result_summary = (result or "")[:100]
                self._on_event("tool_end", idx, tool_name=name, result_summary=result_summary)
                return result

            self._tools.execute = logged_execute

    def run(self, cancel_event: threading.Event | None = None) -> SubAgentResult:
        """执行子 Agent 任务"""
        start = time.monotonic()
        try:
            if self._on_status:
                self._on_status(self._task_id, "running")
            result_text = self._agent.run(
                user_input=None,
                cancel_event=cancel_event,
            )
            elapsed = time.monotonic() - start
            if self._on_status:
                self._on_status(self._task_id, "done")
            result = SubAgentResult(
                success=True,
                output=result_text or "",
                steps=self._agent._step_count,
                elapsed=elapsed,
            )
        except LLMError as e:
            elapsed = time.monotonic() - start
            if self._on_status:
                self._on_status(self._task_id, "error")
            result = SubAgentResult(
                success=False,
                output="",
                steps=0,
                elapsed=elapsed,
                error=str(e),
            )
        except Exception as e:
            elapsed = time.monotonic() - start
            if self._on_status:
                self._on_status(self._task_id, "error")
            result = SubAgentResult(
                success=False,
                output="",
                steps=0,
                elapsed=elapsed,
                error=f"{type(e).__name__}: {e}",
            )

        if self._on_event:
            self._on_event("done", self._task_index, success=result.success, steps=result.steps, elapsed=result.elapsed, error=result.error or "")
        return result


def run_parallel(
    specs: list[SubAgentSpec],
    parent_agent,
    cancel_event: threading.Event | None = None,
    on_status: Callable[[str, str], None] | None = None,
    on_event: Callable | None = None,
    max_workers: int = 3,
) -> list[SubAgentResult]:
    """并发执行多个子 Agent 任务"""
    results: dict[int, SubAgentResult] = {}

    def _run_one(spec: SubAgentSpec, idx: int) -> tuple[int, SubAgentResult]:
        sub = SubAgent(parent_agent, spec, on_status=on_status, on_event=on_event, task_index=idx)
        result = sub.run(cancel_event=cancel_event)
        return idx, result

    with ThreadPoolExecutor(max_workers=min(max_workers, len(specs))) as pool:
        futures = {pool.submit(_run_one, spec, i): i for i, spec in enumerate(specs)}
        for future in as_completed(futures):
            idx, result = future.result()
            results[idx] = result

    return [results[i] for i in range(len(specs))]
