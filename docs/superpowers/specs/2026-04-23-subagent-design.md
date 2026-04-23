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

## 防递归机制

`spawn_subagents` 工具**只在主 Agent 可用**，SubAgent 的 Tools 不包含此工具。

```
主 Agent: 有 spawn_subagents 工具
  └── SubAgent 1: 无 spawn_subagents 工具
  └── SubAgent 2: 无 spawn_subagents 工具
  └── SubAgent N: 无 spawn_subagents 工具
```

SubAgent 只能调用 `bash` 和 `read_file`，无法再拆分任务。

## 任务拆分流程

```
用户: "帮我查天气、写代码、发邮件"
  → 主 agent 调用 spawn_subagents(["查天气", "写代码", "发邮件"])
  → SubAgentPool 并行创建 3 个 SubAgent
  → 每个 SubAgent 独立运行在自己的 Context 中
  → 结果汇总返回给主 agent
  → 主 agent 将汇总结果返回给用户
```

## 实现细节

### SubAgent 类

```python
class SubAgent:
    def __init__(self, task: str, llm_adapter: LLMAdapter, tools: ToolRegistry, context: Context, max_steps: int = 10)
    def run(self) -> str
```

- 每个 SubAgent 有独立 Context（任务描述 + 结果）
- 使用精简版 Tools（无 spawn_subagents）
- 返回执行结果字符串

### SubAgentPool 类

```python
class SubAgentPool:
    def __init__(self, llm_adapter: LLMAdapter, base_tools: ToolRegistry, max_parallel: int = 5)
    def spawn(self, tasks: list[str]) -> list[str]  # 并行执行，返回结果列表
```

- 使用 `threading` 并行执行
- 限制最大并行数（默认 5）
- 等待所有 SubAgent 完成

### spawn_subagents 工具

主 Agent 的 Tools 中注册：

```python
def spawn_subagents_handler(tasks: list[str]) -> str:
    # 调用 SubAgentPool 并行执行
    # 返回格式化结果
```

### 消息传递（防递归关键）

SubAgent 添加到主 Context 的消息格式：

```
role: user
content: [{
    "type": "tool_result",
    "tool_use_id": "<id>",
    "content": "SubAgent 1: 结果1\nSubAgent 2: 结果2\nSubAgent 3: 结果3"
}]
```

## 限制

- SubAgent 不可使用 `spawn_subagents`（由工具注册机制保证）
- 最大并行数限制为 5（防止资源耗尽）
- 每个 SubAgent 最大步骤限制为 10
