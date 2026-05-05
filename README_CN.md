# Bitz 🐱

> **v0.5.0**

[English](README.md)

一个极简 AI Agent，拥有精美的终端聊天界面 — 核心代码不到 1000 行。

**Bitz** 是一个学习项目，通过一个可以在终端对话的 AI Agent，教你理解 ReAct 模式、工具调用、LLM 适配、上下文管理和 TUI 开发。

## 特性

- **ReAct Agent 循环** — Think → Act → Observe 循环，可配置最大步数
- **8 个内置工具** — bash、read_file、write_file、edit_file、glob、grep、fetch、spawn
- **三级危险检测** — 只读自动批准、危险操作需确认、破坏性操作强制确认
- **子代理 / Spawn** — 生成子代理并行执行任务；3 种内置代理类型（general-purpose、explore、plan）
- **Fork 模式** — 父子代理共享 prompt cache，高效并行执行
- **双协议支持** — Anthropic API（原生）和 OpenAI 兼容 API
- **精美 TUI** — Markdown 渲染、可折叠工具卡片（状态图标）、语法高亮
- **主题系统** — 3 套主题（cat-dark / cat-light / cat-nord），自动检测终端，`/theme` 切换
- **会话洞察** — Token 用量追踪、每轮计时、步数计数
- **Skill 系统** — 基于提示词的行为编排，内置 `/review`、`/debug`、`/explain`，用户可通过 `.bitz/skills/` 自定义；支持目录型 skill（含 rules/ 和 references/ 子目录，如 `/admin-review`）
- **斜杠命令** — /help、/new、/clear、/compact、/theme、/models、/skill，支持 Tab 自动补全
- **多行输入** — Shift+Enter 换行，自动扩展文本框
- **代码 Diff 视图** — 文件编辑的内联 diff，带语法高亮
- **子代理卡片** — 实时显示子代理状态，可折叠日志
- **复制按钮** — 消息和工具结果一键复制到剪贴板
- **鼠标支持** — 滚动、点击展开/折叠、光标定位
- **内联确认** — 危险命令在聊天中直接显示 y/n 确认
- **优雅取消** — ESC 取消当前操作，Ctrl+C 退出
- **模型管理** — 多模型配置持久化到 `~/.bitz/models.json`，运行时通过 /models 切换

## 快速开始

```bash
cd Bitz
pip install -r requirements.txt
cp .env.example .env          # 编辑 .env，填入你的 ANTHROPIC_API_KEY
python tui.py                  # 启动 TUI
python tui.py --legacy         # 启动旧版 ANSI TUI（备用）
```

## 架构

```
tui.py (入口)
├── agent/              核心 Agent 模块
│   ├── loop.py         Agent — ReAct 循环、确认流程、取消机制
│   ├── adapter.py      LLMAdapter — Anthropic/OpenAI API、5 次重试、可取消、stream_chat()
│   ├── context.py      Context — 消息历史、active_skill、tool_use/tool_result 配对
│   ├── tools.py        ToolRegistry — 注册/执行、三级危险检测
│   ├── builtin_tools.py  8 个内置工具定义
│   ├── prompt.py       系统提示词构建器（人设 + 规则 + CLAUDE.md + 环境 + skills）
│   ├── skills.py       SkillRegistry — 加载/解析 .md skill 文件、触发查找
│   ├── models.py       ModelStore — 多模型配置持久化（~/.bitz/models.json）
│   ├── tasks.py        Task — 数据模型、持久化 CRUD、文件锁
│   ├── task_reminder.py  任务提醒 — 基于步数的提醒注入
│   ├── session.py      Session — 会话管理、路径清洗
│   ├── agent_definition.py  AgentDefinition 数据类 + 3 种内置代理类型
│   ├── subagent.py     SubAgent — 并发执行、上下文隔离
│   └── fork_message_builder.py  ForkMessageBuilder — 并行子代理的 prompt cache 共享
├── skills/             内置 Skill 文件
│   ├── code-review.md  /review — 代码质量审计
│   ├── debug.md        /debug — 系统化调试
│   ├── explain.md      /explain — 代码解释
│   └── admin-review/   /admin-review — 行政文档合规审查（38 个审查点）
├── tui/                Textual TUI
│   ├── app.py          BitzApp — Agent 集成、Skill 激活、工具日志、确认、计时
│   ├── theme.py        3 套原生主题 + 自动检测
│   └── widgets/
│       ├── chat.py     ChatLog、UserMessage、AssistantMessage、ThinkingIndicator、SubAgentCard、TurnTiming
│       ├── tool_card.py  可折叠工具卡片（⟳/✓/✗ 状态图标）+ diff 视图
│       ├── input.py     InputBar + MessageInput（TextArea）+ 命令/Skill 自动补全
│       ├── command_popup.py  动态命令+Skill 自动补全弹窗（虚拟滚动）
│       ├── status.py    StatusBar（模型、步数、Token、工作目录）
│       ├── confirm.py   内联 y/n 确认提示
│       ├── banner.py    动画猫咪横幅（渐变色）+ 退出动画
│       ├── task_list.py  任务列表组件（状态图标、自动折叠）
│       ├── session_list.py  会话列表（选择-操作模式）
│       ├── session_banner.py  会话信息横幅
│       ├── copy_button.py  剪贴板复制按钮组件
│       ├── model_select.py  模型选择弹窗
│       ├── model_add.py     添加模型表单弹窗
│       └── model_confirm.py 删除确认弹窗
├── learning/           渐进式教程
├── tests/              测试套件（20 个测试文件）
└── docs/               设计文档
```

