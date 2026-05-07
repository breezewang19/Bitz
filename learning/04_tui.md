# 04: TUI — 终端用户界面

minimal 版用 `input(">>> ")` 和 `print()` 与用户交互。能用，但体验有限——看不到工具执行过程，无法中途取消，长输出刷屏。

完整版用 [Textual](https://textual.textualize.so/) 构建了一个终端 UI，解决这些问题。

## 从 REPL 到 TUI

REPL 的问题：

1. **阻塞** — `agent.run()` 是同步的，执行期间用户什么都做不了
2. **无反馈** — 工具执行时没有进度指示
3. **无法取消** — 一旦开始就只能等

TUI 的解决方式：

1. **异步** — agent 在后台线程运行，UI 保持响应
2. **实时反馈** — 工具执行状态、LLM 流式输出实时显示
3. **可取消** — 随时按 Esc 取消当前操作

核心转变：从"同步阻塞"到"事件驱动"。

## 事件驱动

Textual 的核心是事件循环。用户输入、LLM 响应、工具执行结果——都是事件：

```python
class BitzApp(App):
    def on_input_submitted(self, event):  # 用户按回车
        self.run_agent(event.value)       # 启动后台任务

    def on_agent_response(self, event):   # LLM 返回了文本
        self.message_list.add_message(event.text)

    def on_tool_executed(self, event):    # 工具执行完毕
        self.tool_panel.add_result(event.name, event.output)
```

每个事件触发一个处理函数，处理函数可能产生新事件。这就是事件驱动——不用主动轮询，等事件来就行。

## 组件组合

TUI 由 11 个组件组成，按功能分组：

### 核心交互

| 组件 | 职责 |
|------|------|
| `ChatInput` | 用户输入框，支持多行、历史回溯 |
| `MessageList` | 消息列表，区分用户/助手/工具消息 |

### 状态展示

| 组件 | 职责 |
|------|------|
| `StatusBar` | 底部状态栏，显示模型名、token 数、步数 |
| `ToolPanel` | 工具执行面板，显示命令、输出、耗时 |

### 辅助面板

| 组件 | 职责 |
|------|------|
| `HelpPanel` | 快捷键帮助 |
| `ModelPanel` | 模型切换 |
| `TaskPanel` | 任务列表 |
| `SkillPanel` | 技能浏览 |
| `HistoryPanel` | 历史会话 |

### 容器

| 组件 | 职责 |
|------|------|
| `ChatScreen` | 主屏幕，组合所有组件 |
| `BitzApp` | 应用入口，管理生命周期 |

组件之间通过 Textual 的消息系统通信——一个组件发出消息，另一个组件接收处理。不需要直接引用对方。

## 异步确认

minimal 版的确认是同步的：

```python
answer = input("确认执行? [y/N] ")  # 阻塞
```

TUI 版是异步的：

```python
# 弹出确认对话框
dialog = ConfirmDialog("执行命令: rm -rf /")
# 用户点击按钮后触发回调
def on_confirm():
    self.execute_tool(confirmed=True)
```

用户可以在确认前继续浏览消息、滚动历史——UI 不会卡住。

## 流式输出

LLM 的回复可以逐 token 显示，而不是等全部生成完：

```python
async def on_text_delta(self, delta):
    self.current_message.append(delta.text)
    self.message_list.refresh()  # 实时更新
```

这需要 LLM API 的 streaming 模式。minimal 版不用 streaming，TUI 版用。

## 关键设计决策

**为什么用 Textual 而不是 curses？**
curses 是底层库，需要手动处理布局、颜色、输入。Textual 提供了 CSS 布局、组件系统、事件机制——写 TUI 像写 Web 前端。

**为什么后台线程而不是 asyncio？**
Anthropic SDK 的 `messages.create()` 是同步调用。放在主线程会阻塞 UI。用后台线程包装，主线程跑 Textual 事件循环。

**为什么组件之间用消息通信？**
解耦。`ChatInput` 不需要知道 `MessageList` 的存在——它只发出 `InputSubmitted` 事件。谁想响应就订阅。这让组件可以独立开发和替换。

---

## 下一步

- [05: 测试](05_testing.md) — 如何测试一个会调 API 的智能体
- [07: 超越 Minimal](07_beyond_minimal.md) — 从 minimal 到完整版的演进路径
