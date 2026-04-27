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
2. **工具注册** - 动态注册和调用工具，支持危险操作确认
3. **LLM 适配** - Anthropic 协议适配 + 自动重试 + 取消支持
4. **上下文管理** - 会话历史和消息截断
5. **TUI 开发** - 基于 Textual 的现代终端界面（组件化 + 动画 + 线程安全）

## 项目结构

```
Bitz/
├── agent/            # 核心模块
│   ├── adapter.py   # LLM 适配器（Anthropic 协议 + 重试 + 可取消）
│   ├── context.py   # 会话上下文（Anthropic 格式）
│   ├── loop.py      # Agent 循环（ReAct 模式 + 危险操作确认）
│   ├── tools.py     # 工具注册表 + 危险操作检测
│   └── builtin_tools.py  # 内置工具定义
├── tui/              # Textual TUI 模块
│   ├── app.py       # 主应用（Agent 集成 + 确认流程 + 动画控制）
│   ├── theme.py     # 主题配色 + 全局 CSS
│   └── widgets/     # 组件
│       ├── banner.py   # 启动动画（彩虹猫 + 边框 + 眨眼 + 打字机）
│       ├── chat.py     # 聊天面板（消息 + 思考指示器 + 工具调用）
│       ├── confirm.py  # 内联确认提示（y/n 批准/拒绝）
│       ├── input.py    # 输入栏（历史 + 繁忙状态）
│       └── status.py   # 状态栏（模型名 + 步数）
├── tests/            # 单元测试
├── learning/         # 学习资料
│   ├── 01-agent-frameworks-overview.md
│   ├── 02-minimal-agent-design.md
│   ├── 03-agent-robustness-engineering.md
│   └── 04-tui-with-textual.md
├── tui_core.py       # Legacy TUI（纯 ANSI，--legacy 可切换）
├── tui_win.py        # Legacy Windows 兼容层
├── tui_mac.py        # Legacy macOS/Linux 兼容层
├── tui.py            # 入口（默认 Textual，--legacy 切换旧版）
├── .env              # API 配置
├── .env.example      # 配置模板
└── requirements.txt  # 依赖
```

## 内置工具

| 工具 | 参数 | 说明 |
|------|------|------|
| `bash` | `command: str` | 执行 shell 命令 |
| `read_file` | `path: str` | 读取文件内容 |
| `write_file` | `path: str, content: str` | 写入文件内容 |
| `edit_file` | `path, old_string, new_string` | 替换文件中的唯一字符串 |
| `glob` | `pattern: str` | 搜索文件（支持 `**/*.py` 等） |
| `grep` | `pattern, path?, include?` | 搜索文件内容（支持正则） |
| `fetch` | `url: str` | 获取网页内容（自动清理 HTML 标签） |

## 危险操作确认

`bash` 命令中的危险操作（如 `rm`, `dd`, `chmod 777` 等）和 `write_file` 覆盖已有文件时，会在聊天面板中显示内联确认提示。用户可以用左右方向键选择批准或拒绝，按 Enter 确认。

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

- [Agent 框架总览](learning/01-agent-frameworks-overview.md)
- [Minimal Agent 设计文档](learning/02-minimal-agent-design.md)
- [Agent 健壮性工程实战](learning/03-agent-robustness-engineering.md)
- [Textual TUI 开发实战](learning/04-tui-with-textual.md)
