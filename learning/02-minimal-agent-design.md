# 最小 Agent 循环实战手册

## 前言

本书面向想理解 Agent 本质并动手实现的开发者。

我们会从头开始，先讲清概念，再逐步构建一个最小 Agent 循环。代码量控制在 1000 行以内，核心逻辑一览无余。

**前置知识**：Python 基础，了解 LLM API 调用（OpenAI/Anthropic 风格）。

---

## 一、Agent 是什么

### 1.1 从问答到循环

普通 LLM 调用是这样的：

```
用户 → LLM → 回复
```

这是**一次性问答**。你问，它答，结束。

但有些任务需要**多步操作**，比如："帮我读取 /tmp/test.txt 文件，统计行数，然后发给我"。

这需要三步：读文件 → 统计 → 发给你。LLM 怎么知道该读哪个文件？读完后怎么统计？发到哪里？

这就需要让 LLM **能够使用工具**，并形成**循环**：

```
用户输入 → LLM 推理 → [要调用工具？] → 执行工具 → 返回结果 → LLM 推理 → ...
```

### 1.2 Agent 的定义

Anthropic 对 Agent 的定义：

> **Agent**：LLM 动态指导自身流程和工具使用。

对应的另一种范式叫**工作流（Workflow）**，它通过预定义代码路径编排 LLM 和工具。

| 范式 | 特点 | 适用场景 |
|------|------|----------|
| **工作流** | 步骤固定，代码控制 | 任务明确、可预测 |
| **Agent** | LLM 决定下一步做什么 | 开放式问题、灵活应对 |

### 1.3 Agent 的本质

**Agent = 循环 + 工具 + 上下文管理**

一个完整的 Agent 循环需要：

1. **循环控制器** — 控制循环次数，决定何时停止
2. **工具注册表** — 管理可用工具，提供执行能力
3. **LLM 适配层** — 对接不同模型，统一接口
4. **会话上下文** — 管理对话历史，处理 token 限制

---

## 二、Tool Calling 协议

这是 Agent 的核心机制。理解它，你就能理解 Agent 为什么能"调用工具"。

### 2.1 关键认知

**LLM 没有真正调用任何函数。**

当 LLM 输出"我要调用 read_file"时，它只是在**生成一段符合格式的文本**。真正的函数执行，是你的代码做的。

所以这个机制叫 **Tool Use**（工具使用建议），而不是 Tool Call（工具调用）。

### 2.2 Anthropic 协议详解

#### 第一步：告诉 LLM 有哪些工具可用

```python
# 工具定义：告诉 LLM 有哪些工具、怎么用
tools = [
    {
        "name": "read_file",                      # 工具名：LLM 用它来"调用"
        "description": "读取文件内容",             # 描述：让 LLM 知道什么时候该用
        "input_schema": {                          # 参数规范：LLM 生成参数的依据
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"}
            },
            "required": ["path"]                   # 必填参数
        }
    }
]
```

你把这个列表传给 LLM，它就"知道"有这些工具可以用。

#### 第二步：LLM 输出结构化文本

当 LLM 判断需要调用工具时，它会输出：

```json
{
    "type": "tool_use",
    "id": "toolu_01A...",
    "name": "read_file",
    "input": {"path": "/tmp/test.txt"}
}
```

这看起来像 JSON，但它是 **LLM 生成的一段文本**，格式恰好符合你的 schema 定义。

#### 第三步：你的代码解析并执行

