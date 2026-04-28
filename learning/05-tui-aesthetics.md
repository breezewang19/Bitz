# 05 — TUI 美观性：Markdown、工具卡片、主题与状态增强

> 前置：[04-tui-with-textual.md](04-tui-with-textual.md) — 基础 TUI 布局与交互

上一章我们搭建了稳定的 TUI 骨架：ChatLog + InputBar + StatusBar + 确认流程。但输出都是纯文本，没有格式化；工具调用混在聊天流里，难以区分；主题硬编码，无法切换。

本章我们给 Bitz 加上"面子工程"——五个独立的视觉增强功能，每个都对应一个 Textual 的核心能力。

---

## 5.1 Markdown 渲染

### 问题

LLM 返回的文本天然包含 Markdown（标题、代码块、列表、粗体），但 `Static` 只能显示纯文本。代码块没有语法高亮，表格对不齐，标题和正文一样大。

### 方案：Textual 的 Markdown 组件

Textual 内置 `textual.widgets.Markdown`，基于 Pygments 做语法高亮，开箱即用：

```python
from textual.widgets import Markdown as MarkdownWidget

class AssistantMessage(Static):
    def __init__(self, content: str) -> None:
        super().__init__()
        self._content = content

    def compose(self):
        yield MarkdownWidget(self._content)

    def update_content(self, text: str) -> None:
        """流式更新（为未来 streaming 预留）"""
        md = self.query_one(MarkdownWidget)
        md.update(text)
```

### 关键设计决策

**为什么 `AssistantMessage` 仍然继承 `Static` 而不是直接用 `Markdown`？**

因为 `Markdown` 的样式控制有限。用 `Static` 做容器，`Markdown` 做子组件，可以在 `Static` 的 `DEFAULT_CSS` 里控制外边距、内边距、颜色等，而 `Markdown` 只负责渲染内容。这是 Textual 的"容器-内容"模式。

**用户消息为什么不用 Markdown？**

用户输入通常很短（一行命令或问题），不需要 Markdown 渲染。保持 `Static` 更轻量。

---

## 5.2 Tool Call 卡片

### 问题

工具调用和结果混在聊天流里，跟 assistant 消息难以区分。运行中的工具没有视觉反馈，成功/失败状态不直观。

### 方案：Collapsible + 状态图标

Textual 的 `Collapsible` 组件可以折叠/展开内容，正好适合工具输出——默认折叠，点击展开看详情。

```python
from textual.widgets import Collapsible

class ToolCard(Static):
    """可折叠的工具调用卡片，带状态图标。"""

    def __init__(self, tool_name: str, args_summary: str = "") -> None:
        super().__init__()
        self._tool_name = tool_name
        self._args_summary = args_summary[:60]  # 截断长参数
        self._status = "running"  # running | success | error
        self._collapsible: Collapsible | None = None
        self._output_widget: Static | None = None

    def compose(self):
        label = self._make_label()
        self._output_widget = Static("", classes="tool-output")
        self._collapsible = Collapsible(
            self._output_widget, title=label, collapsed=False
        )
        yield self._collapsible
```

### 状态图标与折叠逻辑

```python
def _make_label(self) -> str:
    icons = {"running": "⟳", "success": "✓", "error": "✗"}
    icon = icons.get(self._status, "⟳")
    if self._args_summary:
        return f"{icon} {self._tool_name}: {self._args_summary}"
    return f"{icon} {self._tool_name}"

def set_success(self, output: str = "") -> None:
    self._status = "success"
    self._update_label()
    # 输出截断到 500 字符
    if self._output_widget and output:
        display = output if len(output) <= 500 else output[:497] + "..."
        self._output_widget.update(display)
    self._collapsible.collapsed = True   # 成功 → 折叠

def set_error(self, output: str = "") -> None:
    self._status = "error"
    self._update_label()
    if self._output_widget and output:
        display = output if len(output) <= 500 else output[:497] + "..."
        self._output_widget.update(display)
    self._collapsible.collapsed = False  # 错误 → 展开
```

### Textual 的 Reactive 属性

`Collapsible.collapsed` 和 `Collapsible.title` 都是 **reactive 属性**——赋值后自动触发 UI 更新，不需要手动刷新。这是 Textual 的核心机制之一：

```python
# 这一行就够了，不需要 refresh() 或重绘
self._collapsible.collapsed = True
```

### 集成到 BitzApp

在 `_install_tool_logger` 的 monkey-patch 中，工具执行后更新 ToolCard 状态：

