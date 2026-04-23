# Bitz

AI Agent 学习项目 · 终端对话界面

## 定位

一个最小可运行的 AI Agent 实现，用于学习 Agent 的核心原理。

## 快速开始

```bash
cd Bitz
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 配置 API Key
python tui.py
```

## 学习内容

通过本项目可以学习：

1. **Agent 循环** - ReAct 模式的循环控制器
2. **工具注册** - 动态注册和调用工具
3. **LLM 适配** - Anthropic 协议适配
4. **上下文管理** - 会话历史和消息截断
5. **TUI 开发** - 终端界面彩色输出

## 项目结构

```
Bitz/
├── agent/           # 核心模块
│   ├── adapter.py  # LLM 适配器（Anthropic 协议）
│   ├── context.py   # 会话上下文
│   ├── loop.py     # Agent 循环
│   └── tools.py    # 工具注册表
├── tests/           # 单元测试
├── learning/        # 学习资料
│   ├── 2026-04-23-agent-frameworks-research.md
│   └── 2026-04-23-minimal-agent-research-report.md
├── tui.py           # 终端界面入口
├── .env             # API 配置
└── requirements.txt # 依赖
```

## 内置工具

| 工具 | 参数 | 说明 |
|------|------|------|
| `bash` | `command: str` | 执行 shell 命令 |
| `read_file` | `path: str` | 读取文件内容 |

## 测试

```bash
pytest -v
```

## 配置

`.env` 文件：

```bash
ANTHROPIC_API_KEY=your-api-key
ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic
ANTHROPIC_MODEL=MiniMax-M2.7
```

## 学习资料

- [Agent 框架调研](learning/2026-04-23-agent-frameworks-research.md)
- [Minimal Agent 研究报告](learning/2026-04-23-minimal-agent-research-report.md)