```python
# 发送请求给 LLM
# 关键：tools 参数告诉 LLM 有哪些工具可用
response = client.messages.create(
    model="claude-sonnet-4-7",
    tools=tools,           # 工具定义列表
    messages=messages       # 对话历史（包含之前的 tool_use 和 tool_result）
)

# 检查 stop_reason 判断 LLM 的意图
if response.stop_reason == "tool_use":
    # LLM 说想调用工具 → 执行工具并把结果喂回去
    for block in response.content:
        if block.type == "tool_use":
            tool_name = block.name      # "read_file" — LLM 想调用的工具
            tool_args = block.input     # {"path": "/tmp/test.txt"} — 生成的参数

            # 你的代码真正执行这个函数（LLM 没有执行能力）
            result = tool_registry.execute(tool_name, tool_args)

            # 把结果塞回给 LLM — 注意 role 是 "user"
            # tool_use_id 必须与 LLM 生成的一致，用于配对
            messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": block.id,    # 配对 ID
                    "content": result            # 执行结果
                }]
            })
```

### 2.3 完整循环流程

```
用户: "帮我读取 /tmp/test.txt 并统计行数"

[第 1 轮]
LLM: "我需要先读取文件"
     stop_reason = "tool_use"          ← LLM 请求工具
     content = [{type: "tool_use",      ← 工具调用块
                 name: "read_file",
                 input: {path: "/tmp/test.txt"}}]

执行 read_file(path="/tmp/test.txt")    ← 你的代码真正执行
→ 返回文件内容（假设 100 行）

[第 2 轮]
LLM: "我需要统计行数"
     stop_reason = "tool_use"
     content = [{type: "tool_use",
                 name: "bash",
                 input: {command: "wc -l /tmp/test.txt"}}]

执行 bash(command="wc -l /tmp/test.txt")
→ 返回 "100"

[第 3 轮]
LLM: "文件 /tmp/test.txt 共有 100 行。"
     stop_reason = "end_turn"           ← 完成，输出最终回复
```

### 2.4 为什么 LLM 能输出正确格式？

这是**指令微调（Instruction Tuning）**的效果：

1. **训练时**：给模型大量 (prompt + 工具定义, tool_call) 的样本
2. **微调后**：模型学会"看到工具描述 + 用户问题 → 输出对应格式"
3. **推理时**：模型只是在"模仿"训练时学到的格式

### 2.5 协议差异

| 协议 | 停止原因 | 工具块类型 |
|------|---------|-----------|
| Anthropic | `tool_use` | `tool_use` |
| OpenAI | `function_call` | `function_call` |
| GLM/MiniMax | 兼容 OpenAI | 兼容 OpenAI |

国产大模型通常兼容 OpenAI 格式，通过 `base_url + api_key` 接入。

---

## 三、会话上下文（Context）管理

### 3.1 Context 是什么

LLM 没有记忆。每次 API 调用都是独立的，**全靠你传入的 messages 构建上下文**。

```python
# 每次请求都要传完整上下文
response = client.messages.create(
    messages=messages,      # 对话历史（必须）
    tools=tools,            # 工具定义（必须）
    system=system_prompt    # 系统提示（必须）
)
```

### 3.2 Context 的三大组成部分

```
┌─────────────────────────────────────────────────┐
│                   System Prompt                   │
│  - Agent 身份和约束                              │
│  - 核心指令                                     │
├─────────────────────────────────────────────────┤
│                   Messages                       │
│  - 对话历史                                     │
│  - tool_use / tool_result 交替                 │
├─────────────────────────────────────────────────┤
│                    Tools                         │
│  - 工具定义列表（每次请求都要传）                 │
└─────────────────────────────────────────────────┘
```

### 3.3 消息结构

**角色（Role）**：

| Role | 含义 | 示例 |
|------|------|------|
| `system` | 系统提示 | Agent 身份设定 |
| `user` | 用户输入或工具结果 | 两者都叫 user |
| `assistant` | LLM 输出 | 文本或 tool_use |

**注意**：`tool_result` 的 role 是 `user`，不是 `assistant`。这是协议规定。

**内容块类型**：

| 类型 | 谁生成 | 说明 |
|------|--------|------|
| `text` | LLM | 普通文本回复 |
| `tool_use` | LLM | 工具调用请求 |
| `tool_result` | 你的代码 | 工具执行结果 |

