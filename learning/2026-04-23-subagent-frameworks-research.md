# Subagent 并行执行框架调研

## 前言

当单个 Agent 遇到复杂任务时（如"帮我查三个股票的实时行情，然后分析并生成报告"），我们自然想到：**能不能让多个 Agent 同时工作**？

这就是 Subagent（子 Agent）并行执行的核心需求。本文档调研主流框架的实现方式，重点关注：
1. **架构模式** — 如何拆分和汇总任务
2. **上下文管理** — 共享还是隔离
3. **递归防护** — 如何防止无限嵌套

**前置知识**：理解 Agent 循环、Tool Calling 协议、会话上下文管理。

---

## 一、为什么需要 Subagent

普通 Agent 循环是**串行**的：

```
用户: "帮我查三只股票行情并分析"
  → Agent: 调用工具查股票A
  → 返回结果A
  → Agent: 调用工具查股票B
  → 返回结果B
  → Agent: 调用工具查股票C
  → 返回结果C
  → Agent: 分析并生成报告
```

三个查股票的任务是**独立的**，却要串行执行，浪费时间。

理想情况：

```
用户: "帮我查三只股票行情并分析"
  → Agent: [拆分任务] 并行查A、B、C
                ↓     ↓     ↓
            结果A  结果B  结果C
                ↓     ↓     ↓
  → Agent: [汇总结果] 生成报告
```

Subagent 并行执行就是解决这个问题的机制。

---

## 二、LangGraph

### 2.1 核心概念

LangGraph 是一个**图状框架**，核心原语：

| 原语 | 作用 |
|------|------|
| **State** | 中央状态对象，所有节点共享 |
| **Node** | Python 函数，代表一个操作 |
| **Edge** | 连接节点的边，决定执行流向 |
| **Send** | 并行调用多个节点的 API |

### 2.2 并行执行模式

LangGraph 用 `Send` API 实现**扇出并行**：

```python
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END

class MultiState(TypedDict):
    joke: str
    poem: str
    combined: str

def gen_joke(state: MultiState) -> dict:
    """生成笑话节点"""
    return {"joke": llm.invoke(f"Write a joke about {state['topic']}")}

def gen_poem(state: MultiState) -> dict:
    """写诗节点"""
    return {"poem": llm.invoke(f"Write a poem about {state['topic']}")}

def combine(state: MultiState) -> dict:
    """汇总节点"""
    return {"combined": f"{state['joke']}\n\n{state['poem']}"}

# 定义图
graph = StateGraph(MultiState)
graph.add_node("joke", gen_joke)
graph.add_node("poem", gen_poem)
graph.add_node("combine", combine)

# 并行分支：用 Send 同时调用 joke 和 poem
def route_parallel(state: MultiState):
    return [Send("joke", state), Send("poem", state)]

graph.add_conditional_edges(START, route_parallel)
graph.add_edge("joke", "combine")
graph.add_edge("poem", "combine")
graph.add_edge("combine", END)

app = graph.compile()
```

### 2.3 上下文管理

**完全共享状态**：

```
┌─────────────────────────────────────┐
│            MultiState                │
│  joke: str  │  poem: str  │ combined  │
├─────────────────────────────────────┤
│  所有节点读写同一个 State 对象         │
│  节点返回部分更新，Reducer 合并结果    │
└─────────────────────────────────────┘
```

Reducer 机制：当多个节点同时更新同一字段时，按顺序合并。

### 2.4 递归防护

**无内置机制**，完全靠开发者实现：

```python
class RecursiveState(TypedDict):
    count: int
    result: str
    # 开发者自己加计数器

def should_continue(state: RecursiveState):
    if state["count"] >= 5:  # 手动限制深度
        return END
    return "agent_node"

graph.add_conditional_edges("agent_node", should_continue)
```

**问题**：如果不主动加计数器，可能无限递归。

### 2.5 局限性

- **图结构复杂**：简单任务也需定义 State、Node、Edge
- **调试困难**：图执行不直观
- **灵活性代价**：过度设计风险

---

## 三、AutoGen (Microsoft)

### 3.1 核心概念

AutoGen 是**对话式多 Agent 框架**：

