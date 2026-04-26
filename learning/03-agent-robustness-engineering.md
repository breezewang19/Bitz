# Agent 健壮性工程实战

## 前言

上一篇我们构建了最小 Agent 循环——它能跑，但离"生产可用"还很远。

真实场景中，LLM 会返回意外格式、API 会限流、工具输出会爆炸、用户会中断操作。每一个未处理的边界情况，都是一次崩溃或无限循环。

本文记录 Bitz 项目从"能跑"到"能稳定跑"的健壮性增强过程。所有问题都来自真实踩坑，所有修复都经过测试验证。

**前置知识**：阅读过 02（最小 Agent 循环），理解 Anthropic Tool Calling 协议。

---

## 一、问题全景

对照 Claude Code 和 OpenCode 两个成熟项目审计后，发现 8 个关键问题：

| # | 问题 | 级别 | 后果 |
|---|------|------|------|
| 1 | 多个 tool_result 未合并为单条 user 消息 | CRITICAL | API 返回 400 |
| 2 | max_tokens stop_reason 未处理 | CRITICAL | 无限循环消耗 credits |
| 3 | 多 pending tools + 混合确认场景丢失结果 | CRITICAL | 上下文不完整 |
| 4 | retry 逻辑太弱 | HIGH | 限流时频繁失败 |
| 5 | 工具输出无截断 | HIGH | 超出 context 限制 |
| 6 | 工具安全标记不完整 | HIGH | 危险操作未拦截 |
| 7 | API 调用无超时 | HIGH | 挂起时无限等待 |
| 8 | 中断后状态残留 | HIGH | 下次操作异常 |

下面逐个分析原因、修复方案和关键代码。

---

## 二、CRITICAL：API 协议违规导致 400 错误

### 2.1 问题：多个 tool_result 必须合并

Anthropic API 有一条硬性规则：**同一轮的所有 tool_result 必须放在一个 user 消息里**。

当 LLM 返回多个 tool_use 时，原始代码为每个结果创建独立的 user 消息：

```python
# 错误写法：每个 tool_result 一条消息
for tool_use in response.content:
    result = self.tools.execute(tool_name, tool_args)
    self.context.add_tool_result(tool_id, result)  # 每次创建新 user 消息
```

这导致 API 返回 400 错误，因为 Anthropic 期望：

```json
// 正确：所有 tool_result 在一个 user 消息中
{"role": "user", "content": [
    {"type": "tool_result", "tool_use_id": "t1", "content": "result1"},
    {"type": "tool_result", "tool_use_id": "t2", "content": "result2"}
]}
```

### 2.2 修复：add_tool_results 批量添加

```python
class Context:
    def add_tool_results(self, results: list[tuple[str, str]]) -> None:
        """添加多个 tool_result 到一条 user 消息"""
        blocks = []
        for tool_id, result in results:
            blocks.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": result,
            })
        self.messages.append({"role": "user", "content": blocks})
        self._trim()

    def add_tool_result(self, tool_use_id: str, content: str) -> None:
        """单个 tool_result（兼容方法，内部调用 add_tool_results）"""
        self.add_tool_results([(tool_use_id, content)])
```

在 loop.py 中，所有工具执行完后一次性写入：

```python
self.context.add_tool_results(
    [(tool_id, result) for tool_id, tool_name, tool_args, result in confirmed_results]
)
```

### 2.3 上下文裁剪的配对完整性

另一个相关问题：`_trim()` 裁剪旧消息时，可能把 assistant 的 tool_use 消息裁掉，但留下对应的 tool_result。这会导致 API 报错（tool_result 找不到对应的 tool_use）。

修复：裁剪后检查第一条消息是否为孤立的 tool_result，如果是则一并移除：

```python
def _trim(self) -> None:
    if len(self.messages) <= self.keep_last_n:
        return
    self.messages = self.messages[-self.keep_last_n:]
    # 移除孤立的 tool_result（对应的 tool_use 已被裁掉）
    while self.messages:
        first = self.messages[0]
        if first["role"] == "user" and isinstance(first.get("content"), list):
            has_tool_result = any(
                isinstance(b, dict) and b.get("type") == "tool_result"
                for b in first["content"]
            )
            if has_tool_result:
                self.messages.pop(0)
                continue
        break
```

**关键认知**：Anthropic 协议要求 tool_use 和 tool_result 严格配对。任何破坏配对的操作都会导致 API 错误。

---

## 三、CRITICAL：max_tokens 导致无限循环

### 3.1 问题

