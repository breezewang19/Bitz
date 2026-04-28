# 04 — TUI 开发实战：从纯 ANSI 到组件化界面

> 前置：[03-agent-robustness-engineering.md](03-agent-robustness-engineering.md) — 健壮性增强

上一篇我们让 Agent 从"能跑"变成了"能稳定跑"。但终端界面还是原始的 `print()` + ANSI 转义序列。本文记录 Bitz 从纯 ANSI 迁移到 Textual 框架的全过程，以及后续的美观性和体验增强。

---

## 一、为什么要迁移到 Textual

### 1.1 纯 ANSI 的局限

| 问题 | 原因 |
|------|------|
| 平台差异大 | msvcrt vs termios，输入处理完全不同 |
| 无法组件化 | 所有渲染逻辑混在主循环里 |
| 动画靠 sleep | thinking 转圈用 `time.sleep` 阻塞主线程 |
| 确认靠 input() | 危险操作确认阻塞整个界面 |
| 无状态管理 | 繁忙/空闲、确认/正常全靠全局变量 |

### 1.2 Textual 的核心特性

- **组件化**：Widget 体系，每个 UI 元素是独立对象
- **异步事件循环**：基于 asyncio，动画不阻塞
- **CSS 样式**：用 CSS 控制布局和外观
- **跨平台**：统一输入处理，不再需要 tui_win/tui_mac
- **Rich 集成**：直接使用 Rich Text 做富文本渲染

---

## 二、架构与模块划分

```
tui/
├── app.py          # 主应用（Agent 集成 + 确认流程 + 动画控制）
├── theme.py        # 主题配色 + 全局 CSS
└── widgets/
    ├── banner.py   # 启动动画（彩虹猫 + 边框 + 眨眼 + 打字机）
    ├── chat.py     # 聊天面板（消息 + 思考指示器 + 工具调用）
    ├── confirm.py  # 内联确认提示（y/n 批准/拒绝）
    ├── input.py    # 输入栏（TextArea 多行 + 历史 + 命令补全）
    └── status.py   # 状态栏（模型名 + 步数 + token + CWD）
```

组件关系：

```
BitzApp
├── ChatLog (VerticalScroll)
│   ├── UserMessage / AssistantMessage(Markdown) / ToolCard(Collapsible)
│   ├── ThinkingIndicator (思考/工具运行/取消 三态)
│   └── ConfirmPrompt (确认时挂载，用户选择后移除)
├── StatusBar
└── InputBar
    ├── MessageInput (TextArea, Enter 发送, Shift+Enter 换行)
    └── CommandPopup (斜杠命令补全)
```

---

## 三、核心挑战与解决方案

### 3.1 线程安全：Agent 在 executor 中运行，UI 在主线程

Agent 的 `run()` 在 `loop.run_in_executor` 中执行，工具回调在 executor 线程。**跨线程 UI 更新必须用 `call_from_thread`，直接操作 Widget 会崩溃。**

```python
def _install_tool_logger(self):
    original = self._original_execute
    app = self

    def logged_execute(name, args, confirmed=False, tool_id=None):
        app._post_tool_call(name, content)      # call_from_thread
        app._set_tool_running(name)              # call_from_thread
        try:
            result = original(name, args, confirmed=confirmed, tool_id=tool_id)
        finally:
            app._set_tool_running(None)          # call_from_thread
        return result

    self._agent.tools.execute = logged_execute
```

### 3.2 异步确认：不用 ModalScreen，用 asyncio.Future

ModalScreen 的 `push_screen_wait` 会阻塞主线程事件循环，与 executor 线程配合时产生死锁。**asyncio.Future 是异步等待的正确原语。**

```python
async def _show_confirm_inline(self, tool_name, tool_args):
    prompt = ConfirmPrompt(tool_name, tool_args)
    self._confirm_prompt = prompt
    self._confirm_result = asyncio.get_event_loop().create_future()
    chat.mount(prompt)
    result = await self._confirm_result  # 非阻塞等待
    return result
```

### 3.3 ThinkingIndicator 三态切换

