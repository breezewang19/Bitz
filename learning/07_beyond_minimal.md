# 07: 超越 Minimal — 从 526 行到完整版

minimal 是最小可运行的 ReAct 智能体。526 行，4 个文件，一切清晰可见。

完整版有 ~4400 行。多出来的代码做了什么？每一段都有存在的理由——解决 minimal 遇到的真实问题。

## 任务系统

**问题**：让 LLM "创建一个任务追踪进度"，它只能用 write_file 写 JSON。并发写入会损坏数据，没有结构化查询。

**解决**：`agent/task_manager.py` 提供四个工具——`task_create`、`task_update`、`task_list`、`task_get`。

核心实现：
- 每个任务是一个 JSON 文件（`tasks/<id>.json`）
- 读写操作用文件锁（`fcntl.flock` / `msvcrt.locking`）保护，防止并发损坏
- LLM 通过工具调用操作任务，不需要直接读写文件

为什么 minimal 不需要？526 行的目的是理解 ReAct 循环。任务系统是"LLM 用工具管理状态"的延伸，理解了工具执行就理解了任务系统。

**源码**：`agent/task_manager.py`（~160 行）

## 子智能体与 Fork 模式

**问题**：复杂任务需要并行——"同时调研 A 和 B 两个方案"。单个 agent 只能串行。

**解决**：`agent/subagent.py` 提供 `spawn` 工具。

spawn 的本质是递归——创建一个新的 Agent 实例，给它一个子任务，等它完成后返回结果。子智能体有自己的 Context，但共享父智能体的 LLM 客户端。

Fork 模式更巧妙：不是复制 Context 对象，而是利用 Anthropic API 的 prompt caching——子智能体继承父智能体的消息前缀作为缓存，避免重复传输。这比复制整个 Context 更高效。

为什么 minimal 不需要？子智能体增加了循环的复杂度（递归调用、结果收集、错误传播）。526 行的目的是展示单层循环，递归是自然的延伸。

**源码**：`agent/subagent.py`（~200 行）

## 技能系统

**问题**：不同任务需要不同的 system prompt 和工具集。"代码审查"需要 git + read_file；"写文档"需要 write_file + glob。每次手动指定太麻烦。

**解决**：`agent/skill_registry.py` 实现技能的注册和发现。

技能 = 预设的 system_prompt + 工具白名单。放在 `skills/` 目录下，每个技能一个 Python 文件，自动发现加载。LLM 通过 `skill_list` 查看可用技能，通过 `skill_use` 激活。

这和 Unix 的"配置文件 + 命令行参数"一个思路——技能是预设配置，避免每次重复指定。

为什么 minimal 不需要？技能是"工具集的预组合"，理解了工具注册就理解了技能。526 行用 `create_tools()` 硬编码工具集，技能系统只是让它可配置。

**源码**：`agent/skill_registry.py`（~120 行）

## 多模型与 OpenAI 协议

**问题**：不同模型有不同权衡——Opus 强但贵，Haiku 快但弱。有时需要用 OpenAI 兼容的 API（如本地部署的模型）。

**解决**：
- `agent/model_manager.py` — 运行时切换模型，无需重启
- `agent/adapter.py` 的 OpenAI 兼容层 — 将 Anthropic 工具格式转换为 OpenAI function calling 格式

OpenAI 兼容层做了什么？两件事：
1. 请求格式转换：Anthropic 的 `tools` 参数 → OpenAI 的 `functions` 参数
2. 响应格式转换：OpenAI 的 `function_call` → Anthropic 的 `tool_use` block

这样上层代码（loop.py）不需要知道底层用的是哪个 API。

为什么 minimal 不需要？526 行只支持 Anthropic 原生协议，一个 `LLMAdapter` 类搞定。多协议是"适配器模式"的标准应用，理解了 `LLMAdapter.chat()` 就理解了适配器。

**源码**：`agent/adapter.py`（~400 行）、`agent/model_manager.py`（~80 行）

## TUI

**问题**：REPL 的 `input()` + `print()` 能用，但无法流式输出、无法中途取消、无法展示工具执行过程。

**解决**：`tui/` 用 Textual 构建终端 UI。

从 REPL 到 TUI 的关键转变：
- 同步 → 异步：agent 在后台线程运行，UI 保持响应
- 阻塞确认 → 异步确认：弹出对话框，不卡住 UI
- 一次性输出 → 流式输出：逐 token 显示 LLM 回复
- 纯文本 → 富文本：Markdown 渲染、语法高亮、颜色区分

详细设计见 [04: TUI](04_tui.md)。

**源码**：`tui/`（~1500 行）

## 阅读路线图

建议阅读顺序：

1. **minimal/ 代码** — 先跑起来，再逐文件阅读
2. **learning/07 本篇** — 了解完整版每个模块存在的理由
3. **对应源码** — 按需深入：
   - 任务系统 → `agent/task_manager.py`
   - 子智能体 → `agent/subagent.py`
   - 技能系统 → `agent/skill_registry.py`
   - 多模型 → `agent/adapter.py` + `agent/model_manager.py`
   - TUI → `tui/app.py` + `tui/widgets/`

每个模块都是 minimal 对应概念的延伸——理解了 minimal，完整版只是"加了更多同类型的东西"。
