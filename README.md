# Bitz 🐱

[中文文档](README_CN.md)

A minimal AI Agent with a beautiful terminal chat interface — core agent under 1000 lines of code.

**Bitz** is a learning project that teaches the ReAct pattern, tool calling, LLM adaptation, context management, and TUI development through a working AI agent you can chat with in your terminal.

## Features

- **ReAct Agent Loop** — Think → Act → Observe cycle with configurable max steps
- **8 Built-in Tools** — bash, read_file, write_file, edit_file, glob, grep, fetch, spawn
- **3-Tier Danger Detection** — Auto-approve readonly, confirm dangerous, force-confirm destructive
- **SubAgent / Spawn** — Spawn child agents for parallel tasks; 3 built-in agent types (general-purpose, explore, plan)
- **Fork Mode** — Share prompt cache between parent and child agents for efficient parallel execution
- **Dual LLM Protocol** — Anthropic API (native) and OpenAI-compatible API support
- **Beautiful TUI** — Markdown rendering, collapsible tool cards with status icons, syntax highlighting
- **Theme System** — 3 themes (cat-dark / cat-light / cat-nord), auto-detect terminal, `/theme` to switch
- **Session Insights** — Token usage tracking, per-turn timing, step counter
- **Skill System** — Prompt-driven behavior orchestration, `/review`, `/debug`, `/explain` built-in, user-customizable via `.bitz/skills/`; supports directory-type skills with rules/ and references/ subdirectories (e.g. `/admin-review`)
- **Slash Commands** — /help, /new, /clear, /compact, /theme, /models, /skill with Tab autocomplete
- **Multi-line Input** — Shift+Enter for newline, auto-expanding textarea
- **Code Diff View** — Inline diff for file edits with syntax highlighting
- **SubAgent Cards** — Real-time status cards for spawned sub-agents with collapsible logs
- **Copy Buttons** — Copy to clipboard on messages and tool results
- **Mouse Support** — Scroll, click to expand/collapse, cursor positioning
- **Inline Confirmation** — Dangerous commands show y/n prompt right in the chat
- **Graceful Cancellation** — ESC to cancel, Ctrl+C to quit
- **Model Management** — Multi-model config persisted to `~/.bitz/models.json`, runtime switching via /models

## Quick Start

```bash
cd Bitz
pip install -r requirements.txt
cp .env.example .env          # Edit .env to add your ANTHROPIC_API_KEY
python tui.py                  # Launch the TUI
python tui.py --legacy         # Launch the legacy ANSI TUI (fallback)
```

## Architecture

```
tui.py (entry point)
├── agent/              Core Agent modules
│   ├── loop.py         Agent — ReAct loop, confirm flow, cancellation
│   ├── adapter.py      LLMAdapter — Anthropic/OpenAI API, 5x retry, cancel-aware, stream_chat()
│   ├── context.py      Context — message history, active_skill, tool_use/tool_result pairing
│   ├── tools.py        ToolRegistry — register/execute, 3-tier danger detection
│   ├── builtin_tools.py  8 built-in tool definitions
│   ├── prompt.py       System prompt builder (persona + rules + CLAUDE.md + environment + skills)
│   ├── skills.py       SkillRegistry — load/parse .md skill files, trigger lookup
│   ├── models.py       ModelStore — multi-model config persistence (~/.bitz/models.json)
│   ├── agent_definition.py  AgentDefinition dataclass + 3 built-in agent types
│   ├── subagent.py     SubAgent — concurrent execution, context isolation
│   └── fork_message_builder.py  ForkMessageBuilder — prompt cache sharing for parallel subagents
├── skills/             Built-in Skill files
│   ├── code-review.md  /review — code quality audit
│   ├── debug.md        /debug — systematic debugging
│   ├── explain.md      /explain — code explanation
│   └── admin-review/   /admin-review — administrative document compliance review (38 review points)
├── tui/                Textual TUI
│   ├── app.py          BitzApp — agent integration, skill activation, tool logger, confirm, timing
│   ├── theme.py        3 native themes + auto-detect
│   └── widgets/
│       ├── chat.py     ChatLog, UserMessage, AssistantMessage, ThinkingIndicator, SubAgentCard, TurnTiming
│       ├── tool_card.py  Collapsible tool cards (⟳/✓/✗ status icons) + diff view
│       ├── input.py     InputBar + MessageInput (TextArea) + command/skill autocomplete
│       ├── command_popup.py  Dynamic command+skill autocomplete with virtual scroll
│       ├── status.py    StatusBar (model, steps, tokens, CWD)
│       ├── confirm.py   Inline y/n confirm prompt
│       ├── banner.py    Animated cat banner with gradient + goodbye animation
│       ├── copy_button.py  Clipboard copy button widget
│       ├── model_select.py  Model selection modal
│       ├── model_add.py     Model add form modal
│       └── model_confirm.py Delete confirmation modal
├── learning/           Progressive tutorials
├── tests/              Test suite (20 test files)
└── docs/               Design docs
```