工具调用发生在"思考"期间，ThinkingIndicator 应切换到"运行工具"状态，而不是被移除。只有当助手最终回复时才移除。

状态切换：`show_thinking()` → `set_tool_running(name)` → `set_canceling()` → `hide_thinking()`

### 3.4 动画任务累积 Bug

每次 Agent 循环开始时调用 `_start_thinking_animation()`，如果上一轮的动画任务没取消，就会同时运行多个动画循环——转圈速度翻倍。**每次创建新 Task 前，必须显式取消旧的。**

```python
def _start_thinking_animation(self):
    self._thinking_task = asyncio.create_task(self._thinking_animation_loop())

def _stop_thinking_animation(self):
    if self._thinking_task is not None:
        self._thinking_task.cancel()
        self._thinking_task = None
```

### 3.5 确认是暂停点，不是终点

用户确认后，Agent 可能继续调用工具。确认流程必须支持 `continue`，拒绝时也要写入 tool_result 保持上下文配对完整性（Anthropic 协议要求 tool_use 和 tool_result 严格配对）。

---

## 四、美观性增强

### 4.1 Markdown 渲染

LLM 返回的文本天然包含 Markdown。用 Textual 内置 `Markdown` 组件做语法高亮。`AssistantMessage` 继承 `Static` 做容器控制布局，内嵌 `Markdown` 做渲染——"容器-内容"模式。

### 4.2 ToolCard 可折叠卡片

用 `Collapsible` 组件实现工具调用卡片。状态图标（⟳/✓/✗）+ 折叠/展开 + 输出截断。成功默认折叠，错误和 diff 默认展开。`Collapsible.collapsed` 是 reactive 属性，赋值即更新。

### 4.3 主题系统

用 Textual 3.x 的 `Theme` 数据类 + `register_theme()` + CSS 变量 `$var`。三套主题：Dracula dark / Light / Nord。`/theme` 命令切换，`COLORFGBG` 环境变量自动检测明暗。

### 4.4 状态栏与计时

StatusBar 显示模型名、步数、累积 token（从 `adapter._last_usage` 读取）、CWD。ThinkingIndicator 实时计时 + TurnTiming 持久汇总。

---

## 五、体验增强

### 5.1 斜杠命令与补全

输入 `/` 开头时发送 `CommandSubmitted` 消息（而非 `MessageSubmitted`），BitzApp 按命令名分发。`CommandPopup` 弹出列表自动过滤，Tab 补全，上下键导航，ESC 关闭。

可用命令：`/help`、`/clear`、`/compact`、`/theme [name]`

### 5.2 多行输入

`MessageInput(TextArea)` 替换 `Input`。Enter 发送消息，Shift+Enter 插入换行。CSS `height: auto` + `max-height: 7` 实现自适应高度。

### 5.3 代码 diff 视图

在 `_install_tool_logger` 的 monkey-patch 中，执行 `edit_file`/`write_file` 前读取原文件，执行后用 `difflib.unified_diff` 生成 diff，`rich.syntax.Syntax(lexer="diff")` 渲染高亮。diff 默认展开。

### 5.4 鼠标支持

Textual 默认启用鼠标，无需代码。滚轮滚动、点击折叠/展开、光标定位自动工作。

---

## 六、设计原则总结

| 原则 | 说明 |
|------|------|
| 线程边界是硬边界 | 跨线程 UI 操作必须 `call_from_thread` |
| 异步等待用 Future | 与 executor 配合时，Future 不阻塞事件循环 |
| 动画任务必须显式管理 | 每次创建新 Task 前，必须取消旧任务 |
| render() 必须安全返回 | 不依赖 on_mount 中初始化的值 |
| 工具调用是"思考中"的子状态 | ThinkingIndicator 切换而非移除 |
| 确认是暂停点不是终点 | 支持 continue，拒绝时写入 tool_result |
| 消息机制是组件间通信标准 | InputBar 只分发，BitzApp 只处理 |
| 用框架原生能力 | Theme、Markdown、Collapsible、鼠标都是现成的 |
| monkey-patch 最小侵入 | 不改 agent/ 接口，只扩展 tool logger |
