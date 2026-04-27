# Textual TUI 开发实战：从纯 ANSI 到组件化界面

## 前言

上一篇我们让 Agent 从"能跑"变成了"能稳定跑"。但终端界面还是原始的 `print()` + ANSI 转义序列——没有组件化、没有状态管理、没有动画框架。

本文记录 Bitz 项目从纯 ANSI TUI 迁移到 Textual 框架的全过程。重点不是 Textual 的 API 用法，而是迁移中遇到的真实问题：线程安全、异步确认、动画状态机、工具调用拦截——每一个都是"能跑"和"好用"之间的鸿沟。

**前置知识**：阅读过 02（最小 Agent 循环）和 03（健壮性增强），理解 Agent 的运行流程。

---

## 一、为什么要迁移

### 1.1 纯 ANSI 的局限

原始 TUI 由三个文件组成：

```
tui_core.py  — 共性逻辑（颜色、banner、动画、输出、主循环）
tui_win.py   — Windows 兼容层（msvcrt 输入 + 粘贴检测）
tui_mac.py   — macOS/Linux 兼容层（termios 输入）
```

核心问题：

| 问题 | 原因 |
|------|------|
| 平台差异大 | msvcrt vs termios，输入处理完全不同 |
| 无法组件化 | 所有渲染逻辑混在主循环里 |
| 动画靠 sleep | thinking 转圈用 `time.sleep` 阻塞主线程 |
| 确认靠 input() | 危险操作确认阻塞整个界面 |
| 无状态管理 | 繁忙/空闲、确认/正常全靠全局变量 |

### 1.2 为什么选 Textual

Textual 是 Python 的现代 TUI 框架，核心特性：

- **组件化**：Widget 体系，每个 UI 元素是独立对象
- **异步事件循环**：基于 asyncio，动画不阻塞
- **CSS 样式**：用 CSS 控制布局和外观
- **跨平台**：统一输入处理，不再需要 tui_win/tui_mac
- **Rich 集成**：直接使用 Rich Text 做富文本渲染

---

## 二、架构设计

### 2.1 模块划分

```
tui/
├── __init__.py     # 懒加载入口
├── app.py          # 主应用（Agent 集成 + 确认流程 + 动画控制）
├── theme.py        # 主题配色 + 全局 CSS
└── widgets/
    ├── __init__.py
    ├── banner.py   # 启动动画（彩虹猫 + 边框 + 眨眼 + 打字机）
    ├── chat.py     # 聊天面板（消息 + 思考指示器 + 工具调用）
    ├── confirm.py  # 内联确认提示（y/n 批准/拒绝）
    ├── input.py    # 输入栏（历史 + 繁忙状态）
    └── status.py   # 状态栏（模型名 + 步数）
```

设计原则：**每个 Widget 一个文件，职责单一，通过 Message 通信**。

### 2.2 组件关系

```
BitzApp
├── ChatLog (VerticalScroll)
│   ├── BannerWidget (启动时挂载，动画完成后发 BannerDone)
│   ├── UserMessage / AssistantMessage / ToolMessage
│   ├── ThinkingIndicator (思考/工具运行/取消 三态)
│   └── ConfirmPrompt (确认时挂载，用户选择后移除)
├── StatusBar
└── InputBar
    └── Input
```

### 2.3 入口兼容

保留旧版 TUI，通过 `--legacy` 参数切换：

```python
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy", action="store_true")
    args, _ = parser.parse_known_args()

    if args.legacy:
        # 旧版纯 ANSI TUI
        from tui_win import main as legacy_main
        legacy_main()
    else:
        # 新版 Textual TUI
        app = BitzApp(agent=agent)
        app.run()
```

---

## 三、核心挑战与解决方案

### 3.1 线程安全：Agent 在 executor 中运行，UI 在主线程

**问题**：Agent 的 `run()` 方法在 `loop.run_in_executor` 中执行（阻塞调用），而 Textual 的 UI 更新必须在主线程。工具执行时需要实时更新 UI（显示工具名、转圈动画），但工具回调在 executor 线程。

**解决**：`call_from_thread()` + monkey-patch。

