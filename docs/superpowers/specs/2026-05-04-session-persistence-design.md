# Chat Session Persistence Design

## Problem

Bitz's Python agent layer has no session persistence — conversations are purely in-memory. When the TUI closes, all context is lost. Users cannot resume previous conversations, browse history, or switch between sessions.

## Decision

Implement lightweight JSONL-based session persistence in the Python agent layer, inspired by Claude Code's approach but significantly simplified.

## Storage

**Path**: `~/.bitz/sessions/<project-slug>/`

- `project-slug`: cwd path sanitized (non-alphanumeric → `-`, truncated 200 chars)
- Each session: one `.jsonl` file + one `.meta.json` file

### JSONL Entry Types

| type | fields | description |
|------|--------|-------------|
| `user` | uuid, content, timestamp | User text input |
| `assistant` | uuid, content, timestamp | Assistant text reply |
| `tool_use` | uuid, name, args, timestamp | Tool call request |
| `tool_result` | uuid, tool_use_id, content, is_error, timestamp | Tool execution result |

### meta.json

```json
{
  "session_id": "uuid",
  "title": "auto-generated or user-set",
  "model": "claude-sonnet-4-20250514",
  "project": "/path/to/project",
  "created_at": "ISO8601",
  "updated_at": "ISO8601",
  "message_count": 42,
  "first_prompt": "First 80 chars of first user message..."
}
```

### Write Strategy

- Each `Context.add_*` method synchronously appends one JSONL line (`json.dumps() + "\n"`)
- meta.json written on session creation, updated after each conversation turn (`updated_at`, `message_count`)
- Lazy file materialization: files created on first write, not on session init

### Read Strategy

- Session list: read `.meta.json` files only (no JSONL parsing) — fast
- Session restore: parse JSONL line-by-line → rebuild `Context.messages`
- Search: stream-scan JSONL lines for keyword matches

## Core Module: `agent/session.py`

### SessionStore

```python
class SessionStore:
    def __init__(self, project_dir: str): ...
    def create_session(self, model: str) -> str              # returns session_id
    def list_sessions(self) -> list[SessionMeta]             # read meta.json list
    def load_session(self, session_id: str) -> list[dict]    # parse JSONL → messages
    def delete_session(self, session_id: str) -> None        # delete .jsonl + .meta.json
    def append_entry(self, session_id: str, entry: dict)     # append one JSONL line
    def update_meta(self, session_id: str, **kwargs)         # update meta.json
    def search_sessions(self, query: str) -> list[SessionMeta]  # search session content
    def get_latest_session(self) -> SessionMeta | None       # most recent session
```

### Context Integration

Minimal, non-invasive change to `agent/context.py`:

```python
class Context:
    def __init__(self, ..., session_id: str = None, session_store: SessionStore = None):
        self.session_id = session_id
        self._store = session_store
```

Each `add_*` method gets a `_persist()` call at the end:

```python
def add_user(self, content: str) -> None:
    self.messages.append({"role": "user", "content": content})
    self._trim()
    self._persist("user", content)

def _persist(self, entry_type: str, content, **kwargs) -> None:
    if self._store is None:
        return
    entry = {"type": entry_type, "uuid": str(uuid4()), "timestamp": iso_now(), ...}
    self._store.append_entry(self.session_id, entry)
```

When `session_store` is None (subagents, tests), `_persist` is a no-op — zero behavioral change.

### Session Restore

```python
def restore_session(store: SessionStore, session_id: str) -> Context:
    messages = store.load_session(session_id)
    meta = store.get_meta(session_id)
    context = Context(
        system_prompt=build_system_prompt(cwd=meta.project),
        session_id=session_id,
        session_store=store,
    )
    context.messages = messages
    return context
```

Restored messages keep original role/content structure. Context._trim naturally prunes during subsequent conversation.

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
| `/save` | Manually save current session metadata |

### BitzApp Changes

```python
class BitzApp(App):
    def __init__(self, agent, ..., session_store=None, resume_session_id=None):
        self._session_store = session_store
        self._resume_session_id = resume_session_id
```

- `on_mount`: if `resume_session_id` set, restore session and render history into ChatLog
- `action_new_conversation`: create new session (new session_id, clear Context, re-associate session_store)
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

- Single Bitz process: Python GIL serializes writes naturally
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
