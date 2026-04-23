# Agent 框架 Subagent/并行 Agent 实现调研

## 概述

研究主流 Agent 框架如何实现 subagent、并行执行、上下文管理和递归防护。

---

## 1. LangGraph

### 架构
- **图状框架**，节点是 Python 函数，边负责路由
- 状态通过中央 `State` 对象管理（dict 或 Pydantic 模型）
- 支持**循环**（不同于 typical DAG workflows）

### 并行执行
- 使用 `Send` API 实现扇出并行
- `add_conditional_edges` 动态路由到多个节点
- **Reducer 函数** 合并并行分支输出

```python
from typing import Annotated
from langgraph.graph import StateGraph

class State(TypedDict):
    joke: str
    poem: str
    combined_output: str

# 并行节点通过 Send API 调用
def call_llm_1(state: State):
    return {"joke": llm.invoke(f"Joke about {state['topic']}")}
```

### 上下文隔离 vs 共享
- **共享状态**，所有节点通过单一 State 对象
- 节点接收完整 state，返回部分更新
- Reducer 合并并行分支的更新

### 递归防护
- **无内置机制** — 开发者需自行实现：
  - State 中的最大迭代计数器
  - 基于计数器的条件边路由到 END
  - 外部编排层

### 局限性
- 复杂图学习曲线陡峭
- 大图调试困难
- 执行流需手动管理

---

## 2. AutoGen (Microsoft)

### 架构
- 基于 agent 的对话系统
- **GroupChatManager** 编排多 agent 对话
- 通过 **Team** 概念支持嵌套 agent 层级

### 并行/Subagent 实现
- **Selector GroupChat**：从 agent 池选择下一个发言者
- **嵌套 Teams**：Teams 可包含 sub-teams
- Agent 组对话直到满足终止条件

```python
# GroupChat 模式
from autogen.agentchat import GroupChat, GroupChatManager

group_chat = GroupChat(agents=[agent1, agent2, agent3])
manager = GroupChatManager(groupchat=group_chat)
```

### 上下文管理
- **隐式会话状态**，通过对话历史
- 消息通过共享 group chat 传递
- 可通过函数参数传递显式上下文

### 递归防护
- **终止条件**（消息数量、时间限制）
- GroupChat 的 `max_round` 参数
- 发言者选择可约束防止循环

### 局限性
- 简单工作流配置复杂
- 需仔细管理对话流
- 对内部 agent 推理可见性有限

---

## 3. CrewAI

### 架构
- **Crew/Agent/Task/Tool** 层级结构
- **Process** 模式：Sequential、Hierarchical、Parallel

### 并行/Subagent 实现
- **Sequential Process**：任务按顺序执行，输出喂给下一个
- **Hierarchical Process**：Manager agent 委派任务给 worker agents
- `allow_delegation=True` 标志控制 agent 能否移交工作

```python
# Hierarchical process
researcher = Agent(role="Researcher", allow_delegation=True)
writer = Agent(role="Writer")

crew = Crew(agents=[researcher, writer], process=Process.hierarchical)
```

### 上下文管理
- Task **context** 参数传递前一个任务输出
- `context=[task1, task2]` 在任务间链式传递输出
- Agent **memory** 特性存储对话历史
- Verbose 模式暴露 agent 推理过程

### 递归防护
- **无显式递归防护**
- 通过 `allow_delegation` 标志控制委派
- Process 结构（sequential/hierarchical）限制任意嵌套

### 局限性
- 并行执行选项有限
- 上下文窗口管理困难
- 委派可能产生隐式循环且无可见性

---

## 4. OpenAI Swarm

### 架构
- **轻量级教育框架**（非生产级）
- 两个原语：**Agents** 和 **Handoffs**
- 无状态编排 — 无内置状态管理

### Subagent 实现
- Agent 是自包含的，有指令和工具
- **Handoffs** 在 agents 间转移控制权
- Agent 函数可返回 handoff 指令

```python
from swarm import Swarm, Agent

def transfer_to_b():
    return agent_b

agent_a = Agent(name="Agent A", instructions="...", functions=[transfer_to_b])
```

### 上下文管理
- **无隐式上下文共享** — 开发者显式管理
- 消息直接传给 `client.run()`
- 每个 agent 接收自己的指令集

### 递归防护
- **完全由开发者负责**
- 无内置 handoff 链限制
- 需实现外部安全措施

### 局限性
- 实验性，不适合生产
- 无持久化、内存或复杂状态
- 工具生态有限

---

## 5. LlamaIndex

### Subagent 概念
- **AgentRunner** 架构，带层级 agents
- 通过 `SubAgent` 类支持 **Sub-Agent** 功能
- 支持嵌套 agent 执行处理专业任务

### 关键模式
- 内置工具使用和任务分解
- 通过 agent 层级传递上下文
- 多步骤任务的查询规划

---

## 共同模式与创新

### 架构模式
1. **图/状态机**：LangGraph — 灵活的循环和条件
2. **团队层级**：AutoGen — 嵌套 agent 组与管理
3. **Crew/角色分配**：CrewAI — 基于角色的显式委派
4. **Handoff/转移**：Swarm — 显式控制转移原语

### 上下文管理方式
| 框架 | 方式 |
|--------|------|
| LangGraph | 中央状态 + reducer 合并 |
| AutoGen | 隐式对话历史 |
| CrewAI | Task context 链式传递 + agent memory |
| Swarm | 开发者管理的无状态 |

### 递归防护机制
| 框架 | 机制 |
|--------|------------|
| LangGraph | 基于计数器的条件边（手动） |
| AutoGen | max_round，终止条件 |
| CrewAI | allow_delegation 标志，process 约束 |
| Swarm | 无（开发者负责） |

---

## 关键发现

1. **无通用递归防护方案** — 各框架处理方式不同（或根本没有）

2. **上下文隔离差异大**：从完全共享（LangGraph）到完全隔离（Swarm）

3. **并行执行模式**：Send API（LangGraph）、GroupChat（AutoGen）、Process 模式（CrewAI）

4. **Subagent 深度限制**：大多数框架依赖开发者纪律；只有 AutoGen 有结构化终止

5. **内存管理**：随着 agent 对话增长越发重要 — 框架在增加 memory/上下文摘要功能

---

## 建议

- **复杂工作流**：LangGraph（灵活）或 AutoGen（结构化）
- **团队任务**：CrewAI（基于角色，清晰的委派）
- **教育/原型**：Swarm（最小开销）
- **无论选什么框架都要实现**：最大迭代限制、深度计数器、超时机制