```python
def _install_tool_logger(self):
    """Monkey-patch tools.execute to log tool calls to UI."""
    original = self._original_execute
    app = self

    def logged_execute(name, args, confirmed=False, tool_id=None):
        content = format_tool_content(name, args)
        app._post_tool_call(name, content)      # call_from_thread
        app._set_tool_running(name)              # call_from_thread
        try:
            result = original(name, args, confirmed=confirmed, tool_id=tool_id)
        finally:
            app._set_tool_running(None)          # call_from_thread
        return result

    self._agent.tools.execute = logged_execute
```

关键认知：**跨线程 UI 更新必须用 `call_from_thread`，直接操作 Widget 会崩溃。** `try/finally` 确保即使工具执行失败，UI 状态也能恢复。

### 3.2 异步确认：不用 ModalScreen，用 asyncio.Future

**问题**：Agent 循环在 executor 线程中运行，需要等待用户确认。如果用 Textual 的 `push_screen_wait`，会阻塞主线程的事件循环——而 executor 线程还在等结果，死锁。

**解决**：内联 ConfirmPrompt + asyncio.Future。

```python
async def _show_confirm_inline(self, tool_name, tool_args):
    """在 ChatLog 中挂载确认提示，等待用户 y/n。"""
    prompt = ConfirmPrompt(tool_name, tool_args)
    self._confirm_prompt = prompt
    self._confirm_result = asyncio.get_event_loop().create_future()

    chat.mount(prompt)
    bar._input.placeholder = "y/n?"
    bar._input.focus()

    result = await self._confirm_result  # 非阻塞等待
    return result
```

用户按 y/n/Enter/Escape 时，`on_key` 处理器调用 `_resolve_confirm()`，设置 Future 的结果：

```python
def _resolve_confirm(self, approved: bool):
    if self._confirm_result and not self._confirm_result.done():
        self._confirm_result.set_result(approved)
    if self._confirm_prompt:
        self._confirm_prompt.remove()
        self._confirm_prompt = None
    self._confirm_result = None
```

关键认知：**ModalScreen 适合纯 UI 交互，但与 executor 线程配合时会产生死锁。asyncio.Future 是异步等待的正确原语。**

### 3.3 ThinkingIndicator 三态切换

**问题**：Agent 运行时有三种状态需要显示——思考中、工具运行中、取消中。原始实现只有"思考"一种状态。

**解决**：ThinkingIndicator 内部维护 `_tool_name` 和 `_canceling` 两个状态变量：

```python
class ThinkingIndicator(Static):
    def render(self) -> Text:
        frame = self.SPINNER_FRAMES[self._frame % len(self.SPINNER_FRAMES)]
        if self._canceling:
            return Text.assemble(
                Text(f"{frame} ", style=COLORS["error"]),
                Text("[ESC] Canceling", style=COLORS["error"]),
            )
        if self._tool_name:
            return Text.assemble(
                Text(f"{frame} ", style=COLORS["tool"]),
                Text(f"Running ", style=COLORS["tool"]),
                Text(f"[{self._tool_name}]", style=f"bold {COLORS['tool']}"),
            )
        return Text.assemble(
            Text(f"{frame} ", style=COLORS["thinking"]),
            Text("Thinking", style=COLORS["thinking"]),
        )
```

状态切换时机：
- `show_thinking()` → 挂载 ThinkingIndicator（默认"思考"状态）
- `set_tool_running(name)` → 切换到"运行 [工具名]"状态
- `set_tool_running(None)` → 切回"思考"状态
- `set_canceling()` → 切换到"取消中"状态
- `hide_thinking()` → 移除 ThinkingIndicator

关键认知：**工具调用发生在"思考"期间，不应该隐藏 ThinkingIndicator。** 只有当助手最终回复时才移除。原始代码在 `add_message` 中不区分角色就移除，导致工具调用时转圈消失。

### 3.4 动画状态机：BannerWidget 四阶段

**问题**：启动动画需要依次展示：彩虹猫逐字显现 → Welcome 打字机效果 → 眨眼动画 → 完成。每个阶段的推进逻辑不同。

**解决**：用 `_phase` 变量实现简单状态机：

