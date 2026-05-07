# 02: 构建智能体

上一篇我们理解了"为什么"——LLM + 工具 = 智能体。这篇我们动手构建一个。

最终产物是 `minimal/` 目录下的 4 个文件，共 526 行。建议先通读本篇理解思路，再对照源码阅读。

## ReAct 循环

智能体的核心是一个循环：

```
用户输入 → LLM 思考 → 需要工具？
  ├─ 是 → 执行工具 → 结果回注 → 继续 LLM 思考
  └─ 否 → 返回文本回复
```

这就是 ReAct（Reasoning + Acting）模式。LLM 不是一次性给出答案，而是可以多轮"思考-行动"。

## 四个模块

| 文件 | 职责 |
|------|------|
| `context.py` | 管理消息列表，负责裁剪和配对完整性 |
| `llm.py` | 封装 Anthropic API 调用，带重试 |
| `tools.py` | 注册工具，执行工具，管理危险确认 |
| `agent.py` | 编排 ReAct 循环，提供 REPL 入口 |

下面逐个讲解。

---

## context.py — 消息管理

LLM API 需要一个消息列表，每条消息有 `role`（system/user/assistant）和 `content`。

```python
class Context:
    def __init__(self, system_prompt: str = "", keep_last_n: int = 40):
        self.system_prompt = system_prompt
        self.messages: list[dict] = []
        self.keep_last_n = keep_last_n
```

### 添加消息

四种消息类型，对应四个方法：

```python
c.add_user("hello")                    # 用户消息
c.add_assistant_text("hi there")       # 助手纯文本
c.add_assistant_message(content_blocks) # 助手含 tool_use 的消息
c.add_tool_results(results)            # 工具结果（批量）
```

为什么 `add_assistant_text` 和 `add_assistant_message` 要分开？因为 Anthropic API 对消息格式有严格要求：
- 纯文本回复：`content` 是字符串
- 含工具调用的回复：`content` 是 block 列表

混用会导致 API 报错。

### 工具结果的批量添加

`add_tool_results` 接收一个列表：`[(tool_use_id, content, is_error), ...]`

```python
c.add_tool_results([
    ("id_1", "file contents...", False),
    ("id_2", "Error: file not found", True),
])
```

为什么是批量而不是逐条？因为 Anthropic API 要求同一轮的所有工具结果合并为一条 `user` 消息。如果逐条添加，会产生多条 `user` 消息，API 会拒绝。

### 裁剪

对话越来越长，token 越来越多。`_trim()` 保留最近 N 条消息，但：
- 保护第一条用户消息（对话的起点）
- 调用 `_ensure_pair_integrity()` 确保没有孤立的 `tool_use` 或 `tool_result`

什么是"孤立"？如果裁剪掉了 `tool_use` 消息但留下了对应的 `tool_result`，API 会报错。`_ensure_pair_integrity()` 检测并移除这些孤立项。

---

## llm.py — LLM 通信

```python
class LLMAdapter:
    def chat(self, messages: list[dict], tools: list[dict] = None,
             max_retries: int = 3) -> tuple[str, list]:
```

返回 `(stop_reason, content_blocks)`：
- `end_turn` — LLM 完成了回复
- `tool_use` — LLM 想调用工具
- `max_tokens` — 输出被截断，需要续传

### 重试

网络不稳定、API 限流是常态。重试策略：
- 3 次指数退避 + 随机抖动
- 仅对 `RateLimitError`、`InternalServerError`、`APIConnectionError`、`APITimeoutError` 重试
- `BadRequestError` 不重试（参数错误，重试也没用）

### 懒初始化

`_get_client()` 在第一次调用时才创建 `anthropic.Anthropic` 实例。这样 import 时不需要网络，测试时也方便 mock。

---

## tools.py — 工具注册与执行

### ToolResult

工具执行的结果有三种：

```python
ToolResult.ok("file contents...")       # 成功
ToolResult.error("file not found")      # 失败
ToolResult.confirm("执行命令: rm -rf /") # 需要用户确认
```

`needs_confirm=True` 时，Agent 会暂停，打印 `confirm_message`，等待用户输入 y/N。

### ToolRegistry

```python
registry = create_tools()  # 创建带 5 个内置工具的注册表
registry.tool_definitions()  # → 返回 Anthropic API 格式的工具定义
registry.execute("bash", {"command": "ls"})  # → ToolResult
```

`tool_definitions()` 返回的格式直接传给 LLM API，LLM 据此知道有哪些工具可用。

### 5 个内置工具

| 工具 | 危险 | 说明 |
|------|------|------|
| bash | 是 | 子进程执行，含 readonly 白名单 |
| read_file | 否 | 读文件 |
| write_file | 是 | 写文件 |
| edit_file | 是 | 查找替换编辑 |
| glob | 否 | 文件模式搜索 |

### bash 的只读检测

`bash_is_readonly()` 判断命令是否安全：
- 第一个词在白名单（ls, cat, git, grep...）→ 只读
- 命令含 `|`, `>`, `$()`, 反引号 → 非只读（防止管道/重定向绕过）

只读命令自动批准，不需要用户确认。非只读命令需要确认。

---

## agent.py — ReAct 循环

```python
class Agent:
    def run(self, user_input: str) -> str:
```

核心循环逻辑：

```python
for _ in range(self.max_steps):  # 最多 30 步
    stop_reason, blocks = self.llm.chat(messages, tool_defs)

    if stop_reason == "end_turn":
        # LLM 完成回复，返回文本
        return text

    if stop_reason == "tool_use":
        # 执行工具，结果回注上下文
        for tool_block in tool_blocks:
            result = self.tools.execute(name, args)
            if result.needs_confirm:
                # 同步确认
                answer = input("确认执行? [y/N] ")
                ...
        self.context.add_assistant_message(content_blocks)
        self.context.add_tool_results(results)
        continue  # 继续循环

    if stop_reason == "max_tokens":
        # 输出被截断，保存已有文本，注入"请继续"
        self.context.add_assistant_text(partial_text)
        self.context.add_user("请继续输出...")
        continue
```

注意 `add_assistant_message` 和 `add_tool_results` 的顺序：先保存 LLM 的 tool_use 消息，再添加工具结果。这样上下文中的消息序列是 `assistant(tool_use) → user(tool_results)`，符合 API 要求。

### REPL

```python
while True:
    user_input = input(">>> ")
    response = agent.run(user_input)
    print(response)
```

支持 `/quit` 退出和 `/clear` 清空上下文。

---

## 运行它

本篇讲解的所有代码就是 `minimal/` 目录的完整实现：

```bash
pip install -r minimal/requirements.txt
echo "ANTHROPIC_API_KEY=your-key" > .env
python -m minimal.agent
```

526 行，4 个文件，一个完整可运行的 ReAct 智能体。

---

## 完整版差异

minimal 是学习用的最小实现。完整版（`agent/`）增加了：

| 特性 | minimal | 完整版 |
|------|---------|--------|
| 确认机制 | 同步 `input()` | 异步事件，TUI 弹窗 |
| 取消 | 无 | `cancel_event` 轮询 |
| 子智能体 | 无 | spawn + fork 模式 |
| 任务系统 | 无 | JSON + 文件锁 |
| 技能系统 | 无 | 预设 prompt + 工具集 |
| LLM 协议 | 仅 Anthropic | Anthropic + OpenAI |
| 工具数量 | 5 | 7（+ grep, fetch）|
| 会话持久化 | 无 | 保存/恢复 |

想了解这些扩展特性的设计思路？继续阅读 [07: 超越 Minimal](07_beyond_minimal.md)。
