# Subagent 并行执行实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为主 Agent 添加并行任务拆分能力，支持将复杂任务拆分给多个独立 SubAgent 同时执行，同时通过三层防护机制防止递归。

**Architecture:** 新增 `agent/subagent.py`，包含 `SubAgent` 和 `SubAgentPool` 类。主 Agent 通过 `spawn_subagents` 工具拆分任务，SubAgentPool 使用 `threading` 并行执行。SubAgent 拥有独立 Context 和精简版 Tools（无 `spawn_subagents`）。

**Tech Stack:** Python threading (跨平台超时机制)

---

## 文件结构

```
agent/
├── __init__.py
├── adapter.py      # 不改
├── context.py      # 不改
├── loop.py         # 修改: 添加 spawn_subagents 工具注册
├── tools.py        # 不改
└── subagent.py     # 新增: SubAgent + SubAgentPool

tests/
├── __init__.py
├── test_adapter.py      # 不改
├── test_context.py      # 不改
├── test_loop.py         # 可选: 测试 spawn 工具
└── test_subagent.py     # 新增: SubAgent 测试
```

---

## 实现步骤

### Task 1: 创建 agent/subagent.py（SubAgent + SubAgentPool）

**Files:**
- Create: `agent/subagent.py`

> **注意**：Spec 与 Plan 的差异说明
> - Spec 中 `context` 作为构造参数传入
> - Plan 中 SubAgent **自己创建独立 Context**（这是正确的设计决策，因为 SubAgent 必须隔离）
> - Spec 中 `timeout` 参数计划在 Task 3 的 `create_spawn_tools` 中统一传递
> - 跨平台兼容性：使用 `threading.Event.wait(timeout)` 替代 `signal.SIGALRM`（后者仅 Unix）

- [ ] **Step 1: 写 SubAgent 类的基础结构**

```python
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
        """Agent 循环（参考 agent/loop.py）"""
        for step in range(self.max_steps):
            messages = self.context.get_messages()
            tools = self.tools.list_for_llm() if hasattr(self.tools, 'list_for_llm') else []

            response = self.llm_adapter.chat(messages, tools)

            if response.stop_reason == "end_turn":
                return response.content

            if response.stop_reason == "tool_use":
                self.context.add_assistant_message(response.content)

                for tool_use in response.content:
                    tool_name = tool_use["name"]
                    tool_args = tool_use["input"]
                    tool_id = tool_use["id"]

                    result = self.tools.execute(tool_name, tool_args)
                    self.context.add_tool_result(tool_id, result)
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
```

- [ ] **Step 2: 写 SubAgentPool 类**

```python
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

        def worker(task: str, index: int):
            subagent = SubAgent(
                task=task,
                llm_adapter=self.llm_adapter,
                tools=self.base_tools,
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
```

- [ ] **Step 3: 提交**

```bash
git add agent/subagent.py
git commit -m "feat: add SubAgent and SubAgentPool for parallel execution"
```

---

### Task 2: 创建 tests/test_subagent.py

**Files:**
- Create: `tests/test_subagent.py`

- [ ] **Step 1: 写 SubAgent 基本测试**