```python
def _advance(self):
    if self._phase == "cat":
        self._lit += 2
        if self._lit > self._max_lit + 2:
            self._phase = "welcome"
        self._render_frame()
    elif self._phase == "welcome":
        self._welcome_idx += 1
        if self._welcome_idx > len(WELCOME_TEXT):
            self._phase = "blink"
        self._render_frame()
    elif self._phase == "blink":
        self._blink_count += 1
        if self._blink_count > 6:
            self._phase = "done"
            self._finish()
            return
        self._blink_state = not self._blink_state
        self._render_frame()
```

渲染函数根据 `_phase` 决定显示内容：

- **cat 阶段**：未显示的字符用 `dim` 样式，已显示的用 `bold` 彩虹色
- **welcome 阶段**：Welcome 文字逐字出现，末尾带光标 `▌`
- **blink 阶段**：猫眼在 `o` 和 `-` 之间交替
- **done 阶段**：调用 `_finish()` 渲染最终静态画面，发送 `BannerDone` 消息

关键认知：**动画状态机不需要复杂框架，一个字符串变量 + if/elif 就够了。** 复杂度在于渲染逻辑，而非状态管理。

### 3.5 动画任务累积 Bug

**问题**：每次 Agent 循环开始时调用 `_start_thinking_animation()`，但如果上一轮的动画任务没取消，就会同时运行两个动画循环——转圈速度翻倍。多轮对话后越来越快。

**解决**：每次启动前先停止：

```python
def _start_thinking_animation(self):
    self._thinking_task = asyncio.create_task(self._thinking_animation_loop())

def _stop_thinking_animation(self):
    if self._thinking_task is not None:
        self._thinking_task.cancel()
        self._thinking_task = None
```

在 `_agent_loop` 中，每次循环开始时先 stop 再 start：

```python
while True:
    self._stop_thinking_animation()   # 先停
    chat.show_thinking()
    self._start_thinking_animation()  # 再启
    # ...
```

关键认知：**asyncio.Task 不会自动取消。** 每次创建新 Task 前，必须显式取消旧的。这个 Bug 的特征是"越来越快"——典型的多任务并行症状。

---

## 四、视觉还原：从 ANSI 到 Rich Text

### 4.1 用户消息

原始 ANSI：
```python
print(f"\033[48;5;17m\033[38;5;82m> {content}\033[0m")
```

Textual + Rich：
```python
class UserMessage(Static):
    DEFAULT_CSS = """
    UserMessage {
        background: #1a1a2e;
        color: #50fa7b;
        margin: 0 0 1 0;
        padding: 0 1;
    }
    """
    def render(self) -> Text:
        return Text.assemble(
            Text("> ", style=f"bold {COLORS['user']}"),
            Text(self._content, style=COLORS['user']),
        )
```

### 4.2 工具调用

原始 ANSI：
```python
print(f"\033[1m\033[38;5;177m[{name}]\033[0m \033[38;5;177m{content}\033[0m")
```

Textual + Rich：
```python
class ToolMessage(Static):
    def render(self) -> Text:
        return Text.assemble(
            Text(f"[{self._tool_name}]", style=f"bold {COLORS['tool']}"),
            Text(f" {self._content}", style=COLORS['tool']),
        )
```

### 4.3 彩虹猫边框

用 Unicode box-drawing 字符绘制圆角边框：

```python
def _make_border_top(inner_w: int) -> Text:
    return Text(f"  ╭{'─' * inner_w}╮", style=BORDER_COLOR)

def _make_border_bottom(inner_w: int) -> Text:
    return Text(f"  ╰{'─' * inner_w}╯", style=BORDER_COLOR)

def _make_row(content: str, inner_w: int) -> Text:
    pad = inner_w - len(content)
    return Text.assemble(
        Text("  │", style=BORDER_COLOR),
        Text(content),
        Text(" " * max(pad, 0)),
        Text("│", style=BORDER_COLOR),
    )
```

边框宽度计算：`inner_w = max(最长猫行, Welcome文字长度) + 2`，保证内容不溢出。

关键认知：**Unicode 字符的显示宽度不等于字符数。** 中文字符占 2 列，但 `len()` 返回 1。边框宽度计算时必须用显示宽度而非字符长度。Bitz 的猫和 Welcome 都是 ASCII，所以暂时没问题，但 `_make_row` 的 `len(content)` 在未来支持中文时需要替换为显示宽度计算。