| 组件 | 作用 |
|------|------|
| **Agent** | 能说话（发消息）的实体 |
| **GroupChat** | Agent 群聊容器 |
| **GroupChatManager** | 主持人，决定谁下一句发言 |

### 3.2 并行执行模式

AutoGen 用 **GroupChat** 实现 Agent 间的对话协作：

```python
from autogen.agentchat import GroupChat, GroupChatManager

# 创建三个专家 Agent
researcher = AssistantAgent(name="researcher", system_message="你是研究员...")
coder = AssistantAgent(name="coder", system_message="你是程序员...")
reviewer = AssistantAgent(name="reviewer", system_message="你是评审...")

# 创建群聊
group_chat = GroupChat(
    agents=[researcher, coder, reviewer],
    max_round=10  # 限制轮次，防止无限对话
)

# 创建管理器
manager = GroupChatManager(groupchat=group_chat)

# 启动群聊
researcher.initiate_chat(
    manager,
    message="研究一下 RAG 技术并实现一个 demo"
)
```

### 3.3 嵌套 Teams（Subagent 层级）

AutoGen 支持**层级嵌套**：

```python
from autogen.agentchat import Team

# 创建子团队
backend_team = Team(
    agents=[backend_dev, tester],
    interleaved_termination=True
)

# 主团队包含子团队
main_team = Team(
    agents=[architect, backend_team],  # 子团队作为整体
    termination=some_condition
)
```

### 3.4 上下文管理

**隐式共享**：通过群聊消息历史共享上下文。

```
researcher: "我研究了 RAG..."
  ↓ (消息进入 group chat)
coder: "我看到你的研究，开始写代码..."
  ↓ (消息进入 group chat)
reviewer: "代码评审意见..."
  ↓ (消息进入 group chat)
```

每个 Agent 都能看到完整的对话历史。

### 3.5 递归防护

**有结构化终止机制**：

```python
# 方式 1: max_round 限制
group_chat = GroupChat(agents=[...], max_round=10)

# 方式 2: 显式终止条件
def termination_check(msg):
    return "任务完成" in msg.get("content", "")

group_chat = GroupChat(
    agents=[...],
    max_round=10,
    speaker_selection=termination_check  # 自定义选择逻辑
)
```

### 3.6 局限性

- **配置复杂**：简单任务也需设置 GroupChat、Manager
- **调试困难**：多 Agent 对话不透明
- **资源消耗**：多 Agent 长期运行成本高

---

## 四、CrewAI

### 4.1 核心概念

CrewAI 是**角色驱动**的框架：

| 组件 | 作用 |
|------|------|
| **Agent** | 有角色、目标、工具的实体 |
| **Task** | 具体任务，有描述和预期输出 |
| **Crew** | Agent 集合 + 执行流程 |
| **Process** | 执行模式（Sequential/Hierarchical） |

### 4.2 并行执行模式

```python
from crewai import Agent, Task, Crew, Process

# 定义 Agent
researcher = Agent(
    role="股票研究员",
    goal="获取最新股票行情",
    backstory="你是一名专业股票研究员..."
)

analyst = Agent(
    role="股票分析师",
    goal="分析行情数据",
    backstory="你是一名专业股票分析师..."
)

# 定义任务
task1 = Task(description="查询股票A、B、C的实时行情", agent=researcher)
task2 = Task(description="基于行情数据分析投资机会", agent=analyst, context=[task1])  # 依赖 task1

# 创建 Crew
crew = Crew(
    agents=[researcher, analyst],
    tasks=[task1, task2],
    process=Process.sequential  # 或 Process.hierarchical
)

# 启动
result = crew.kickoff()
```

### 4.3 Hierarchical Process（层级委派）

```python
# Manager agent 委派任务给 workers
crew = Crew(
    agents=[manager_agent, worker1, worker2, worker3],
    process=Process.hierarchical,  # manager 自动委派
    manager_agent=manager_agent
)
```

Manager Agent 负责：
1. 分析任务需求
2. 拆分并委派给合适的 worker
3. 汇总 worker 结果

### 4.4 上下文管理

**Task Context 链式传递**：