```python
def logged_execute(name, args, confirmed=False, tool_id=None):
    content = format_tool_content(name, args if isinstance(args, dict) else {})
    app._post_tool_call(name, content)      # 创建 ToolCard
    app._set_tool_running(name)
    try:
        result = original(name, args, confirmed=confirmed, tool_id=tool_id)
        is_error = result.startswith("Error") or result.startswith("[CONFIRM_REQUIRED]")
        app._post_tool_result(name, result, is_error)  # 更新 ToolCard 状态
    finally:
        app._set_tool_running(None)
    return result
```

线程安全的关键：`_post_tool_result` 通过 `call_from_thread` 把 UI 更新调度到主线程：

```python
def _post_tool_result(self, tool_name: str, result: str, is_error: bool) -> None:
    try:
        self.call_from_thread(self._update_tool_result, tool_name, result, is_error)
    except Exception:
        pass
```

---

## 5.3 主题系统

### 问题

颜色全部硬编码在 `theme.py` 的 `COLORS` 字典里。暗色终端下好看，亮色终端下看不清。无法切换主题。

### 方案：Textual 原生 Theme 类

Textual 3.x 提供了 `Theme` 数据类，配合 `register_theme()` 和 `app.theme` 属性，可以零代码切换整个应用的颜色方案：

```python
from textual.theme import Theme

BITZ_THEMES = [
    Theme(
        name="cat-dark",
        primary="#bd93f9",       # 主色：紫色
        secondary="#8be9fd",     # 副色：青色
        warning="#f1fa8c",
        error="#ff5555",
        success="#50fa7b",
        accent="#ff79c6",
        foreground="#f8f8f2",    # 文字色
        background="#1e1e2e",    # 背景色
        surface="#282a36",       # 表面色（输入框、状态栏）
        panel="#44475a",         # 面板色（边框、分割线）
        dark=True,
        variables={              # 自定义 CSS 变量
            "user": "#50fa7b",
            "thinking": "#8be9fd",
            "tool": "#bd93f9",
            "border": "#44475a",
        },
    ),
    Theme(name="cat-light", ...),  # 亮色主题
    Theme(name="cat-nord", ...),   # Nord 冷色调主题
]
```

### 注册与切换

```python
# on_mount 中注册所有主题
for theme in BITZ_THEMES:
    self.register_theme(theme)
self.theme = detect_theme()  # 自动检测

# 切换主题只需一行
self.theme = "cat-nord"
```

### 自动检测终端明暗

```python
def detect_theme() -> str:
    """根据 COLORFGBG 环境变量自动检测终端明暗。"""
    colorfgbg = os.environ.get("COLORFGBG", "")
    if colorfgbg and ";" in colorfgbg:
        fg = colorfgbg.split(";")[0]
        if fg in ("0", "15", "7"):
            return "cat-dark"
    return "cat-dark"
```

`COLORFGBG` 是终端模拟器设置的环境变量，格式为 `前景色;背景色`。暗色终端的前景色通常是 `15`（白色）或 `0`（黑色在深色背景上）。

### CSS 变量与主题联动

Textual 的 CSS 支持 `$variable` 语法，自动跟随当前主题：

```css
StatusBar {
    background: $surface;    /* 跟随主题的 surface 色 */
    color: $text-muted;
}
```

自定义变量通过 `Theme.variables` 定义，在 CSS 中用 `$user`、`$tool` 等引用。

### /theme 命令

在 InputBar 中拦截 `/theme` 输入，发送 `ThemeChangeRequested` 消息：

```python
# InputBar
if text == "/theme":
    self.post_message(self.ThemeChangeRequested())
else:
    self.post_message(self.MessageSubmitted(text))

# BitzApp
def on_input_bar_theme_change_requested(self, event):
    from tui.theme import THEME_NAMES
    idx = THEME_NAMES.index(self.theme)
    next_idx = (idx + 1) % len(THEME_NAMES)
    self.theme = THEME_NAMES[next_idx]
```

---

## 5.4 状态栏增强

### 问题

状态栏只显示模型名和步数，缺少关键信息：token 用量（成本监控）和当前工作目录。

### 方案：累积 token 计数 + CWD 显示

```python
class StatusBar(Widget):
    def __init__(self) -> None:
        super().__init__()
        self.model_name: str = ""
        self.step_count: int = 0
        self.input_tokens: int = 0
        self.output_tokens: int = 0

    def _format_tokens(self, n: int) -> str:
        if n >= 1000:
            return f"{n / 1000:.1f}k"
        return str(n)

    def _render_text(self) -> str:
        cwd = os.path.basename(os.getcwd())
        inp = self._format_tokens(self.input_tokens)
        out = self._format_tokens(self.output_tokens)
        return (
            f" {self.model_name} │ Step {self.step_count} │ "
            f"📥{inp} 📤{out} │ 📁 {cwd}"
        )
```