当 LLM 输出达到 `max_tokens` 限制时，`stop_reason` 为 `"max_tokens"` 而非 `"end_turn"`。

原始代码只处理了 `end_turn` 和 `tool_use` 两个分支。`max_tokens` 不匹配任何分支，于是进入下一轮循环——LLM 再次输出部分内容，再次触发 `max_tokens`，无限循环。

每次循环都是一次 API 调用，都在烧 credits。

### 3.2 修复

将 `max_tokens` 作为与 `end_turn` 同等地位的终止条件：

```python
if response.stop_reason == "end_turn":
    self.context.add_assistant_text(response.content)
    return response.content

if response.stop_reason == "tool_use":
    # ... 工具调用处理
    continue

# max_tokens 或其他 stop_reason：记录部分响应并返回
self.context.add_assistant_text(response.content)
if response.stop_reason == "max_tokens":
    return f"{response.content}\n\n[输出被截断，已达最大 token 限制]"
return response.content
```

**关键认知**：Agent 循环必须处理所有可能的 stop_reason。未处理的分支就是潜在的无限循环。

---

## 四、CRITICAL：混合确认场景的结果丢失

### 4.1 问题

当 LLM 返回多个 tool_use，其中部分需要确认时：

```
LLM 返回: [echo(无需确认), bash(需要确认)]
```

原始代码：
1. 执行 echo → 结果存入 `confirmed_results`（局部变量）
2. bash 需要确认 → 保存为 `_pending_confirm`，返回
3. 用户确认后调用 `confirm_pending` → 只写入 bash 的结果

echo 的结果呢？丢了。`confirmed_results` 是 `run()` 的局部变量，`confirm_pending` 访问不到。

### 4.2 修复

将 `confirmed_results` 保存为实例属性，`confirm_pending` 时一起写入：

```python
class Agent:
    def __init__(self, ...):
        self._confirmed_results: list = []  # 已确认但未写入上下文的工具结果

    def run(self, ...):
        if pending_tools:
            self._confirmed_results = confirmed_results  # 保存
            return result

    def confirm_pending(self, confirmed_tools: set) -> tuple:
        # ... 执行确认的工具
        result = self.tools.execute(tool_name, tool_args, confirmed=True, tool_id=tool_id)

        # 收集所有工具结果：之前已确认的 + 刚确认的
        all_results = list(self._confirmed_results)
        all_results.append((tool_id, tool_name, tool_args, result))
        self._confirmed_results = []

        self.context.add_tool_results(
            [(tid, res) for tid, tname, targs, res in all_results]
        )
        return (True, result)
```

**关键认知**：Agent 循环中的状态跨越多次方法调用时，必须用实例属性而非局部变量。任何需要跨 run/confirm 保存的数据都是如此。

---

## 五、HIGH：retry 逻辑增强

### 5.1 问题

原始 retry 只有 3 次，backoff 为 1s/2s——太短了。Anthropic 的 rate limit 冷却期通常更长。

### 5.2 参考 OpenCode 的做法

OpenCode 的 retry 策略：
- 最多 8 次重试
- exponential backoff：2s, 4s, 8s, 16s...
- 20% jitter 防止惊群
- 从 RateLimitError 的 response header 中提取 Retry-After
- 重试期间检查 cancel_event（用户可能已经按了 ESC）

### 5.3 实现

```python
def chat(self, messages, tools, cancel_event=None, max_retries=5):
    for attempt in range(max_retries):
        try:
            return self._chat_once(messages, tools, cancel_event)
        except LLMError:
            raise  # 不可重试的错误直接抛出
        except Exception as e:
            if retryable and attempt < max_retries - 1:
                # exponential backoff: 2s, 4s, 8s, 16s, 32s
                base_wait = 2 ** (attempt + 1)
                # 20% jitter 防止惊群
                jitter = base_wait * random.uniform(-0.2, 0.2)
                wait = max(1, base_wait + jitter)
                # 从 RateLimitError 中提取 Retry-After header
                retry_after = self._get_retry_after(e)
                if retry_after:
                    wait = max(wait, retry_after)
                # 分段 sleep，每 0.5s 检查 cancel_event
                self._cancel_aware_sleep(wait, cancel_event)
                continue
```

**cancel_aware_sleep** 是关键细节——如果用户按了 ESC，不应该在 sleep 中卡住：

```python
def _cancel_aware_sleep(self, seconds, cancel_event=None):
    end_time = time.monotonic() + seconds
    while time.monotonic() < end_time:
        if cancel_event and cancel_event.is_set():
            raise LLMError("已中断")
        time.sleep(min(0.5, end_time - time.monotonic()))
```