### 3.4 配对机制

LLM 输出 tool_use 时会带一个唯一 `id`：

```json
{
    "type": "tool_use",
    "id": "toolu_01A...",
    "name": "read_file",
    "input": {"path": "/tmp/test.txt"}
}
```

你执行后返回结果时，必须携带相同的 `id`：

```json
{
    "type": "tool_result",
    "tool_use_id": "toolu_01A...",
    "content": "文件内容..."
}
```

这是 LLM 将"结果"与"调用"关联起来的方式。

### 3.5 上下文膨胀问题

每轮 tool calling 会让 messages 增长：

```
第 1 轮：1 条消息
第 2 轮：3 条消息（user + assistant + user 结果）
第 3 轮：5 条消息
...
```

10 轮后就是 20+ 条消息，可能达到几万 tokens。

如果不加管理：
1. **超出限制** — API 报错
2. **成本飙升** — 按 token 计费
3. **效果下降** — 无关内容干扰 LLM 注意力

### 3.6 截断策略

当上下文快要超限时，需要裁剪。以下是三种策略：

**策略 1：保留最近 N 轮**（最简单）

```python
def truncate_keep_recent(messages, max_tokens, keep_last_n=10):
    """
    简单策略：只看消息数量，不精确算 token
    - 如果还没超限，直接返回
    - 超限了就只保留最近 N 条
    """
    if estimate_tokens(messages) <= max_tokens:
        return messages
    return messages[-keep_last_n:]  # 丢弃旧消息，保留最新的
```

**策略 2：工具结果先截断**（推荐组合使用）

工具执行结果（文件内容、bash 输出）往往是最大的膨胀源：

```python
def truncate_tool_result(result, max_chars=2000):
    """
    工具结果截断：在执行时就控制大小
    - 如果结果太长，只保留最后 500 字符
    - 告诉 LLM 结果被截断了
    """
    if len(result) > max_chars:
        return f"[结果截断]\n{result[-500:]}"  # 保留结尾，可能更有用
    return result
```

**策略 3：LLM 摘要**（保留信息最多）

用另一个 LLM 调用把历史压缩成摘要：

```python
async def compress_history(messages, llm):
    """
    摘要压缩：调用 LLM 把历史总结
    - 成本高（多一次 LLM 调用）
    - 但能保留更多有用信息
    - 适合长对话场景
    """
    summary = await llm.chat([
        {"role": "user", "content": f"摘要以下对话，保留关键信息：\n{messages}"}
    ])
    # 返回一个"伪装的"对话历史
    return [
        {"role": "system", "content": "..."},           # 原始 system prompt
        {"role": "user", "content": f"[摘要] {summary}"}  # 摘要作为用户消息
    ]
```

**推荐组合**：入门用策略 1，简单有效。进阶用策略 1+2 组合，保留更多信息。

---

## 四、构建最小 Agent 循环

现在我们来实现一个最小的 Agent 循环。

### 4.1 核心组件

我们需要四个组件：

| 组件 | 职责 |
|------|------|
| `Agent` | 循环控制器 |
| `ToolRegistry` | 工具注册与执行 |
| `LLMAdapter` | 模型接口适配 |
| `Context` | 会话状态管理 |

### 4.2 完整代码（带逐行注释）

