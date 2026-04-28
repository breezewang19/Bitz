# Bitz 🐱

A minimal AI Agent with a beautiful terminal chat interface — under 1000 lines of code.

**Bitz** is a learning project that teaches the ReAct pattern, tool calling, LLM adaptation, context management, and TUI development through a working AI agent you can chat with in your terminal.

## Features

- **ReAct Agent Loop** — Think → Act → Observe cycle with configurable max steps
- **7 Built-in Tools** — bash, read_file, write_file, edit_file, glob, grep, fetch
- **3-Tier Danger Detection** — Auto-approve readonly, confirm dangerous, force-confirm destructive
- **Beautiful TUI** — Markdown rendering, collapsible tool cards with status icons, syntax highlighting
- **Theme System** — 3 themes (Dracula dark / Light / Nord), auto-detect terminal, `/theme` to switch
- **Session Insights** — Token usage tracking, per-turn timing, step counter
- **Slash Commands** — /help, /clear, /compact, /theme with Tab autocomplete
- **Multi-line Input** — Shift+Enter for newline, auto-expanding textarea
- **Code Diff View** — Inline diff for file edits with syntax highlighting
- **Mouse Support** — Scroll, click to expand/collapse, cursor positioning
- **Inline Confirmation** — Dangerous commands show y/n prompt right in the chat
- **Graceful Cancellation** — ESC to cancel, Ctrl+C to quit

## Quick Start

```bash
cd Bitz
pip install -r requirements.txt
cp .env.example .env          # Edit .env to add your ANTHROPIC_API_KEY
python tui.py                  # Launch the TUI
```

## Architecture

```
tui.py (entry point)
├── agent/              Core Agent modules
│   ├── loop.py         Agent — ReAct loop, confirm flow, cancellation
│   ├── adapter.py      LLMAdapter — Anthropic API, 5x retry, cancel-aware, stream_chat()
│   ├── context.py      Context — message history with tool_use/tool_result pairing
│   ├── tools.py        ToolRegistry — register/execute, 3-tier danger detection
│   └── builtin_tools.py  7 built-in tools
└── tui/                Textual TUI
    ├── app.py          BitzApp — agent integration, tool logger, confirm, timing
    ├── theme.py        3 native themes + auto-detect
    └── widgets/
        ├── chat.py     ChatLog, AssistantMessage (Markdown), TurnTiming
        ├── tool_card.py  Collapsible tool cards (⟳/✓/✗ status icons)
        ├── input.py     InputBar + /theme command
        ├── status.py    StatusBar (model, steps, tokens, CWD)
        ├── confirm.py   Inline y/n confirm prompt
        └── banner.py    Welcome / goodbye animations
```

## Key Data Flow

1. User types in `InputBar` → `MessageSubmitted` event → `BitzApp._run_agent()`
2. Agent loop runs in `run_in_executor` (thread pool) to avoid blocking Textual's event loop
3. `LLMAdapter.chat()` → Anthropic API → response with `stop_reason`
4. Tool execution: `ToolRegistry.execute()` checks danger level → auto-approve / confirm / force-confirm
5. Confirmation: `[CONFIRM_REQUIRED]` → inline `ConfirmPrompt` → `asyncio.Future` resolves → loop continues
6. Cancellation: ESC sets `threading.Event` → `LLMAdapter._chat_once()` polls every 100ms → raises error

## Testing

```bash
pytest -v                                          # Run all tests
pytest Bitz/tests/test_loop.py -v                  # Run a single test file
pytest Bitz/tests/test_loop.py::TestAgent::test_basic -v  # Run a single test
```

## Learning Path

The `learning/` directory contains progressive tutorials:

| # | Topic | Key Concepts |
|---|-------|-------------|
| 00 | Introduction | Project goals, what you'll learn |
| 01 | Agent Loop | ReAct pattern, tool calling, max steps |
| 02 | LLM Adapter | Anthropic API, retry with backoff, cancellation |
| 03 | Tools & Context | Tool registry, danger detection, context trimming |
| 04 | TUI with Textual | Layout, events, thread safety, confirm flow |
| 05 | TUI Aesthetics | Markdown, tool cards, themes, timing, status bar |
| 06 | TUI Experience | Slash commands, multi-line input, streaming, diff view |

## Conventions

- All user-facing text and comments are in Chinese
- Tool output truncated at 30,000 chars
- `fetch` tool has SSRF protection (blocks private/internal IPs)
- `LLMAdapter` uses lazy `import anthropic` to avoid ~3s startup penalty
- Agent persona: "Bitz-Cat" — friendly, cat-like assistant

## License

MIT