## 核心数据流

```
用户在 InputBar 输入
    │
    ▼
MessageSubmitted 事件
    │
    ▼
BitzApp._run_agent() → asyncio.create_task(_agent_loop())
    │
    ▼
Agent.run() 在 ThreadPoolExecutor 中运行（不阻塞 Textual 事件循环）
    │
    ▼  (ReAct 循环)
    ├──► LLMAdapter.chat() → Anthropic/OpenAI API
    │        │
    │        ▼
    │    LLMResponse (stop_reason: "end_turn" | "tool_use" | "max_tokens")
    │        │
    │        ▼  (如果是 tool_use)
    │    ToolRegistry.execute() → 三级危险检测
    │        │
    │        ├── 自动批准 → 立即执行
    │        ├── [CONFIRM_REQUIRED] → 内联 ConfirmPrompt → 用户 y/n
    │        └── 强制确认 → 内联 ConfirmPrompt → 用户 y/n
    │        │
    │        ▼
    │    Context.add_tool_result() → 继续循环
    │
    ▼  (如果是 end_turn)
助手回复在 ChatLog 中以 Markdown 渲染
```

## 内置代理类型

| 类型 | 工具 | 权限 | 最大步数 | 说明 |
|------|------|------|----------|------|
| general-purpose | 全部 | auto | 50 | 完整能力 |
| explore | 无 write_file、edit_file、spawn | readonly | 50 | 只读代码库探索 |
| plan | 无 write_file、edit_file、spawn | readonly | 50 | 架构规划 |

## 测试

```bash
pytest -v                                          # 运行所有测试
pytest tests/test_loop.py -v                       # 运行单个测试文件
pytest tests/test_loop.py::TestAgent::test_basic -v  # 运行单个测试
```

## 学习路径

`learning/` 目录包含渐进式教程：

| # | 主题 | 核心概念 |
|---|------|----------|
| 01 | Agent 框架概览 | Agent 框架生态、设计权衡 |
| 02 | 极简 Agent 设计 | ReAct 模式、工具调用、最大步数 |
| 03 | Agent 健壮性工程 | 重试、取消、危险检测、上下文裁剪 |
| 04 | 用 Textual 构建 TUI | 布局、事件、线程安全、确认流程、美学 |
| 05 | 提示词工程 | 分层提示词、动态注入、工具描述、缓存 |
| 06 | [Skill 系统](learning/06-skill-system.md) | Skill ≠ Tool、frontmatter 解析、动态 system_prompt 拼接 |

## 约定

- 工具输出截断上限 30,000 字符
- `fetch` 工具有 SSRF 防护（屏蔽私有/内网 IP）
- `LLMAdapter` 延迟 `import anthropic`，避免约 3 秒的启动开销
- Agent 人设："Bitz-Cat" — 友好的猫咪助手
- 通过 `ThreadPoolExecutor` 并行执行工具

## 许可证

MIT
