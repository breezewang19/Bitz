# 06 — TUI 体验增强：斜杠命令、多行输入、代码 diff 与鼠标

> 前置：[05-tui-aesthetics.md](05-tui-aesthetics.md) — Markdown、工具卡片、主题与状态增强

上一章我们让 Bitz 看起来很美：Markdown 渲染、折叠工具卡片、主题切换、状态栏和计时。但交互体验还不够好——没有命令系统，只能单行输入，文件编辑没有 diff 视图。

本章我们给 Bitz 加上四个体验增强功能，从最简单到最复杂，每个都对应一个核心设计模式。

---

## 6.1 斜杠命令与补全

### 问题

用户不知道有哪些可用命令，输入 `/theme` 是硬编码的特殊处理，没有统一的命令框架。也没有命令补全——用户必须记住完整的命令名。

### 方案：CommandSubmitted 消息 + CommandPopup 补全

**命令框架**：当输入以 `/` 开头时，InputBar 发送 `CommandSubmitted` 消息（而非 `MessageSubmitted`），BitzApp 按命令名分发处理：

```python
class CommandSubmitted(Message):
    def __init__(self, command: str, args: str = "") -> None:
        super().__init__()
        self.command = command  # 命令名（不含 /）
        self.args = args        # 命令参数
```

```python
# InputBar on_key
if text.startswith("/"):
    parts = text[1:].split(None, 1)
    command = parts[0] if parts else ""
    args = parts[1] if len(parts) > 1 else ""
    self.post_message(self.CommandSubmitted(command, args))
else:
    self.post_message(self.MessageSubmitted(text))
```

**命令补全**：`CommandPopup` 是一个弹出列表，当用户输入 `/` 时自动显示，继续输入时过滤匹配命令：

```python
COMMANDS = [
    ("/help", "显示帮助信息"),
    ("/clear", "清屏"),
    ("/compact", "压缩上下文"),
    ("/theme [name]", "切换主题"),
]

class CommandPopup(Static):
    def __init__(self, prefix: str = "") -> None:
        super().__init__()
        self._filtered_commands = self._filter(prefix)

    def _filter(self, prefix: str) -> list[str]:
        if not prefix:
            return [cmd.split()[0] for cmd, _ in COMMANDS]
        return [cmd.split()[0] for cmd, _ in COMMANDS
                if cmd.split()[0][1:].startswith(prefix)]
```

**交互**：Tab 补全当前高亮命令，上下键导航，ESC 关闭弹出列表。

### 关键设计决策

**为什么用消息而非直接调用？** Textual 的消息机制是组件间通信的标准方式。InputBar 只负责输入和消息分发，BitzApp 负责命令处理——职责分离，InputBar 不需要知道命令的具体逻辑。

**为什么 CommandPopup 是 InputBar 的子组件？** 补全弹出列表应该紧跟输入框，作为 InputBar 的子组件最自然。mount/remove 控制显示/隐藏。

---

## 6.2 多行输入

### 问题

单行 `Input` 无法输入多行内容（代码块、长问题描述）。用户只能一行一行发，无法换行。

### 方案：TextArea 替换 Input

Textual 的 `TextArea` 支持多行编辑、光标定位、自动滚动。我们创建 `MessageInput` 子类，拦截 Enter 键发送消息：

```python
class MessageInput(TextArea):
    """自定义 TextArea，Enter 发送消息，Shift+Enter 换行。"""

    class Submit(Message):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    def on_key(self, event: Key) -> None:
        if event.key == "enter":
            text = self.text.strip()
            if text:
                self.post_message(self.Submit(text))
            event.prevent_default()
            event.stop()
```

**关键**：`event.key == "enter"` 只匹配普通 Enter，Shift+Enter 由 TextArea 默认处理（插入换行）。`event.stop()` 阻止事件继续传播，避免 TextArea 的默认 Enter 行为。

### CSS 自适应高度

