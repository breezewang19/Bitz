# Chat Session Persistence Design

## Problem

Bitz's Python agent layer has no session persistence — conversations are purely in-memory. When the TUI closes, all context is lost. Users cannot resume previous conversations, browse history, or switch between sessions.

## Decision

Implement lightweight JSONL-based session persistence in the Python agent layer, inspired by Claude Code's approach but significantly simplified.

## Storage

**Path**: `~/.bitz/sessions/<project-slug>/`

- `project-slug`: cwd path sanitized (non-alphanumeric → `-`, truncated 200 chars)
- Each session: one `.jsonl` file + one `.meta.json` file

### JSONL Format

One JSONL line per `Context.add_*` call, preserving the exact `role` and `content` structure that the Anthropic API expects. This eliminates the need for any reconstruction algorithm — `load_session()` reads lines and directly populates `Context.messages`.

Each line is a JSON object with the message dict plus persistence metadata:

```jsonl
{"role":"user","content":"hello","uuid":"...","timestamp":"..."}
{"role":"assistant","content":[{"type":"text","text":"Let me check"},{"type":"tool_use","id":"toolu_01","name":"bash","input":{"command":"ls"}}],"uuid":"...","timestamp":"..."}
{"role":"user","content":[{"type":"tool_result","tool_use_id":"toolu_01","content":"file1.txt\nfile2.txt"}],"uuid":"...","timestamp":"..."}
{"role":"assistant","content":"Here are the files.","uuid":"...","timestamp":"..."}
```

Key design decisions:
- `role` and `content` are stored exactly as Anthropic API messages — no decomposition into separate entry types
- `uuid` is a persistence identifier (for deduplication and reference), separate from Anthropic's `tool_use_id` which lives inside `content` blocks
- `timestamp` is ISO 8601 UTC
- On restore, each line becomes one entry in `Context.messages` with no transformation needed

### meta.json

```json
{
  "session_id": "uuid",
  "title": "auto-generated or user-set",
  "model": "claude-sonnet-4-20250514",
  "project": "/path/to/project",
  "created_at": "ISO8601",
  "updated_at": "ISO8601",
  "turn_count": 5,
  "first_prompt": "First 80 chars of first user message..."
}
```

`turn_count` counts user turns (number of times the user submitted input), not total messages or JSONL lines.

### Write Strategy

- Each `Context.add_*` method synchronously appends one JSONL line containing the full message dict plus `uuid` and `timestamp`
- `append_entry()` uses a `threading.Lock` to ensure atomic writes (agent.run executes in a thread pool via `run_in_executor`)
- meta.json written on session creation, updated after each user turn (`updated_at`, `turn_count`)
- Lazy file materialization: files created on first write, not on session init

### Read Strategy

- Session list: read `.meta.json` files only (no JSONL parsing) — fast
- Session restore: parse JSONL line-by-line → extract `role`/`content` → populate `Context.messages` directly
- Search: case-insensitive substring match across JSONL lines, return matching sessions with a snippet of the matching line

## Core Module: `agent/session.py`

### SessionStore

```python
class SessionStore:
    def __init__(self, project_dir: str): ...
    def create_session(self, model: str) -> str              # returns session_id
    def list_sessions(self) -> list[SessionMeta]             # read meta.json list
    def load_session(self, session_id: str) -> list[dict]    # parse JSONL → messages (role/content dicts)
    def delete_session(self, session_id: str) -> None        # delete .jsonl + .meta.json
    def append_entry(self, session_id: str, entry: dict)     # append one JSONL line (thread-safe, locked)
    def update_meta(self, session_id: str, **kwargs)         # update meta.json
    def search_sessions(self, query: str) -> list[tuple[SessionMeta, str]]  # (meta, snippet) case-insensitive substring
    def get_latest_session(self) -> SessionMeta | None       # most recent session
    def get_meta(self, session_id: str) -> SessionMeta       # read single meta.json
```

### Context Integration

Minimal, non-invasive change to `agent/context.py`:

```python
class Context:
    def __init__(self, ..., session_id: str = None, session_store: SessionStore = None):
        self.session_id = session_id
        self._store = session_store
```

Each `add_*` method gets a `_persist()` call at the end. The `_persist` method stores the full message dict (role + content) as-is:

```python
def add_user(self, content: str) -> None:
    msg = {"role": "user", "content": content}
    self.messages.append(msg)
    self._trim()
    self._persist(msg)

def add_assistant_text(self, text: str) -> None:
    msg = {"role": "assistant", "content": text}
    self.messages.append(msg)
    self._trim()
    self._persist(msg)

def add_assistant_message(self, content: list) -> None:
    msg = {"role": "assistant", "content": content}
    self.messages.append(msg)
    self._trim()
    self._persist(msg)

def add_tool_results(self, results: list[tuple[str, str]]) -> None:
    blocks = [{"type": "tool_result", "tool_use_id": tid, "content": content} for tid, content in results]
    msg = {"role": "user", "content": blocks}
    self.messages.append(msg)
    self._trim()
    self._persist(msg)

def _persist(self, msg: dict) -> None:
    if self._store is None:
        return
    entry = {**msg, "uuid": str(uuid4()), "timestamp": datetime.now(timezone.utc).isoformat()}
    self._store.append_entry(self.session_id, entry)
```

When `session_store` is None (subagents, tests), `_persist` is a no-op — zero behavioral change.

### Session Restore

```python
def restore_session(store: SessionStore, session_id: str) -> Context:
    messages = store.load_session(session_id)  # returns list of {"role": ..., "content": ...}
    meta = store.get_meta(session_id)
    context = Context(
        system_prompt=build_system_prompt(cwd=meta.project),
        session_id=session_id,
        session_store=store,
    )
    context.messages = messages  # direct assignment — JSONL stores exact role/content structure
    return context
```

`load_session()` reads each JSONL line, strips `uuid` and `timestamp`, and returns the remaining `{"role": ..., "content": ...}` dict. No reconstruction needed — the format matches Anthropic API message structure exactly.

### Subagent Isolation

Subagents (`agent/subagent.py`) create Context without session_store — no persistence for subagent conversations.

## TUI Integration

### New Components

1. **SessionListScreen** — modal overlay (like ModelSelectScreen)
   - List history sessions: title, model, time, message count
   - Up/down to select, Enter to restore, `d` to delete, `/` to search
   - Top search bar with real-time filtering

2. **SessionRestoreBanner** — startup prompt
   - Shown below Banner when unfinished history sessions exist
   - `Detected last session: "xxx..." (42 messages) [Enter to restore / Esc to skip]`

### New Slash Commands

| Command | Description |
|---------|-------------|
| `/sessions` | Open session list modal |
| `/resume [id]` | Resume specified session (latest if no id) |
| `/title <text>` | Set current session title |

### BitzApp Changes

```python
class BitzApp(App):
    def __init__(self, agent, ..., session_store=None, resume_session_id=None):
        self._session_store = session_store
        self._resume_session_id = resume_session_id
```

- `on_mount`: if `resume_session_id` set, restore session and render history into ChatLog
- `action_new_conversation`: finalize old session's meta.json (final `update_meta()`), then create new session (new session_id, clear Context, re-associate session_store). `get_latest_session()` returns the session with the most recent `updated_at`, so a brand-new empty session will not overshadow a previous session with actual content.
- `_process_agent_result`: call `session_store.update_meta()` after each turn
- `action_quit`: ensure final meta update completes

### Restored ChatLog Rendering

On restore, iterate `Context.messages` and call `chat.add_message(role, content)` for each. tool_use/tool_result messages rendered as ToolCard style.

### Auto Title

First user message's first 80 chars used as default title in meta.json. User can override with `/title`.

## Error Handling

### Write Failure

- JSONL append failure (disk full, permissions): catch exception, silently degrade — conversation continues without persistence
- Show small disk icon in StatusBar to indicate persistence error, don't block conversation

### File Corruption

- Invalid JSONL lines during parse: skip line, continue parsing, don't abort restore
- Corrupted meta.json: rebuild from JSONL file (scan first/last lines)

### Concurrency

- `append_entry()` uses a `threading.Lock` to ensure atomic writes — `agent.run()` executes in a thread pool via `run_in_executor`, and tool execution also uses `ThreadPoolExecutor`, so concurrent `_persist()` calls are possible
- Multiple Bitz instances on same project: each has independent session_id, no file conflicts

### Large Files

- JSONL > 5MB: session list reads meta.json only (no JSONL parsing)
- Search: stream-scan large files line-by-line, don't load into memory
- No compaction (Context._trim handles in-memory pruning; JSONL retains full history for review)

### Session Cleanup

- No automatic deletion (disk usage is minimal)
- Users delete manually via TUI

## Startup Flow

```
Bitz starts
  → SessionStore.list_sessions()
  → History sessions exist?
    → Yes: show SessionRestoreBanner
      → User presses Enter → restore latest session
      → User presses Esc → create new session
    → No: create new session
```

## Future Extensions (not in scope)

- `bitz --resume <id>` / `bitz --continue` CLI arguments
- Session export/import
- Session memory (structured markdown notes, like Claude Code's SessionMemoryService)