```
task1 执行 → 输出结果
       ↓
task2 的 context=[task1] → 能看到 task1 的输出
       ↓
task3 的 context=[task2] → 能看到 task2 的输出（包含 task1 的影响）
```

```python
# Task 之间的上下文传递
task2 = Task(
    description="分析股票",
    agent=analyst,
    context=[task1]  # task2 能看到 task1 的结果
)
```

### 4.5 递归防护

**通过 `allow_delegation` 标志**：

```python
# 默认不允许委派
researcher = Agent(role="研究员", allow_delegation=False)

# 只有 Manager 能委派，worker 不能
# Hierarchical process 下自动控制
```

**Process 约束**：Sequential/Hierarchical 模式本身就限制了无限嵌套。

### 4.6 局限性

- **并行有限**：Sequential 模式下任务顺序固定
- **Context 膨胀**：长链条的 task context 可能很大
- **委派可见性差**： delegation 可能产生隐式循环

---

## 五、OpenAI Swarm

### 5.1 核心概念

Swarm 是**教育性轻量框架**，两个原语：

| 原语 | 作用 |
|------|------|
| **Agent** | 指令集 + 工具集 + 函数列表 |
| **Handoff** | 在 Agent 之间转移控制权 |

### 5.2 并行执行模式

Swarm 没有真正的并行机制，只有 **Handoff**（转移）：

```python
from swarm import Swarm, Agent

# 定义 Agent
sales_agent = Agent(
    name="销售",
    instructions="你是销售助手...",
    functions=[transfer_to_tech]
)

tech_agent = Agent(
    name="技术支持",
    instructions="你是技术支持...",
    functions=[transfer_to_sales]
)

# Handoff 函数
def transfer_to_tech():
    """转移到技术支持"""
    return tech_agent

def transfer_to_sales():
    """转移到销售"""
    return sales_agent

# 运行
client = Swarm()
response = client.run(
    agent=sales_agent,
    messages=[{"role": "user", "content": "我想买企业版"}]
)
```

### 5.3 上下文管理

**完全隔离**：每个 Agent 独立运行，Handoff 时传递消息列表。

```python
# Handoff 时
def transfer_to_tech():
    return tech_agent  # 控制权转移，但上下文需手动管理
```

### 5.4 递归防护

**无任何内置机制**：

```python
# 开发者自己实现防护
def safe_handoff(agent, max_depth=3):
    if current_depth >= max_depth:
        return final_response
    return agent
```

### 5.5 局限性

- **实验性**：非生产级
- **无并行**：只有串行 Handoff
- **无状态管理**：开发者全权负责

---

## 六、LlamaIndex

### 6.1 AgentRunner 架构

LlamaIndex 的 Agent 是**层级结构**：

```
AgentRunner
  └── RootAgent
        └── SubAgent (可嵌套)
```

### 6.2 并行执行

```python
from llama_index.core.agent import AgentRunner, SubAgent

# 创建 SubAgent
sub_agent = SubAgent(
    name="researcher",
    llm=llm,
    tools=tools
)

# RootAgent 调度 SubAgent
root = AgentRunner(llm=llm, tools=[])
root.add_sub_agent(sub_agent)
```

### 6.3 上下文管理

通过 **ToolCall 传递**：SubAgent 的结果通过 ToolCall 返回给 RootAgent。

---

## 七、对比总结

### 7.1 架构模式

| 框架 | 并行模式 | 子 Agent 层级 | 适用场景 |
|------|----------|---------------|----------|
| **LangGraph** | Send API 扇出 | 扁平（节点） | 复杂图结构工作流 |
| **AutoGen** | GroupChat 对话 | 嵌套 Teams | 多 Agent 协作讨论 |
| **CrewAI** | Process 模式 | Hierarchical | 角色驱动任务分解 |
| **Swarm** | Handoff 转移 | 无层级 | 教育/简单原型 |
| **LlamaIndex** | ToolCall | 可嵌套 | 文档理解/问答 |

### 7.2 上下文管理方式

