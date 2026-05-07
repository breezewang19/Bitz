# Bitz

一个学习型 AI 智能体——从 526 行核心到完整工具链。

## 两条路径

| | 阅读路径 | 使用路径 |
|---|---|---|
| **目标** | 理解智能体如何工作 | 使用功能完整的智能体 |
| **代码** | `minimal/` — 526 行，4 文件 | `agent/` + `tui/` — ~4400 行 |
| **运行** | `python -m minimal.agent` | `python tui.py` |
| **依赖** | `anthropic`, `python-dotenv` | 见 `requirements.txt` |

## 架构

### minimal/ — 阅读路径

```
minimal/
├── agent.py    (112 行)  ReAct 循环 + REPL
├── context.py  (102 行)  消息管理 + 裁剪
├── llm.py       (95 行)  Anthropic API + 重试
└── tools.py    (217 行)  工具注册 + 5 个内置工具
```

### 完整版

```
agent/
├── loop.py              ReAct 循环（含取消、子智能体）
├── context.py           消息管理（含持久化）
├── adapter.py           多协议 LLM 适配
├── tools.py             工具注册 + 执行上下文
├── builtin_tools.py     7 个内置工具
├── tool_result.py       ToolResult 含确认/错误
├── subagent.py          子智能体 spawn + fork
├── task_manager.py      任务 CRUD（JSON + 文件锁）
├── skill_registry.py    技能发现 + 加载
└── model_manager.py     多模型切换
tui/
├── app.py               Textual TUI 应用
├── theme.py             主题系统
└── widgets/             9 个自定义组件
```

## 特性

### 核心特性（minimal + 完整版共有）

- ReAct 循环 — 用户输入 → LLM → 工具执行 → 结果回注 → 循环
- 5 个工具 — bash、read_file、write_file、edit_file、glob
- 危险操作确认（同步 y/n）
- 上下文裁剪，保持 tool_use/tool_result 配对完整
- API 重试，指数退避

### 扩展特性（仅完整版）

- TUI — 基于 Textual 的终端界面，流式输出
- 子智能体 — spawn 子智能体，fork 模式（共享 prompt cache 前缀）
- 技能系统 — 预设 system_prompt + 工具集，自动发现
- 任务管理 — create/update/list/get，JSON + 文件锁
- 多模型 — 运行时切换模型
- OpenAI 协议 — 兼容 OpenAI 风格 API
- 额外工具 — grep、fetch
- 会话持久化 — 保存/恢复对话

## 快速开始

### minimal

```bash
pip install -r minimal/requirements.txt
echo "ANTHROPIC_API_KEY=your-key" > .env
python -m minimal.agent
```

### 完整版

```bash
pip install -r requirements.txt
echo "ANTHROPIC_API_KEY=your-key" > .env
python tui.py
```

## 学习教程

| # | 主题 | 核心概念 |
|---|---|---|
| 01 | [为什么要造智能体](learning/01_why.md) | LLM + 工具 = 智能体 |
| 02 | [构建智能体](learning/02_agent.md) | ReAct 循环、上下文、工具 |
| 03 | [工具设计](learning/03_tools.md) | 安全、只读检测、确认机制 |
| 04 | [TUI](learning/04_tui.md) | 事件驱动 UI、组件组合 |
| 05 | [测试](learning/05_testing.md) | Mock LLM、集成测试 |
| 06 | [架构](learning/06_architecture.md) | 模块边界、数据流 |
| 07 | [超越 Minimal](learning/07_beyond_minimal.md) | 任务、子智能体、技能、多模型 |

## 测试

```bash
python -m pytest tests/ -v
```

30 个测试，覆盖 context、tools、adapter、loop。

## 许可

MIT
