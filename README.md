# Bitz

A learning-oriented AI agent — from a 526-line core to a full toolchain.

## Two Paths

| | Reading Path | Usage Path |
|---|---|---|
| **Goal** | Understand how an agent works | Use a full-featured agent |
| **Code** | `minimal/` — 526 lines, 4 files | `agent/` + `tui/` — ~4400 lines |
| **Run** | `python -m minimal.agent` | `python tui.py` |
| **Deps** | `anthropic`, `python-dotenv` | see `requirements.txt` |

## Architecture

### minimal/ — Reading Path

```
minimal/
├── agent.py    (112 lines)  ReAct loop + REPL
├── context.py  (102 lines)  Message management + trimming
├── llm.py       (95 lines)  Anthropic API + retry
└── tools.py    (217 lines)  Tool registry + 5 built-in tools
```

### Full Version

```
agent/
├── loop.py              ReAct loop (cancel, sub-agents)
├── context.py           Message management (persistence)
├── adapter.py           Multi-protocol LLM adapter
├── tools.py             Tool registry + execution context
├── builtin_tools.py     7 built-in tools
├── tool_result.py       ToolResult with confirm/error
├── subagent.py          Sub-agent spawn + fork
├── task_manager.py      Task CRUD (JSON + file lock)
├── skill_registry.py    Skill discovery + loading
└── model_manager.py     Multi-model switching
tui/
├── app.py               Textual TUI app
├── theme.py             Theme system
└── widgets/             9 custom widgets
```

## Features

### Core (minimal + full)

- ReAct loop — user input → LLM → tool execution → result injection → repeat
- 5 tools — bash, read_file, write_file, edit_file, glob
- Dangerous operation confirmation (sync y/n)
- Context trimming with tool_use/tool_result pair integrity
- API retry with exponential backoff

### Extended (full version only)

- TUI — Textual-based terminal UI with streaming output
- Sub-agents — spawn child agents, fork mode (shared prompt cache prefix)
- Skill system — preset system_prompt + tool sets, auto-discovery
- Task management — create/update/list/get, JSON + file lock
- Multi-model — switch models at runtime
- OpenAI protocol — compatible with OpenAI-style APIs
- Extra tools — grep, fetch
- Session persistence — save/restore conversations

## Quick Start

### minimal

```bash
pip install -r minimal/requirements.txt
echo "ANTHROPIC_API_KEY=your-key" > .env
python -m minimal.agent
```

### Full Version

```bash
pip install -r requirements.txt
echo "ANTHROPIC_API_KEY=your-key" > .env
python tui.py
```

## Learning

| # | Topic | Key Concept |
|---|---|---|
| 01 | [Why Build an Agent](learning/01_why.md) | LLM + tools = agent |
| 02 | [Building the Agent](learning/02_agent.md) | ReAct loop, context, tools |
| 03 | [Tool Design](learning/03_tools.md) | Safety, readonly detection, confirmation |
| 04 | [TUI](learning/04_tui.md) | Event-driven UI, widget composition |
| 05 | [Testing](learning/05_testing.md) | Mock LLM, integration tests |
| 06 | [Architecture](learning/06_architecture.md) | Module boundaries, data flow |
| 07 | [Beyond Minimal](learning/07_beyond_minimal.md) | Tasks, sub-agents, skills, multi-model |

## Testing

```bash
python -m pytest tests/ -v
```

30 tests covering context, tools, adapter, and loop.

## License

MIT