```python
"""
最小 Agent 循环实现（Anthropic 协议）
约 180 行代码，核心逻辑一览无余
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import Callable
import anthropic

# ============================================================
# 1. 工具注册表 (ToolRegistry)
# ============================================================
# 职责：管理所有可用工具，提供注册、执行、查询功能
# 工具是 Agent 感知世界的"手脚"

@dataclass
class Tool:
    name: str                    # 工具名称，LLM 用它来"调用"工具
    description: str              # 工具描述，告诉 LLM 什么时候该用它
    input_schema: dict           # 参数规范，LLM 生成参数时参考，也是验证依据
    handler: Callable            # 真正的执行函数，由你的代码实现

class ToolRegistry:
    """工具注册表：管理所有工具的注册和执行"""

    def __init__(self):
        self.tools: dict[str, Tool] = {}

    def register(self, name: str, description: str,
                 input_schema: dict, handler: Callable):
        self.tools[name] = Tool(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=handler
        )

    def execute(self, name: str, args: dict) -> str:
        if name not in self.tools:
            return f"Error: Unknown tool '{name}'"
        try:
            result = self.tools[name].handler(**args)
            return str(result)
        except Exception as e:
            return f"Error executing {name}: {e}"

    def list_for_llm(self) -> list[dict]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema
            }
            for t in self.tools.values()
        ]

# ============================================================
# 2. LLM 适配层 (LLMAdapter)
# ============================================================
# 职责：封装 Anthropic SDK，提供统一接口
# 支持 API 重试和错误兜底

@dataclass
class LLMResponse:
    """LLM 响应的标准化结构"""
    content: str | list      # 响应内容：字符串（普通回复）或列表（tool_use 块）
    stop_reason: str         # 停止原因：决定下一步该做什么

class LLMError(Exception):
    """LLM 请求错误"""
    pass

class LLMAdapter:
    """LLM 适配器：对接 Anthropic 协议"""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    def chat(self, messages: list[dict], tools: list[dict], max_retries: int = 3) -> LLMResponse:
        """发送请求到 LLM，带重试"""
        for attempt in range(max_retries):
            try:
                return self._chat_once(messages, tools)
            except (anthropic.OverloadedError, anthropic.RateLimitError,
                    anthropic.APITimeoutError) as e:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    raise LLMError(f"API 请求失败（重试 {max_retries} 次后）: {e}")
            except anthropic.APIConnectionError as e:
                raise LLMError(f"API 连接失败: {e}")
            except anthropic.BadRequestError as e:
                raise LLMError(f"请求参数错误: {e}")

    def _chat_once(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        """单次请求 LLM"""
        client = anthropic.Anthropic(api_key=self.api_key, base_url=self.base_url)

        # 分离 system prompt 和对话消息
        system_prompt = ""
        conversation_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                conversation_messages.append(msg)

        kwargs = {
            "model": self.model,
            "messages": conversation_messages,
            "max_tokens": 4096,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = tools

        response = client.messages.create(**kwargs)

        # 解析响应
        if response.stop_reason == "end_turn":
            text_content = ""
            for block in response.content:
                if block.type == "text":
                    text_content += block.text
            return LLMResponse(content=text_content, stop_reason="end_turn")

        if response.stop_reason == "tool_use":
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

        # 其他情况
        text_content = ""
        for block in response.content:
            if block.type == "text":
                text_content += block.text
        return LLMResponse(content=text_content, stop_reason=response.stop_reason)

# ============================================================
# 3. 会话上下文 (Context)
# ============================================================
# 职责：管理对话历史，处理 token 限制
# Anthropic 协议：tool_result 的 role 是 "user"

class Context:
    """会话上下文：管理对话历史"""

    def __init__(self, system_prompt: str = "", max_tokens: int = 4096, keep_last_n: int = 10):
        self.system_prompt = system_prompt
        self.messages: list[dict] = []
        self.max_tokens = max_tokens
        self.keep_last_n = keep_last_n

    def add_user(self, content: str):
        """添加用户消息"""
        self.messages.append({"role": "user", "content": content})
        self._trim()

    def add_assistant_message(self, content: list):
        """添加 assistant 消息（包含 tool_use blocks）"""
        self.messages.append({"role": "assistant", "content": content})
        self._trim()

    def add_tool_result(self, tool_use_id: str, content: str):
        """
        添加工具执行结果
        重要：role 是 "user"，不是 "assistant"！这是 Anthropic 协议规定
        """
        self.messages.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": content
            }]
        })
        self._trim()

    def _trim(self):
        """保持消息数量不超过 keep_last_n"""
        if len(self.messages) > self.keep_last_n:
            self.messages = self.messages[-self.keep_last_n:]

    def get_messages(self) -> list[dict]:
        """返回完整消息列表（system 作为独立条目）"""
        msgs = [{"role": "system", "content": self.system_prompt}]
        msgs.extend(self.messages)
        return msgs

# ============================================================
# 4. Agent 循环 (Agent)
# ============================================================
# 核心：控制整个 Agent 的运行循环

class Agent:
    """Agent：循环控制器"""

    def __init__(self, llm_adapter: LLMAdapter, tools, context: Context, max_steps: int = 10):
        self.llm_adapter = llm_adapter      # LLM 适配器
        self.tools = tools                  # 工具注册表
        self.context = context              # 上下文（外部传入）
        self.max_steps = max_steps          # 最大循环次数，防止死循环

    def run(self, user_input: str) -> str:
        """
        运行 Agent

        流程：
        1. 添加用户输入到上下文
        2. 循环调用 LLM
           - 如果 LLM 请求工具 → 执行工具，添加结果，继续循环
           - 如果 LLM 返回文本 → 返回结果，结束
        3. 超过 max_steps 仍未结束 → 返回错误
        """
        # 第一步：把用户输入加入上下文
        self.context.add_user(user_input)

        # 第二步：循环
        for step in range(self.max_steps):
            messages = self.context.get_messages()
            tools = self.tools.list_for_llm() if hasattr(self.tools, 'list_for_llm') else []

            try:
                response = self.llm_adapter.chat(messages, tools)
            except LLMError as e:
                return f"[LLM Error] {e}"

            if response.stop_reason == "end_turn":
                return response.content

            if response.stop_reason == "tool_use":
                # 添加 assistant 的 tool_use 消息到上下文
                self.context.add_assistant_message(response.content)

                # 执行工具并添加结果
                for tool_use in response.content:
                    tool_name = tool_use["name"]
                    tool_args = tool_use["input"]
                    tool_id = tool_use["id"]

                    result = self.tools.execute(tool_name, tool_args)
                    self.context.add_tool_result(tool_id, result)
                continue

        return f"Error: Exceeded max_steps ({self.max_steps})"

# ============================================================
# 5. 使用示例
# ============================================================

def main():
    # 创建 LLM 适配器（Anthropic 协议）
    llm = LLMAdapter(
        api_key=os.getenv("ANTHROPIC_API_KEY", "your-api-key"),
        base_url=os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
        model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
    )

    # 创建工具注册表
    tools = ToolRegistry()

    # 注册内置工具
    tools.register(
        name="read_file",
        description="读取文件内容",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"]
        },
        handler=lambda path: open(path).read()
    )

    tools.register(
        name="bash",
        description="执行 shell 命令",
        input_schema={
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"]
        },
        handler=lambda command: __import__("subprocess").run(
            command, shell=True, capture_output=True, text=True
        ).stdout
    )

    # 创建上下文（外部传入，Agent 不自己创建）
    context = Context(
        system_prompt="You are a helpful coding assistant.",
        max_tokens=4096,
        keep_last_n=20
    )

    # 创建 Agent
    agent = Agent(llm, tools, context)

    # 运行
    result = agent.run("帮我读取 /tmp/test.txt 并统计行数")
    print(result)

if __name__ == "__main__":
    main()
```