---

## 五、ConfirmPrompt：从 ModalScreen 到内联组件

### 5.1 为什么不用 ModalScreen

ModalScreen 是 Textual 的标准弹窗方案，但有两个问题：

1. **与 executor 死锁**：`push_screen_wait` 阻塞主线程事件循环，而 executor 线程在等确认结果
2. **视觉不协调**：全屏弹窗打断聊天流，Claude Code 的确认是内联的

### 5.2 内联方案

ConfirmPrompt 是一个普通 Static Widget，挂载到 ChatLog 中：

```python
class ConfirmPrompt(Static):
    def __init__(self, tool_name: str, tool_args: str = ""):
        super().__init__()
        self._tool_name = tool_name
        self._tool_args = tool_args
        self._selected = 1  # 0=deny, 1=allow

    def render(self) -> Text:
        # 显示工具名、参数、批准/拒绝选项
        ...
```

交互通过 App 层的 `on_key` 处理：

```python
def on_key(self, event: Key):
    if self._confirm_prompt is not None:
        if event.key == "y":
            self._resolve_confirm(True)
        elif event.key == "n":
            self._resolve_confirm(False)
        elif event.key == "left":
            self._confirm_prompt.select_deny()
        elif event.key == "right":
            self._confirm_prompt.select_allow()
        elif event.key == "enter":
            self._resolve_confirm(self._confirm_prompt.selected)
        elif event.key == "escape":
            self._resolve_confirm(False)
```

### 5.3 ConfirmPrompt 的 NoneType 崩溃

**问题**：最初 ConfirmPrompt 在 `on_mount` 中调用 `self.update(content)`，但 Textual 的 `Static._render()` 在 `on_mount` 之前被调用，返回 None 导致崩溃。

**解决**：重写 `render()` 方法，直接返回 Text 对象，不依赖 `update()`：

```python
# 错误：on_mount 中 update，_render 可能在之前调用
def on_mount(self):
    self.update(self._build_content())

# 正确：重写 render，始终返回有效 Text
def render(self) -> Text:
    return self._build_content()
```

关键认知：**Textual 的 Widget 生命周期是 mount → mounted → compose → 等等，但 `_render` 可能在任何时刻被调用。** 如果渲染依赖 `on_mount` 中设置的值，必须确保 `render()` 在 `on_mount` 之前也能安全返回。

---

## 六、Agent 循环集成

### 6.1 确认后继续循环

Agent 循环中，确认批准后可能需要继续（LLM 还有后续工具调用）。原始代码在确认后直接返回，导致后续工具调用丢失。

```python
async def _agent_loop(self, user_input: str):
    while True:
        result = await loop.run_in_executor(None, self._agent.run, ...)

        if result.startswith("[CONFIRM_REQUIRED]"):
            approved = await self._show_confirm_inline(tool_name, tool_args)
            if approved:
                should_continue, exec_result = await loop.run_in_executor(
                    None, self._agent.confirm_pending, self._confirmed_tools,
                )
                if should_continue:
                    # 继续循环——Agent 会获取下一个响应
                    user_input = ""
                    skip_add_user = True
                    bar.set_busy(True)
                    continue        # ← 关键：不是 return
                else:
                    self._process_agent_result(exec_result)
                    bar.set_busy(False)
                    return
```

关键认知：**确认不是循环的终点，而是循环中的一个暂停点。** 批准后 Agent 可能继续调用工具，必须 `continue` 而非 `return`。

### 6.2 确认拒绝的上下文修复

拒绝确认时，必须向上下文中写入拒绝的 tool_result，否则 API 会因为缺少 tool_result 而报错：

```python
if not approved:
    self._agent.context.add_assistant_message([{
        "type": "tool_use",
        "id": tool_id,
        "name": tname,
        "input": targs,
    }])
    self._agent.context.add_tool_result(tool_id, "[已拒绝] 用户拒绝了此危险操作")
```

关键认知：**Anthropic 协议要求 tool_use 和 tool_result 严格配对。** 即使拒绝了工具执行，也必须写入一个 tool_result，否则下一轮 API 调用会报 400。

---

## 七、Textual TUI 设计原则总结