**关键认知**：retry 的核心不是"重试几次"，而是"等多久再试"。backoff + jitter + Retry-After 三者配合，才能在限流场景下稳定恢复。

---

## 六、HIGH：工具输出截断

### 6.1 问题

bash 和 read_file 的输出没有长度限制。一个 `cat large_file.log` 可能返回几十万字符，直接撑爆 context window。

### 6.2 参考 OpenCode

OpenCode 限制工具输出为 30000 字符，超出时保留首尾，中间省略。

### 6.3 实现

```python
MAX_OUTPUT = 30000
HALF_OUTPUT = MAX_OUTPUT // 2

def _truncate(text: str, limit: int = MAX_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    head = text[:HALF_OUTPUT]
    tail = text[-HALF_OUTPUT:]
    omitted = len(text) - len(head) - len(tail)
    return f"{head}\n... [省略 {omitted} 字符] ...\n{tail}"
```

为什么保留首尾而非只保留头部？因为工具输出的末尾往往是最终结果（如编译错误、命令退出码），比开头更有价值。

**关键认知**：工具输出是 context 膨胀的主要来源。在执行阶段截断，比在上下文管理阶段裁剪更高效——裁剪会丢失整条消息，截断只丢失部分内容。

---

## 七、HIGH：工具安全增强

### 7.1 问题

原始代码中，`edit_file` 未标记为 dangerous，意味着 LLM 可以不经确认直接修改文件。此外，bash 工具对所有命令一视同仁——`ls` 和 `rm -rf /` 需要同样的确认流程。

### 7.2 三层安全模型

```
┌─────────────────────────────────────┐
│ Layer 1: 只读白名单（自动批准）       │
│ ls, pwd, cat, git status...         │
├─────────────────────────────────────┤
│ Layer 2: 普通危险（需确认）           │
│ bash, write_file, edit_file         │
├─────────────────────────────────────┤
│ Layer 3: 额外危险（强制确认）         │
│ rm -rf, shutdown, pip install...    │
└─────────────────────────────────────┘
```

### 7.3 实现

在 ToolRegistry 中增加两个可选回调：

```python
@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    handler: Callable
    dangerous: bool = False
    is_readonly: Optional[Callable] = None       # 判断参数是否为只读操作
    is_extra_dangerous: Optional[Callable] = None # 判断参数是否为额外危险操作
```

在 execute 中按层级处理：

```python
def execute(self, name, args, confirmed=False, tool_id=None):
    tool = self.tools[name]

    # Layer 1: 只读命令自动批准
    if tool.dangerous and tool.is_readonly:
        if tool.is_readonly(args["command"]):
            confirmed = True

    # Layer 3: 额外危险命令强制确认
    if tool.dangerous and not confirmed:
        if tool.is_extra_dangerous and tool.is_extra_dangerous(args["command"]):
            return f"[CONFIRM_REQUIRED] 危险命令: {args['command']}"

    # Layer 2: 普通危险命令检查
    if tool.dangerous and not confirmed:
        # ... 原有检查逻辑
```

### 7.4 SSRF 保护

fetch 工具需要防止访问内网地址（SSRF 攻击）：

```python
BLOCKED_HOSTS = {
    '169.254.169.254',  # AWS/GCP/Azure 元数据端点
    'metadata.google.internal',
    'localhost', '127.0.0.1', '0.0.0.0',
    '::1',
}

def fetch_handler(url: str) -> str:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    if hostname.lower() in BLOCKED_HOSTS or hostname.startswith(('10.', '172.16.', '192.168.')):
        return "Error: access to internal/private addresses is blocked"
    # ... 正常请求
```

**关键认知**：安全不是"全部确认"或"全部放行"，而是分层次、按风险等级处理。只读操作应该零摩擦，危险操作才需要确认。

---

## 八、HIGH：API 调用超时

### 8.1 问题

原始代码没有整体超时。如果 API 挂起，Agent 会无限等待。

### 8.2 双重超时机制

```python
def _chat_once(self, messages, tools, cancel_event=None, timeout=120.0):
    import httpx

    # 超时 1：httpx 连接级超时
    client = anthropic.Anthropic(
        api_key=self.api_key,
        base_url=self.base_url,
        timeout=httpx.Timeout(timeout, connect=10.0)
    )

    # 超时 2：轮询级超时兜底
    start_time = time.monotonic()
    while api_thread.is_alive():
        if time.monotonic() - start_time > timeout + 10:
            raise LLMError(f"API 请求超时 ({timeout}s)")
        api_thread.join(timeout=0.1)
```