### 4.3 代码解读

**ToolRegistry**：管理工具定义和执行。关键方法是 `list_for_llm()`，返回符合协议的工具列表。

**LLMAdapter**：封装 Anthropic SDK 调用。支持 API 重试（指数退避）和错误兜底（`LLMError`）。

**Context**：管理会话状态。关键方法是 `add_assistant_message()`（添加 tool_use 消息）和 `add_tool_result()`（添加工具结果，role 为 user）。

**Agent**：核心循环。`run()` 方法在一个 for 循环中：
1. 调用 LLM
2. 检查 stop_reason
3. 如果是 tool_use，添加 assistant 消息到上下文，执行工具并追加结果，继续循环
4. 如果是 end_turn，返回结果
5. 如果 LLM 报错，返回 `[LLM Error]` 提示

---

## 五、Skill 加载机制

当 Agent 需要很多技能时，我们需要管理这些技能的定义和加载方式。

### 5.1 Skill 的本质

**Skill = prompt + 可选的工具/脚本**

```
skill-name/
├── SKILL.md          # 核心：给 LLM 看的指令
├── scripts/          # 可选：配套脚本
│   └── do_something.py
└── config.yaml       # 可选：配置
```

```markdown
<!-- SKILL.md 示例 -->
---
name: meeting-notes
description: 帮你生成会议纪要
---

# Meeting Notes Skill

当用户要求生成会议纪要时：
1. 调用 get_meeting_notes 获取原始内容
2. 按模板格式整理
3. 输出格式化结果
```