### 原则 1：线程边界是硬边界

Agent 运行在 executor 线程，UI 运行在主线程。**任何跨线程的 UI 操作都必须通过 `call_from_thread`。** 直接操作 Widget 是未定义行为——可能工作，可能崩溃，可能只在特定时序下崩溃。

### 原则 2：异步等待用 Future，不用 Screen

ModalScreen 的 `push_screen_wait` 会阻塞事件循环。**与 executor 配合时，asyncio.Future 是唯一安全的等待原语。** Future 不阻塞事件循环，其他事件（动画、按键）正常处理。

### 原则 3：动画任务必须显式管理

asyncio.Task 不会自动取消。**每次创建新动画任务前，必须取消旧任务。** "越来越快"是典型的多任务并行症状——不是动画加速了，而是多个动画同时运行。

### 原则 4：render() 必须在任何时刻安全返回

Textual 可能在 Widget 生命周期的任何时刻调用 `render()`。**不要让 render() 依赖 on_mount 中初始化的值。** 如果必须依赖，提供默认值确保安全。

### 原则 5：工具调用是"思考中"的子状态

工具调用发生在 LLM 思考期间。**ThinkingIndicator 应该切换到"运行工具"状态，而不是被移除。** 只有当助手最终回复时才移除 ThinkingIndicator。

### 原则 6：确认是暂停点，不是终点

用户确认后，Agent 可能继续调用工具。**确认流程必须支持 continue，而不是总是 return。** 拒绝确认时也要写入 tool_result，保持上下文配对完整性。

### 原则 7：边框宽度用显示宽度，不是字符数

Unicode 字符（尤其是 CJK）的显示宽度可能不等于 `len()` 的返回值。**边框和 padding 计算必须基于显示宽度。** 当前代码假设 ASCII，未来支持中文时需要替换 `len()` 为显示宽度计算。

---

## 附录

### A. 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `tui.py` | 重写入口，默认 Textual，`--legacy` 切换旧版 |
| `tui/__init__.py` | 新增，懒加载 BitzApp |
| `tui/app.py` | 新增，主应用（Agent 集成 + 确认流程 + 动画控制） |
| `tui/theme.py` | 新增，Dracula 配色 + 全局 CSS |
| `tui/widgets/banner.py` | 新增，四阶段启动动画 |
| `tui/widgets/chat.py` | 新增，聊天面板 + 消息 + 思考指示器 + 工具调用 |
| `tui/widgets/confirm.py` | 新增，内联确认提示 |
| `tui/widgets/input.py` | 新增，输入栏 + 历史记录 + 繁忙状态 |
| `tui/widgets/status.py` | 新增，状态栏 |
| `requirements.txt` | 新增 textual>=3.0,<4.0 |

### B. 测试覆盖

| 测试文件 | 覆盖内容 |
|---------|---------|
| `test_tui_chat.py` | UserMessage/AssistantMessage/ToolMessage 渲染、ThinkingIndicator 三态、ChatLog 消息管理 |
| `test_tui_confirm.py` | ConfirmPrompt 显示工具信息、批准/拒绝切换、默认选择 |
| `test_tui_input.py` | InputBar 消息提交、历史导航、繁忙状态 |
| `test_tui_status.py` | StatusBar 模型名/步数更新 |
| `test_tui_app.py` | BitzApp 组合、Banner 挂载 |
| `test_tui_integration.py` | 确认流程端到端 |

### C. 从 ANSI 到 Textual 的映射

| ANSI 方式 | Textual 方式 |
|-----------|-------------|
| `print("\033[1m...")` | `Text("...", style="bold")` |
| `time.sleep` + 循环 | `set_interval` / `asyncio.create_task` |
| `input()` | `Input` Widget + `MessageSubmitted` |
| 全局变量状态 | Widget 属性 + Message 通信 |
| `msvcrt` / `termios` | Textual 统一输入处理 |
| 手动 `sys.stdout.write` | `self.update()` / `render()` |

### D. 参考项目

| 项目 | 借鉴内容 |
|------|---------|
| Claude Code | 内联确认提示设计、工具调用显示格式 |
| Textual 官方文档 | Widget 生命周期、call_from_thread、async 集成 |