### Token 数据来源

`LLMAdapter._chat_once()` 在每次 API 调用后存储 `response.usage`：

```python
# adapter.py
try:
    self._last_usage = response.usage
except Exception:
    self._last_usage = None
```

BitzApp 在每轮结束后读取并累积：

```python
usage = getattr(self._agent.llm_adapter, '_last_usage', None)
if usage:
    self._total_input_tokens += getattr(usage, 'input_tokens', 0) or 0
    self._total_output_tokens += getattr(usage, 'output_tokens', 0) or 0
    status.update_tokens(self._total_input_tokens, self._total_output_tokens)
```

**为什么不修改 agent/ 接口？** 项目约束是"不修改 agent/ 模块的公开接口"。在 adapter 实例上存一个 `_last_usage` 属性是最小侵入的做法——不改方法签名，不改返回值，只是多了一个可读的内部属性。

---

## 5.5 会话计时

### 问题

用户不知道一轮对话花了多长时间。思考动画中有计时，但对话结束后就消失了。

### 方案：ThinkingIndicator 实时计时 + TurnTiming 持久汇总

**实时计时**——在思考动画中显示已用时间：

```python
class ThinkingIndicator(Static):
    def __init__(self) -> None:
        super().__init__()
        self._elapsed: float | None = None

    def render(self) -> Text:
        # ... spinner + "Thinking" / "Running [tool]" ...
        if self._elapsed is not None:
            parts.append(Text(f" {self._format_elapsed(self._elapsed)}", style=COLORS["muted"]))
        return Text.assemble(*parts)

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        if seconds >= 60:
            m = int(seconds // 60)
            s = int(seconds % 60)
            return f"{m}m {s}s"
        return f"{seconds:.1f}s"

    def set_elapsed(self, seconds: float) -> None:
        self._elapsed = seconds
        self.refresh()  # 触发重新渲染
```

在 `_thinking_animation_loop` 中每 80ms 更新：

```python
async def _thinking_animation_loop(self) -> None:
    while True:
        chat.update_thinking()
        if self._turn_start > 0 and chat._thinking_indicator is not None:
            elapsed = time.monotonic() - self._turn_start
            chat._thinking_indicator.set_elapsed(elapsed)
        await asyncio.sleep(0.08)
```

**持久汇总**——对话结束后在 assistant 消息下方显示 `TurnTiming`：

```python
class TurnTiming(Static):
    """每轮对话耗时汇总。"""
    def render(self) -> Text:
        return Text(f"Worked for {self._format_elapsed(self._seconds)}", style=COLORS["muted"])
```

在 `_process_agent_result` 中挂载：

```python
def _mount_turn_timing(self, chat: ChatLog) -> None:
    if self._turn_start > 0:
        elapsed = time.monotonic() - self._turn_start
        chat.mount(TurnTiming(elapsed))
```

### 时间格式

| 耗时 | 显示 |
|------|------|
| 3.2 秒 | `Worked for 3.2s` |
| 1 分 23 秒 | `Worked for 1m 23s` |
| 1 小时 2 分 3 秒 | `Worked for 1h 2m 3s` |

---

## 本章小结

| 功能 | Textual 能力 | 关键模式 |
|------|-------------|---------|
| Markdown 渲染 | `Markdown` 组件 | 容器-内容模式：Static 包 Markdown |
| Tool Call 卡片 | `Collapsible` 组件 | Reactive 属性自动刷新 UI |
| 主题系统 | `Theme` + `register_theme()` | CSS 变量 `$var` 跟随主题 |
| 状态栏增强 | 自定义 Widget | `_format_tokens()` 人类可读格式 |
| 会话计时 | `time.monotonic()` | 实时动画 + 持久汇总分离 |

**核心教训：**

1. **用框架原生能力**——Textual 的 Theme、Markdown、Collapsible 都是现成的，不要自己造轮子
2. **Reactive 属性是 Textual 的灵魂**——赋值即更新，不需要手动刷新
3. **容器-内容模式**——外层 Static 控制布局和样式，内层组件负责渲染
4. **线程安全不可妥协**——`call_from_thread` 是从后台线程更新 UI 的唯一正确方式
5. **最小侵入读取内部状态**——`_last_usage` 不改接口，只加属性，外部按需读取
