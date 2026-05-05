from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ExecutionContext:
    session_id: str
    task_base_dir: str | None = None
    agent: Any = None
    on_event: Callable | None = None
    extra: dict[str, Any] = field(default_factory=dict)
