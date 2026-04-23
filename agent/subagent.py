"""Subagent 并行执行模块"""
import threading
from typing import Callable
from dataclasses import dataclass

from agent.context import Context


class SubAgentTimeout(Exception):
    """超时异常"""
    pass


class SubAgent:
    """
    独立 SubAgent，拥有自己的 Context 和精简版 Tools

    防递归机制：
    1. Tools 中无 spawn_subagents（由注册机制保证）
    2. depth=1 标识辈分
    3. 超时保护（跨平台）
    """

    def __init__(
        self,
        task: str,
        llm_adapter,
        tools,  # 精简版 tools（无 spawn_subagents）
        depth: int = 1,
        max_steps: int = 10,
        timeout: int = 30
    ):
        self.task = task
        self.llm_adapter = llm_adapter
        self.tools = tools
        self.depth = depth
        self.max_steps = max_steps
        self.timeout = timeout

        # 每个 SubAgent 有独立的 Context（隔离设计）
        self.context = Context(
            system_prompt=f"你是一个专业助手，负责完成任务：{task}",
            max_tokens=4096,
            keep_last_n=20
        )

    def run(self) -> str:
        """执行 SubAgent 任务"""
        self.context.add_user(self.task)
        return self._run_loop()

    def _run_loop(self) -> str:
        """Agent 循环（参考 agent/loop.py）

        注意：SubAgent 的工具调用只在必要时使用，避免内部 tool_use IDs
        泄漏到主上下文导致 API 错误。
        """
        for step in range(self.max_steps):
            messages = self.context.get_messages()
            tools = self.tools.list_for_llm() if hasattr(self.tools, 'list_for_llm') else []

            response = self.llm_adapter.chat(messages, tools)

            if response.stop_reason == "end_turn":
                return response.content

            if response.stop_reason == "tool_use":
                # 检查是否包含 tool_use
                if not isinstance(response.content, list):
                    continue

                # 执行工具
                tool_results = []
                for tool_use in response.content:
                    if not isinstance(tool_use, dict):
                        continue
                    tool_name = tool_use.get("name", "")
                    tool_args = tool_use.get("input", {})
                    tool_id = tool_use.get("id", "")

                    # 直接执行工具，不添加到 SubAgent 上下文
                    # 这样可以避免内部 tool_use IDs 泄漏
                    result = self.tools.execute(tool_name, tool_args)
                    tool_results.append({
                        "tool_use_id": tool_id,
                        "content": str(result)
                    })

                # 只将最终文本结果添加到上下文
                # 不保留内部的 tool_use/tool_result 链
                if tool_results:
                    # 将工具结果作为用户消息添加（带格式化的输出）
                    outputs = "\n".join([r["content"] for r in tool_results])
                    self.context.add_user(f"[工具执行结果]\n{outputs}")
                continue

        return f"[超时/超限] 任务未能完成"

    def run_with_timeout(self) -> str:
        """带超时的执行（跨平台）"""
        result = None
        exception = [None]
        done_event = threading.Event()

        def worker():
            nonlocal result, exception
            try:
                result = self.run()
            except Exception as e:
                exception[0] = e
            finally:
                done_event.set()

        thread = threading.Thread(target=worker)
        thread.start()

        # 等待完成或超时
        if not done_event.wait(timeout=self.timeout):
            # 超时：等待线程结束（最多1秒）
            thread.join(timeout=1)
            if thread.is_alive():
                return f"[超时] 任务执行超过 {self.timeout} 秒"
            if exception[0]:
                return f"[错误] {str(exception[0])}"

        if exception[0]:
            return f"[错误] {str(exception[0])}"
        return result


class SubAgentPool:
    """
    SubAgent 池，管理多个 SubAgent 的并行执行

    设计：
    - 使用 threading 并行执行
    - 限制最大并行数（默认 5）
    - 等待所有 SubAgent 完成或超时
    """

    def __init__(
        self,
        llm_adapter,
        base_tools,  # 精简版 tools
        max_parallel: int = 5,
        timeout: int = 30
    ):
        self.llm_adapter = llm_adapter
        self.base_tools = base_tools
        self.max_parallel = max_parallel
        self.timeout = timeout

    def spawn(self, tasks: list[str], depth: int = 1) -> list[str]:
        """
        并行执行多个任务

        Args:
            tasks: 任务列表
            depth: 深度标识（主 Agent 是 0，SubAgent 是 1）

        Returns:
            结果列表，按 tasks 顺序返回
        """
        if not tasks:
            return []

        # 限制并行数
        tasks = tasks[:self.max_parallel]

        results = [None] * len(tasks)
        threads = []

        # 使用独立工具副本确保隔离
        from agent.tools import ToolRegistry

        def worker(task: str, index: int):
            # 每个 SubAgent 使用独立工具副本，确保没有状态泄漏
            tools = ToolRegistry()
            for name, tool in self.base_tools.tools.items():
                tools.register(
                    name=tool.name,
                    description=tool.description,
                    input_schema=tool.input_schema,
                    handler=tool.handler
                )

            subagent = SubAgent(
                task=task,
                llm_adapter=self.llm_adapter,
                tools=tools,
                depth=depth + 1,  # SubAgent depth = 2（如果有的话）
                timeout=self.timeout  # 使用 pool 的超时设置
            )
            try:
                results[index] = subagent.run_with_timeout()
            except SubAgentTimeout:
                results[index] = f"[超时] 任务执行超过 {self.timeout} 秒"
            except Exception as e:
                results[index] = f"[错误] {str(e)}"

        # 启动所有线程
        for i, task in enumerate(tasks):
            t = threading.Thread(target=worker, args=(task, i))
            t.start()
            threads.append(t)

        # 等待所有完成
        for t in threads:
            t.join()

        return results

    def format_results(self, tasks: list[str], results: list[str]) -> str:
        """
        格式化结果输出

        格式参考 CrewAI 的 task context chaining：
        [SubAgent 1]
        结果1

        [SubAgent 2]
        结果2
        """
        lines = []
        for i, (task, result) in enumerate(zip(tasks, results), 1):
            lines.append(f"[Task {i}] {task}")
            lines.append(result)
            lines.append("")  # 空行分隔
        return "\n".join(lines)