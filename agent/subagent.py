# agent/subagent.py
"""SubAgent — 子 Agent 执行器，支持并发和上下文隔离"""
from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable


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
