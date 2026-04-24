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
5. **TUI 开发** - 跨平台终端界面（core + 平台兼容层）

## 项目结构

```
Bitz/
├── agent/            # 核心模块
│   ├── adapter.py   # LLM 适配器（Anthropic 协议 + 重试）
│   ├── context.py   # 会话上下文（Anthropic 格式）
│   ├── loop.py      # Agent 循环（ReAct 模式）
│   └── tools.py     # 工具注册表
├── tests/            # 单元测试
├── learning/         # 学习资料
│   ├── 01-agent-frameworks-overview.md
│   └── 02-minimal-agent-design.md
├── tui_core.py       # TUI 共性逻辑（颜色、banner、动画、输出、主循环）
├── tui_win.py        # Windows 兼容层（msvcrt 输入）
├── tui_mac.py        # macOS/Linux 兼容层（termios 输入）
├── tui.py            # 入口（自动检测平台）
├── .env              # API 配置
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