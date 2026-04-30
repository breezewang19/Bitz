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
    ) -> None:
        self._spec = spec
        self._on_status = on_status
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