### 5.2 三种加载策略

**策略 1：全部加载（简单场景）**

启动时把所有 Skill 的完整内容加载到 system prompt。

```python
# 问题：Skill 太多时上下文爆炸
# 假设有 50 个 Skill，每个 500 tokens，那就是 25K tokens ！
system_prompt = f"""
你是一个助手。
## Skills
{all_skills_content}  # 全部塞进去 → 爆炸
"""
```

**策略 2：渐进式披露（推荐）**

核心思想：**启动时只加载元数据（名称 + 描述），运行时按需加载完整内容**。

```python
# 启动时：只加载元数据 → system prompt 保持精简
skill_metadata = [
    {"name": "meeting-notes", "description": "生成会议纪要"},
    {"name": "translator", "description": "多语言翻译"},
]

# 运行时按需加载：Agent 说要用哪个 Skill，才读哪个文件
async def load_skill_full(skill_name: str) -> dict:
    # 异步读取 Skill 的完整定义
    content = await read_file_async(f"skills/{skill_name}/SKILL.md")
    return {
        "name": skill_name,
        "instruction": content    # 完整指令内容
    }
```

这样做可以节省 **70-90% 的 token**，因为大多数 Skill 在整个会话中都不会被用到。

**策略 3：动态工具加载**

更激进的做法：**连工具定义都不一次性全传**，根据意图动态决定加载哪些。

```python
class DynamicToolLoader:
    """根据上下文意图，动态加载对应工具集"""

    def __init__(self):
        self.cache = {}        # 缓存已加载的工具集
        self.all_tools_meta = {}  # 所有工具的元数据

    def get_tools(self, context: Context) -> list[dict]:
        # 从最后一条消息判断用户意图
        intent = classify_intent(context.messages[-1])

        # 命中缓存？直接返回
        if intent in self.cache:
            return self.cache[intent]

        # 没命中？加载对应意图的工具集
        tools = self.load_tools_for_intent(intent)
        self.cache[intent] = tools   # 缓存
        return tools

    def classify_intent(self, message: dict) -> str:
        # 简单实现：关键字匹配
        # 进阶：可以用小模型做分类
        content = message.get("content", "")
        if "翻译" in content:
            return "translator"
        if "会议" in content:
            return "meeting"
        return "default"
```

### 5.3 System Prompt 分层管理

OpenClaw 采用四层分离，避免每次重建整个 prompt：

```
┌──────────────────────────────────┐
│ Layer 1: SOUL.md                 │
│ 核心人格、决策逻辑（几乎不变）      │
├──────────────────────────────────┤
│ Layer 2: openclaw.json          │
│ 工具/Skill 能力配置               │
├──────────────────────────────────┤
│ Layer 3: HEARTBEAT.md            │
│ 周期性主动行为触发规则             │
├──────────────────────────────────┤
│ Layer 4: MEMORY.md               │
│ 持续进化的经验记录                 │
└──────────────────────────────────┘
```