```python
"""SubAgent 并行执行测试"""
import pytest
from unittest.mock import Mock, MagicMock
from agent.subagent import SubAgent, SubAgentPool, SubAgentTimeout
from agent.context import Context
from agent.tools import ToolRegistry


class TestSubAgent:
    """SubAgent 单元测试"""

    def test_subagent_has_independent_context(self):
        """SubAgent 应该有独立的 Context"""
        mock_adapter = Mock()
        mock_adapter.chat.return_value = Mock(
            content="test result",
            stop_reason="end_turn"
        )

        tools = ToolRegistry()

        subagent = SubAgent(
            task="测试任务",
            llm_adapter=mock_adapter,
            tools=tools,
            depth=1
        )

        assert isinstance(subagent.context, Context)
        assert "测试任务" in subagent.context.system_prompt

    def test_subagent_depth_is_one_by_default(self):
        """默认 depth=1"""
        mock_adapter = Mock()
        mock_adapter.chat.return_value = Mock(content="", stop_reason="end_turn")

        tools = ToolRegistry()

        subagent = SubAgent(
            task="测试",
            llm_adapter=mock_adapter,
            tools=tools
        )

        assert subagent.depth == 1

    def test_subagent_run_calls_llm(self):
        """run() 应该调用 LLM"""
        mock_adapter = Mock()
        mock_adapter.chat.return_value = Mock(
            content="完成",
            stop_reason="end_turn"
        )

        tools = ToolRegistry()
        subagent = SubAgent(
            task="测试",
            llm_adapter=mock_adapter,
            tools=tools
        )

        result = subagent.run()

        assert result == "完成"
        mock_adapter.chat.assert_called_once()

    def test_subagent_respects_max_steps(self):
        """应该尊重 max_steps 限制"""
        mock_adapter = Mock()
        # 模拟持续返回 tool_use（直到超限）
        mock_adapter.chat.return_value = Mock(
            content=[{"type": "tool_use", "id": "1", "name": "bash", "input": {"command": "ls"}}],
            stop_reason="tool_use"
        )

        tools = ToolRegistry()
        # 注册一个返回空结果的 bash 工具
        tools.register(
            name="bash",
            description="执行命令",
            input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
            handler=lambda command: ""
        )

        subagent = SubAgent(
            task="测试",
            llm_adapter=mock_adapter,
            tools=tools,
            max_steps=2
        )

        result = subagent.run()

        # 2 步后超限，返回错误信息
        assert "超限" in result or "max_steps" in result.lower()
        # chat 被调用 2 次
        assert mock_adapter.chat.call_count == 2
```

- [ ] **Step 2: 写 SubAgentPool 测试**

```python
class TestSubAgentPool:
    """SubAgentPool 单元测试"""

    def test_spawn_returns_results_list(self):
        """spawn() 应该返回结果列表"""
        mock_adapter = Mock()
        mock_adapter.chat.return_value = Mock(
            content="完成",
            stop_reason="end_turn"
        )

        tools = ToolRegistry()

        pool = SubAgentPool(
            llm_adapter=mock_adapter,
            base_tools=tools,
            max_parallel=5
        )

        tasks = ["任务1", "任务2", "任务3"]
        results = pool.spawn(tasks)

        assert len(results) == 3
        assert all(r is not None for r in results)

    def test_spawn_respects_max_parallel(self):
        """spawn() 应该限制最大并行数"""
        mock_adapter = Mock()
        mock_adapter.chat.side_effect = lambda *args, **kwargs: Mock(
            content="完成",
            stop_reason="end_turn"
        )

        tools = ToolRegistry()

        pool = SubAgentPool(
            llm_adapter=mock_adapter,
            base_tools=tools,
            max_parallel=2
        )

        tasks = ["任务1", "任务2", "任务3", "任务4", "任务5"]
        results = pool.spawn(tasks)

        # 只能并行 2 个
        assert len(results) == 2

    def test_spawn_uses_timeout(self):
        """spawn() 应该使用 pool 的超时设置"""
        mock_adapter = Mock()

        tools = ToolRegistry()

        pool = SubAgentPool(
            llm_adapter=mock_adapter,
            base_tools=tools,
            max_parallel=2,
            timeout=60
        )

        assert pool.timeout == 60

    def test_format_results(self):
        """format_results() 应该正确格式化"""
        mock_adapter = Mock()
        tools = ToolRegistry()

        pool = SubAgentPool(
            llm_adapter=mock_adapter,
            base_tools=tools
        )

        tasks = ["查天气", "写代码"]
        results = ["晴天", "代码完成"]

        formatted = pool.format_results(tasks, results)

        assert "[Task 1] 查天气" in formatted
        assert "[Task 2] 写代码" in formatted
        assert "晴天" in formatted
        assert "代码完成" in formatted

    def test_spawn_empty_tasks(self):
        """spawn() 处理空列表"""
        mock_adapter = Mock()
        tools = ToolRegistry()

        pool = SubAgentPool(
            llm_adapter=mock_adapter,
            base_tools=tools
        )

        results = pool.spawn([])
        assert results == []
```