为什么需要两层？httpx 超时控制单次 HTTP 请求，但 SDK 内部可能有重试逻辑。轮询级超时是最终兜底。

**关键认知**：任何可能无限等待的操作都需要超时。超时值的选择要平衡——太短会误杀正常请求，太长会浪费用户时间。120 秒是 Anthropic 官方推荐的默认值。

---

## 九、HIGH：中断后状态清理

### 9.1 问题

用户按 Ctrl+C 中断时，Agent 可能处于以下状态之一：
- `_pending_confirm` 有值（等待用户确认危险操作）
- `_pending_response` 有值（保存了 LLM 的完整 tool_use 响应）
- `_confirmed_results` 有值（已确认但未写入上下文的工具结果）

如果不清除这些状态，下次用户输入时，Agent 会误以为还有待确认的操作。

### 9.2 修复

在 TUI 层捕获 KeyboardInterrupt 和通用 Exception，清理 Agent 状态：

```python
try:
    response = agent.run(user_input, cancel_event=cancel_event, confirmed_tools=confirmed_tools)
except KeyboardInterrupt:
    agent._pending_confirm = None
    agent._pending_response = None
    agent._confirmed_results = []
    response = "[中断] 请求被用户取消"
except Exception as e:
    agent._pending_confirm = None
    agent._pending_response = None
    agent._confirmed_results = []
    response = f"[错误] {type(e).__name__}: {e}"
```

**关键认知**：中断不是异常，是正常的用户操作。Agent 必须能从中断中干净地恢复，而不是留下残留状态导致后续行为异常。

---

## 十、健壮性设计原则总结

从这 8 个修复中，可以提炼出 Agent 健壮性的核心原则：

### 原则 1：协议合规先于功能

Anthropic API 的每条规则都有原因。tool_result 合并、配对完整性——违反任何一条都会导致 400 错误。**先确保协议合规，再追求功能。**

### 原则 2：所有分支都必须有出口

Agent 循环中的每个 stop_reason 都必须有明确的处理。未处理的分支 = 潜在的无限循环。**用 default 分支兜底，而不是假设"不会发生"。**

### 原则 3：跨调用状态用实例属性

当状态需要跨越多次方法调用（如 run → confirm_pending）时，局部变量会丢失。**凡是需要跨调用保存的，都是实例属性的候选。**

### 原则 4：防御性截断优于事后裁剪

在工具执行阶段截断输出，比在上下文管理阶段裁剪消息更高效。**截断保留部分信息，裁剪丢失全部信息。**

### 原则 5：安全分层而非一刀切

不是所有操作都需要确认。只读操作零摩擦，危险操作按等级确认。**安全的目标是阻止危险操作，不是阻碍正常操作。**

### 原则 6：超时是必须的

任何可能无限等待的操作——API 调用、工具执行、重试等待——都需要超时。**没有超时的等待，就是潜在的死锁。**

### 原则 7：中断是正常操作

用户中断不是异常情况，Agent 必须能从中断中干净恢复。**中断后的残留状态，比中断本身更危险。**

---

## 附录

### A. 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `agent/context.py` | add_tool_results 批量方法、_trim 配对完整性 |
| `agent/loop.py` | max_tokens 处理、_confirmed_results 跨调用保存 |
| `agent/adapter.py` | exponential backoff + jitter、cancel_aware_sleep、httpx 超时 |
| `agent/builtin_tools.py` | _truncate 截断、只读白名单、额外危险检测、SSRF 保护 |
| `agent/tools.py` | is_readonly/is_extra_dangerous 回调、三层安全模型 |
| `tui_core.py` | KeyboardInterrupt/Exception 状态清理 |

### B. 测试覆盖

每个修复都添加了对应的单元测试：

| 测试 | 验证内容 |
|------|---------|
| `test_agent_run_max_tokens_stop_reason` | max_tokens 不循环，只调用一次 LLM |
| `test_agent_confirm_pending_with_confirmed_results` | 混合确认场景，两个 tool_result 都写入上下文 |
| 原有 28 个测试 | 所有修改不破坏已有功能 |

### C. 参考项目

| 项目 | 借鉴内容 |
|------|---------|
| Claude Code | streaming + tool confirmation + robust error recovery |
| OpenCode | retry 8 次 + exponential backoff + jitter + Retry-After |
| OpenCode | bash 输出截断 30000 chars + banned commands + read-only allowlist |
| OpenCode | panic recovery at all goroutine boundaries |