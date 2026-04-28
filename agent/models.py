"""模型配置管理 — 持久化到 ~/.bitz/models.json"""
import json
import os
import stat
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class ModelConfig:
    id: str           # 用户标识，如 "gpt-4o"
    protocol: str     # "openai" | "anthropic"
    base_url: str
    api_key: str
    model: str        # API 实际模型名

    def __post_init__(self):
        if self.protocol not in ("openai", "anthropic"):
            raise ValueError(f"不支持的协议: {self.protocol}，可选: openai, anthropic")

    def masked_key(self) -> str:
        key = self.api_key
        if len(key) <= 7:
            return key[:3] + "***"
        return key[:4] + "..." + key[-3:]


class ModelStore:
    """Placeholder — full implementation in Task 2"""
    pass