```css
InputBar {
    height: auto;
    min-height: 3;
    max-height: 10;
}

InputBar MessageInput {
    height: auto;
    min-height: 1;
    max-height: 7;
}
```

`height: auto` 让组件根据内容自动调整高度。`max-height` 限制最大高度，超出时出现滚动条。

---

## 6.3 代码 diff 视图

### 问题

`edit_file` 和 `write_file` 工具执行后，用户看不到具体改了什么。ToolCard 只显示"成功"或截断的输出，无法直观理解代码变更。

### 方案：difflib + rich.syntax

**Diff 生成**：在 `_install_tool_logger` 中，执行 `edit_file` 或 `write_file` 前读取原文件内容，执行后用 `difflib.unified_diff` 生成 diff：

```python
def logged_execute(name, args, confirmed=False, tool_id=None):
    # 执行前读取原文件
    old_content = None
    if name == "edit_file":
        with open(args.get("path", ""), "r") as f:
            old_content = f.read()

    result = original(name, args, confirmed=confirmed, tool_id=tool_id)

    # 生成 diff
    if not is_error and old_content is not None:
        if name == "edit_file":
            new_content = old_content.replace(args["old_string"], args["new_string"])
        else:
            new_content = args.get("content", "")
        diff_text = "".join(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{args['path']}", tofile=f"b/{args['path']}",
        ))
```

**Diff 渲染**：`ToolCard.set_diff()` 用 `rich.syntax.Syntax` 渲染 diff 文本：

```python
def set_diff(self, diff_text: str) -> None:
    self._status = "success"
    self._update_label()
    try:
        syntax = Syntax(diff_text, lexer="diff", theme="monokai")
        self._output_widget.update(syntax)
    except Exception:
        self._output_widget.update(diff_text[:500])
    self._collapsible.collapsed = False  # diff 默认展开
```

`rich.syntax.Syntax` 自动高亮 diff 格式——绿色标记新增行，红色标记删除行，比纯文本直观得多。

### 关键设计决策

**为什么在 monkey-patch 中生成 diff？** 工具执行发生在 agent 线程中，而文件内容在执行前后才能获取。monkey-patch 是唯一能拦截执行前后状态的点。不修改 `agent/` 模块的公开接口——只扩展 `_post_tool_result` 的参数。

**为什么 diff 默认展开？** 代码变更通常需要用户确认或理解，展开比折叠更合理。成功执行的工具默认折叠，但 diff 视图默认展开——这是不同的 UX 期望。

---

## 6.4 鼠标支持

### 问题

终端应用通常不支持鼠标交互，用户只能用键盘操作。

### 方案：Textual 内置鼠标支持

Textual 默认启用鼠标，无需任何代码。滚轮滚动 ChatLog、点击折叠/展开 ToolCard、点击定位 TextArea 光标——全部自动工作。

唯一需要确认的是 `BitzApp` 没有禁用鼠标（检查确认：没有）。

---

## 本章小结

| 功能 | 核心模式 | 关键技术 |
|------|---------|---------|
| 斜杠命令与补全 | 消息分发 + 弹出列表 | CommandSubmitted 消息，CommandPopup 过滤 |
| 多行输入 | 组件替换 + 事件拦截 | MessageInput(TextArea)，Enter/Shift+Enter |
| 代码 diff 视图 | monkey-patch 拦截 + 渲染 | difflib.unified_diff，rich.syntax.Syntax |
| 鼠标支持 | 框架内置 | Textual 默认启用 |

**核心教训：**

1. **消息机制是组件间通信的标准方式**——InputBar 只分发，BitzApp 只处理
2. **组件替换要保留接口**——MessageInput 替换 Input，但 InputBar 的外部接口不变
3. **monkey-patch 是最小侵入的集成方式**——不改 agent/ 接口，只扩展 tool logger 的参数
4. **用框架内置能力**——Textual 的鼠标支持、rich.syntax 的 diff 渲染都是现成的