---

## 六、Context Guard 机制

高级框架（如 OpenClaw）在压缩上下文时，不是简单截断，而是**多阶段防护**：

```python
class ContextGuard:
    """
    OpenClaw 的上下文守卫
    核心思想：压缩不是丢弃，而是把重要信息转移到更持久的地方
    """

    def compress(self, messages: list[Message]) -> list[Message]:
        # 阶段 1：静默 memory flush
        # 强制 Agent 把关键状态写入文件（Memory）
        # 用户完全感知不到这个操作
        self.silent_flush(messages)

        # 阶段 2：反向遍历，保留关键内容
        # 从最新的消息开始，保留对理解当前任务必需的内容
        # 比如：任务目标、关键决策点、重要结果
        preserved = self.preserve_key_content(messages)

        # 阶段 3：早期消息用 LLM 摘要
        # 更早的历史（已被静默 flush）用 LLM 压缩成摘要
        # 摘要作为结构化信息保留
        early_summary = self.summarize_early(messages[:-preserved])

        # 返回：摘要 + 保留的关键内容
        return early_summary + preserved
```

关键点：
- 不丢失关键信息（通过 memory flush 持久化）
- 用户无感知（静默操作）
- 多轮压缩后仍保持上下文连贯性

---

## 七、参考项目

以下是最小 Agent 循环的优秀参考实现：

| 项目 | 代码量 | 特点 |
|------|--------|------|
| [felixwickholm/claude-agent-loop](https://github.com/felixwickholm/claude-agent-loop) | ~150 行 | 直接用 Anthropic SDK，最贴近官方协议 |
| [SandipKurmi/minimal-ai-agent](https://github.com/SandipKurmi/minimal-ai-agent) | 67 行 | 无框架，XML tag 解析，适合学习 |
| [RED523/minimal-loop-agent](https://github.com/RED523/minimal-loop-agent) | 单文件 | ReAct 风格，简洁易懂 |
| [fedewedreamlabsio/minimal-agent-framework](https://github.com/fedewedreamlabsio/minimal-agent-framework) | 完整框架 | 强调可审计、可回放 |
| [LeonEthan/agentlet](https://github.com/LeonEthan/agentlet) | 完整项目 | 可插拔 Provider + CLI |
| [OpenClaw](https://github.com/openclaw/openclaw) | 完整框架 | 无头运行时，四层配置体系 |

---

## 附录

### A. 关键技术点清单

**必须掌握**：
- LLM API 调用（messages API、tools 参数）
- Tool Calling 协议（tool_use 解析、tool_result 配对）
- ReAct 循环控制（while + max_steps）
- Schema 验证
- 错误处理与恢复（API 重试、LLMError 兜底）
- 上下文窗口管理

**进阶技能**：
- Streaming SSE（实时推送思考过程）
- 多工具并发执行
- 上下文压缩
- MCP 协议

### B. Anthropic 官方文档

- [Tool Use 官方文档](https://docs.anthropic.com/en/docs/build-with-claude/tool-use)
- [Agent 构建指南](https://docs.anthropic.com/en/docs/build-with-claude/agents-overview)

### C. 常见问题

**Q: LLM 为什么不直接调用工具？**

A: 当前 LLM 的本质是文本生成器，没有执行代码的能力。它只是按格式生成文本，你的代码解析并执行。

**Q: 如何防止 LLM 调用错误的工具？**

A: 做好两件事：1) Schema 验证执行前的参数；2) 工具描述要清晰准确。

**Q: max_steps 设置多少合适？**

A: 从 10 开始，根据任务复杂度调整。代码类任务可能需要 20-30 步。

**Q: 工具执行失败了怎么办？**

A: 把错误信息返回给 LLM，让它决定重试还是换策略。
