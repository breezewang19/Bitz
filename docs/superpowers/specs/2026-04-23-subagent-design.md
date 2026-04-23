# Subagent 并行执行设计

## 目标

为主 Agent 添加并行任务拆分能力，支持将复杂任务拆分给多个独立 SubAgent 同时执行。

## 架构

### 组件

- `SubAgent` — 独立 agent，拥有自己的 Context、Adapter、精简版 Tools
- `SubAgentPool` — 管理多个 SubAgent 的并行执行和结果汇总
- `spawn_subagents` 工具 — 主 Agent 专用，用于拆分任务

### 文件结构

```
agent/
├── subagent.py      # SubAgent 和 SubAgentPool
├── loop.py          # 主 Agent（保留，添加 spawn_subagents 工具）
├── ...
```

## 防止递归机制（多层防护）

参考各框架调研结果，实现**三层防护**：

### 第1层：工具注册隔离（推荐做法，参考 CrewAI 的 allow_delegation）

`spawn_subagents` 工具**只在主 Agent 可用**，SubAgent 的 Tools 不包含此工具。

```
主 Agent: 有 spawn_subagents 工具
  └── SubAgent 1: 无 spawn_subagents 工具
  └── SubAgent 2: 无 spawn_subagents 工具
  └── SubAgent N: 无 spawn_subagents 工具
```

SubAgent 只能调用 `bash` 和 `read_file`，无法再拆分任务。

### 第2层：深度参数限制（参考 AutoGen 的 max_round）

SubAgent 携带 `depth` 参数，标识其"辈分"：

```python
# 主 Agent 调用 depth=0
spawn_subagents(tasks, depth=0)

# SubAgent 无法调用 spawn（工具不存在）
# 即使存在，也应拒绝 depth >= 1 的调用
```

### 第3层：超时和资源限制

每个 SubAgent 有独立超时（30秒），超过则强制终止。

## 任务拆分流程

```
用户: "帮我查天气、写代码、发邮件"
  → 主 agent 调用 spawn_subagents(["查天气", "写代码", "发邮件"], depth=0)
  → SubAgentPool 并行创建 3 个 SubAgent（depth=1）
  → 每个 SubAgent 独立运行在自己的 Context 中
  → 结果汇总返回给主 agent
  → 主 agent 将汇总结果返回给用户
```

## 实现细节

### SubAgent 类

```python
class SubAgent:
    def __init__(
        self,
        task: str,
        llm_adapter: LLMAdapter,
        tools: ToolRegistry,
        context: Context,
        depth: int = 1,
        max_steps: int = 10,
        timeout: int = 30
    )
    def run(self) -> str
```

- 每个 SubAgent 有独立 Context（任务描述 + 结果）
- 使用精简版 Tools（无 spawn_subagents）
- depth=1 标识是第一层 SubAgent
- timeout=30s 防止长时间运行
- 返回执行结果字符串

### SubAgentPool 类

```python
class SubAgentPool:
    def __init__(self, llm_adapter: LLMAdapter, base_tools: ToolRegistry, max_parallel: int = 5)
    def spawn(self, tasks: list[str], depth: int = 1) -> list[str]
```

- 使用 `threading` 并行执行
- 限制最大并行数（默认 5）
- 每个 SubAgent 携带 depth 参数
- 等待所有 SubAgent 完成或超时

### spawn_subagents 工具

主 Agent 的 Tools 中注册：

```python
def spawn_subagents_handler(tasks: list[str], depth: int = 0) -> str:
    # depth=0 为主 Agent 调用
    # SubAgentPool.spawn(tasks, depth=depth+1)
    # 返回格式化结果
```

### 消息传递

SubAgent 添加到主 Context 的消息格式：

```
role: user
content: [{
    "type": "tool_result",
    "tool_use_id": "<id>",
    "content: """[SubAgent 1]
结果1

[SubAgent 2]
结果2

[SubAgent 3]
结果3"""
}]
```

格式参考 CrewAI 的 task context chaining，清晰分隔各 SubAgent 结果。

## 限制

| 限制项 | 值 | 说明 |
|--------|-----|------|
| 最大并行数 | 5 | 防止资源耗尽 |
| SubAgent 最大步骤 | 10 | 参考 AutoGen max_round |
| SubAgent 超时 | 30s | 防止长时间运行 |
| SubAgent depth | 1 | 只允许一层 SubAgent |

## 调研参考

详见 `learning/2026-04-23-subagent-frameworks-research.md`