- [ ] **Step 3: 添加防递归测试**

```python
class TestSubAgentAntiRecursion:
    """防递归机制测试"""

    def test_base_tools_lacks_spawn_subagents(self):
        """验证 base_tools 中没有 spawn_subagents"""
        tools = ToolRegistry()
        tools.register(
            name="bash",
            description="执行命令",
            input_schema={"type": "object"},
            handler=lambda **kwargs: "result"
        )

        pool = SubAgentPool(
            llm_adapter=Mock(),
            base_tools=tools
        )

        # base_tools 中没有 spawn_subagents
        assert "spawn_subagents" not in pool.base_tools.tools

    def test_subagent_tools_lacks_spawn_subagents(self):
        """验证 SubAgent 的 tools 中没有 spawn_subagents"""
        tools = ToolRegistry()
        tools.register(
            name="bash",
            description="执行命令",
            input_schema={"type": "object"},
            handler=lambda **kwargs: "result"
        )

        subagent = SubAgent(
            task="测试",
            llm_adapter=Mock(),
            tools=tools,
            timeout=30
        )

        # SubAgent 的 tools 中没有 spawn_subagents
        assert "spawn_subagents" not in subagent.tools.tools

    def test_subagent_depth_is_one(self):
        """SubAgent 默认 depth=1"""
        tools = ToolRegistry()
        subagent = SubAgent(
            task="测试",
            llm_adapter=Mock(),
            tools=tools
        )

        assert subagent.depth == 1
```

- [ ] **Step 4: 运行测试验证**

```bash
pytest tests/test_subagent.py -v
```

- [ ] **Step 5: 提交**

```bash
git add tests/test_subagent.py
git commit -m "test: add SubAgent and SubAgentPool tests with anti-recursion verification"
```

---

### Task 3: 修改 agent/loop.py（添加 spawn_subagents 工具）

**Files:**
- Modify: `agent/loop.py:1-43`

- [ ] **Step 1: 添加 SubAgentPool 导入和 spawn_subagents 工具**

在 `agent/loop.py` 开头添加：

```python
from agent.subagent import SubAgentPool
```

在 `create_tools()` 函数后添加 `create_spawn_tools()` 函数：

```python
def create_spawn_tools(llm_adapter, base_tools):
    """
    创建 spawn_subagents 工具（仅主 Agent 可用）

    SubAgentPool 使用精简版 tools（无 spawn_subagents），防止递归。
    """
    pool = SubAgentPool(llm_adapter=llm_adapter, base_tools=base_tools, max_parallel=5)

    def spawn_subagents_handler(tasks: list[str], depth: int = 0) -> str:
        """
        并行执行多个子任务

        Args:
            tasks: 子任务列表
            depth: 深度标识（主 Agent 调用时为 0）

        Returns:
            格式化后的结果
        """
        # 防护：SubAgent 不应调用此工具
        if depth > 0:
            return "[错误] SubAgent 不可拆分任务"

        # 防护：超限检查
        if len(tasks) > 5:
            return f"[错误] 任务数量 {len(tasks)} 超过限制 (5)"

        results = pool.spawn(tasks, depth=depth)
        return pool.format_results(tasks, results)

    tools = ToolRegistry()

    # 注册 spawn_subagents（只有主 Agent 有这个工具）
    tools.register(
        name="spawn_subagents",
        description="并行执行多个子任务，每个子任务由独立 Agent 处理",
        input_schema={
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "子任务列表（最多5个）"
                },
                "depth": {
                    "type": "integer",
                    "description": "深度标识（内部使用）",
                    "default": 0
                }
            },
            "required": ["tasks"]
        },
        handler=spawn_subagents_handler
    )

    # 保留 base_tools 中的工具
    for name, tool in base_tools.tools.items():
        tools.register(
            name=tool.name,
            description=tool.description,
            input_schema=tool.input_schema,
            handler=tool.handler
        )

    return tools
```

- [ ] **Step 2: 修改 main() 函数使用 spawn 工具**

在 `tui.py` 的 `create_tools()` 调用处：