## Key Data Flow

```
User types in InputBar
    │
    ▼
MessageSubmitted event
    │
    ▼
BitzApp._run_agent() → asyncio.create_task(_agent_loop())
    │
    ▼
Agent.run() in ThreadPoolExecutor (non-blocking to Textual event loop)
    │
    ▼  (ReAct Loop)
    ├──► LLMAdapter.chat() → Anthropic/OpenAI API
    │        │
    │        ▼
    │    LLMResponse (stop_reason: "end_turn" | "tool_use" | "max_tokens")
    │        │
    │        ▼  (if tool_use)
    │    ToolRegistry.execute() → 3-tier danger check
    │        │
    │        ├── auto-approve → execute immediately
    │        ├── [CONFIRM_REQUIRED] → inline ConfirmPrompt → user y/n
    │        └── force-confirm → inline ConfirmPrompt → user y/n
    │        │
    │        ▼
    │    Context.add_tool_result() → continue loop
    │
    ▼  (if end_turn)
Assistant response rendered in ChatLog with Markdown
```

## Built-in Agent Types

| Type | Tools | Permission | Max Steps | Description |
|------|-------|-----------|-----------|-------------|
| general-purpose | All | auto | 50 | Full capabilities |
| explore | No write_file, edit_file, spawn | readonly | 50 | Read-only codebase exploration |
| plan | No write_file, edit_file, spawn | readonly | 50 | Architecture planning |

## Testing

```bash
pytest -v                                          # Run all tests
pytest tests/test_loop.py -v                       # Run a single test file
pytest tests/test_loop.py::TestAgent::test_basic -v  # Run a single test
```

## Learning Path

The `learning/` directory contains progressive tutorials:

| # | Topic | Key Concepts |
|---|-------|-------------|
| 01 | Agent Frameworks Overview | Landscape of agent frameworks, design trade-offs |
| 02 | Minimal Agent Design | ReAct pattern, tool calling, max steps |
| 03 | Agent Robustness Engineering | Retry, cancellation, danger detection, context trimming |
| 04 | TUI with Textual | Layout, events, thread safety, confirm flow, aesthetics |
| 05 | Prompt Engineering | Layered prompts, dynamic injection, tool descriptions, caching |
| 06 | [Skill System](learning/06-skill-system.md) | Skill ≠ Tool, frontmatter parsing, dynamic system_prompt assembly |

## Conventions

- Tool output truncated at 30,000 chars
- `fetch` tool has SSRF protection (blocks private/internal IPs)
- `LLMAdapter` uses lazy `import anthropic` to avoid ~3s startup penalty
- Agent persona: "Bitz-Cat" — friendly, cat-like assistant
- Parallel tool execution via `ThreadPoolExecutor`

## License

MIT