| 框架 | 隔离级别 | 共享方式 | 传递机制 |
|------|----------|----------|----------|
| **LangGraph** | 低（共享 State） | Reducer 合并 | 中央 State |
| **AutoGen** | 中（群聊历史） | 消息广播 | GroupChat |
| **CrewAI** | 中（Task Context） | 链式传递 | context 参数 |
| **Swarm** | 高（完全隔离） | 手动传递 | Handoff |
| **LlamaIndex** | 中 | ToolCall | 函数返回 |

### 7.3 递归防护机制

| 框架 | 防护机制 | 实现难度 |
|------|----------|----------|
| **LangGraph** | 计数器 + 条件边（手动） | 高（需开发者实现） |
| **AutoGen** | max_round + 终止条件 | 低（内置） |
| **CrewAI** | allow_delegation + Process 约束 | 中（部分内置） |
| **Swarm** | 无 | 需自己实现 |
| **LlamaIndex** | 嵌套深度限制 | 中 |

### 7.4 关键发现

1. **无通用递归防护**：大多数框架依赖开发者纪律，只有 AutoGen 有结构化终止

2. **上下文隔离是光谱**：
   - LangGraph：完全共享（最低隔离）
   - Swarm：完全隔离（最高隔离）
   - 其他：居中（按需共享）

3. **并行粒度不同**：
   - LangGraph：节点级并行
   - AutoGen：Agent 级对话并行
   - CrewAI：Task 级并行

4. **复杂度 vs 灵活性的权衡**：
   - Swarm 最简单，但功能最弱
   - LangGraph 最灵活，但配置最复杂

---

## 八、我们的设计决策

基于调研，我们选择**工具注册隔离 + 深度参数 + 超时限制**三层防护：

### 8.1 第一层：工具注册隔离

参考 CrewAI 的 `allow_delegation` 理念：

```python
# 主 Agent 的工具
main_tools = ToolRegistry()
main_tools.register(name="spawn_subagents", handler=spawn_handler, ...)

# SubAgent 的工具（无 spawn_subagents）
sub_tools = ToolRegistry()
sub_tools.register(name="bash", handler=bash_handler, ...)
sub_tools.register(name="read_file", handler=read_handler, ...)
# spawn_subagents 根本不存在！
```

**原理**：SubAgent 的工具列表里根本没有 `spawn_subagents`，无法递归调用。

### 8.2 第二层：深度参数限制

```python
class SubAgent:
    def __init__(self, depth: int = 1, ...):
        self.depth = depth  # 标识辈分

# 主 Agent depth=0，SubAgent depth=1
# spawn_subagents 工具检查：depth >= 1 时拒绝执行
```

### 8.3 第三层：超时机制

```python
import signal

class SubAgent:
    def run_with_timeout(self, timeout=30):
        def timeout_handler(signum, frame):
            raise TimeoutError()
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout)  # 30秒后超时
        try:
            return self.run()
        finally:
            signal.alarm(0)  # 取消 alarm
```

---

## 九、参考项目

| 项目 | 框架 | 代码量 | 特点 |
|------|------|--------|------|
| [LangGraph](https://github.com/langchain-ai/langgraph) | LangGraph | 完整框架 | 图状态机，最灵活 |
| [autogen](https://github.com/microsoft/autogen) | AutoGen | 完整框架 | 微软出品，结构化 |
| [CrewAI](https://github.com/crewAIInc/crewAI) | CrewAI | 完整框架 | 角色驱动，易用 |
| [Swarm](https://github.com/openai/swarm) | Swarm | ~500 行 | 轻量，教育向 |

---

## 附录：常见问题

**Q: Subagent 和 Multi-Agent 有什么区别？**

A: 概念有重叠。Subagent 通常指**层级嵌套**（主 Agent 创建子 Agent），Multi-Agent 更广泛，包括对等 Agent 协作。

**Q: 为什么不直接用 LangGraph？**

A: LangGraph 适合复杂图结构。对于我们 1000 行级别的最小实现，过重的框架不合适。我们只需要并行执行能力，不需要完整的状态机。

**Q: 工具注册隔离够用吗？**

A: 配合 depth 参数和超时，三层防护足够防止误用。真正的递归调用（图灵完备意义上的）在实践中很少发生。