```python
# 原来
tools = create_tools()

# 改为（需要传入 adapter 和 base_tools）
from agent.loop import create_spawn_tools

# 先创建基础工具
base_tools = create_tools()
# 再创建包含 spawn_subagents 的完整工具集
tools = create_spawn_tools(adapter, base_tools)
```

**注意**：实际修改在 `tui.py` 中进行（见 Task 4）。

- [ ] **Step 3: 提交**

```bash
git add agent/loop.py
git commit -m "feat: add spawn_subagents tool to agent/loop.py"
```

---

### Task 4: 修改 tui.py（注册 spawn 工具）

**Files:**
- Modify: `tui.py` 的 `create_tools()` 相关部分

- [ ] **Step 1: 读取当前 tui.py 确认修改点**

```bash
grep -n "create_tools\|adapter\|tools =" tui.py
```

- [ ] **Step 2: 添加导入**

```python
from agent.loop import create_spawn_tools
```

- [ ] **Step 3: 修改 main() 中的工具创建逻辑**

在 `adapter = LLMAdapter(...)` 之后：

```python
# 创建基础工具
base_tools = create_tools()

# 创建包含 spawn_subagents 的完整工具集（主 Agent 专用）
tools = create_spawn_tools(adapter, base_tools)
```

- [ ] **Step 4: 验证**

```bash
python -c "from tui import *; print('OK')"
```

- [ ] **Step 5: 提交**

```bash
git add tui.py
git commit -m "feat: register spawn_subagents tool in tui.py"
```

---

### Task 5: 集成测试

**Files:**
- Create: `tests/test_integration_subagent.py`

- [ ] **Step 1: 写集成测试**

```python
"""Subagent 集成测试"""
import pytest
from unittest.mock import Mock
from agent.subagent import SubAgent, SubAgentPool
from agent.tools import ToolRegistry


def test_subagent_cannot_spawn():
    """验证 SubAgent 的 tools 中没有 spawn_subagents"""
    mock_adapter = Mock()
    mock_adapter.chat.return_value = Mock(content="完成", stop_reason="end_turn")

    base_tools = ToolRegistry()
    base_tools.register(
        name="bash",
        description="执行命令",
        input_schema={"type": "object"},
        handler=lambda **kwargs: "result"
    )

    # SubAgentPool 只传递 base_tools
    pool = SubAgentPool(mock_adapter, base_tools)

    # 检查 base_tools 中没有 spawn_subagents
    assert "spawn_subagents" not in pool.base_tools.tools

    # 创建 SubAgent
    subagent = SubAgent(
        task="测试",
        llm_adapter=mock_adapter,
        tools=pool.base_tools
    )

    # SubAgent 的 tools 中也没有 spawn_subagents
    assert "spawn_subagents" not in subagent.tools.tools
```

- [ ] **Step 2: 运行测试**

```bash
pytest tests/test_integration_subagent.py -v
```

- [ ] **Step 3: 提交**

```bash
git add tests/test_integration_subagent.py
git commit -m "test: add subagent integration test"
```

---

## 验证清单

实现完成后，确保以下防护机制有效：

- [ ] **Tool 隔离**：SubAgent 的 tools 中无 `spawn_subagents`
- [ ] **Depth 参数**：SubAgent depth=1，主 Agent depth=0
- [ ] **超时机制**：SubAgent 30 秒超时（跨平台 threading.Event）
- [ ] **并行限制**：最多 5 个并行 SubAgent
- [ ] **测试通过**：`pytest tests/test_subagent.py -v`
- [ ] **防递归测试通过**：`pytest tests/test_subagent.py::TestSubAgentAntiRecursion -v`

---

## 依赖关系

```
Task 1 (agent/subagent.py)
    ↓
Task 2 (tests/test_subagent.py)
    ↓
Task 3 (agent/loop.py - 添加 spawn 工具)
    ↓
Task 4 (tui.py - 注册工具)
    ↓
Task 5 (tests/test_integration_subagent.py)
```

---

## 参考文档

- 设计规范: `docs/superpowers/specs/2026-04-23-subagent-design.md`
- 调研报告: `learning/2026-04-23-subagent-frameworks-research.md`
