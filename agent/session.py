"""Session 持久化 — JSONL append-only 存储"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def sanitize_path(name: str) -> str:
    s = "".join(c if c.isalnum() else "-" for c in name)
    return s[:200]


@dataclass
class SessionMeta:
    session_id: str
    title: str
    model: str
    project: str
    created_at: str
    updated_at: str
    turn_count: int
    first_prompt: str


class SessionStore:
    def __init__(self, project_dir: str, base_dir: Path | None = None):
        self._base = base_dir or Path.home() / ".bitz" / "sessions"
        self._slug = sanitize_path(project_dir)
        self._dir = self._base / self._slug
        self._lock = threading.Lock()

    def _jsonl_path(self, session_id: str) -> Path:
        return self._dir / f"{session_id}.jsonl"

    def _meta_path(self, session_id: str) -> Path:
        return self._dir / f"{session_id}.meta.json"

    def create_session(self, model: str) -> str:
        session_id = str(uuid4())
        self._dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        meta = SessionMeta(
            session_id=session_id,
            title="",
            model=model,
            project="",
            created_at=now,
            updated_at=now,
            turn_count=0,
            first_prompt="",
        )
        self._write_meta(session_id, meta)
        return session_id

    def append_entry(self, session_id: str, entry: dict) -> None:
        path = self._jsonl_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with self._lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)

    def load_session(self, session_id: str) -> list[dict]:
        path = self._jsonl_path(session_id)
        if not path.exists():
            return []
        messages = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = {k: v for k, v in entry.items() if k in ("role", "content")}
                messages.append(msg)
        return messages

    def get_meta(self, session_id: str) -> SessionMeta:
        path = self._meta_path(session_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        return SessionMeta(**data)

    def update_meta(self, session_id: str, **kwargs) -> None:
        meta = self.get_meta(session_id)
        for k, v in kwargs.items():
            if hasattr(meta, k):
                setattr(meta, k, v)
        meta.updated_at = datetime.now(timezone.utc).isoformat()
        self._write_meta(session_id, meta)

    def _write_meta(self, session_id: str, meta: SessionMeta) -> None:
        path = self._meta_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(meta), ensure_ascii=False, indent=2), encoding="utf-8")

    def list_sessions(self) -> list[SessionMeta]:
        if not self._dir.exists():
            return []
        metas = []
        for p in self._dir.glob("*.meta.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                metas.append(SessionMeta(**data))
            except Exception:
                continue
        metas.sort(key=lambda m: m.updated_at, reverse=True)
        return metas

    def delete_session(self, session_id: str) -> None:
        jsonl = self._jsonl_path(session_id)
        meta = self._meta_path(session_id)
        if jsonl.exists():
            jsonl.unlink()
        if meta.exists():
            meta.unlink()

    def get_latest_session(self) -> SessionMeta | None:
        sessions = self.list_sessions()
        return sessions[0] if sessions else None

    def search_sessions(self, query: str) -> list[tuple[SessionMeta, str]]:
        q = query.lower()
        results = []
        for meta in self.list_sessions():
            path = self._jsonl_path(meta.session_id)
            if not path.exists():
                continue
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if q in line.lower():
                        snippet = line[:200]
                        results.append((meta, snippet))
                        break
        return results


def restore_session(store: SessionStore, session_id: str, system_prompt: str = "") -> tuple:
    """Restore a session into a fresh Context."""
    from agent.context import Context

    messages = store.load_session(session_id)
    meta = store.get_meta(session_id)
    context = Context(
        system_prompt=system_prompt,
        session_id=session_id,
        session_store=store,
    )
    context.messages = messages
    return context, meta
