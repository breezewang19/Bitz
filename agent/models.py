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
    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or Path.home() / ".bitz" / "models.json"
        self._data: dict | None = None

    def _load(self) -> dict:
        if self._data is not None:
            return self._data
        if self.config_path.exists():
            self._data = json.loads(self.config_path.read_text(encoding="utf-8"))
        else:
            self._data = {"models": [], "current": None}
        return self._data

    def _save(self, data: dict) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        if os.name != "nt":
            self.config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        self._data = data

    def init_from_env(self) -> ModelConfig:
        """从 .env 环境变量种子初始化（仅首次启动时创建默认模型）"""
        data = self._load()
        if not data["models"]:
            config = ModelConfig(
                id="default",
                protocol="anthropic",
                base_url=os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
                api_key=os.getenv("ANTHROPIC_API_KEY", ""),
                model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
            )
            data["models"].append(asdict(config))
            data["current"] = "default"
            self._save(data)
            return config
        current = self.get_current()
        if current:
            return current
        first = self.get(data["models"][0]["id"])
        if first:
            self.set_current(first.id)
        return first

    def add(self, config: ModelConfig) -> None:
        data = self._load()
        if any(m["id"] == config.id for m in data["models"]):
            raise ValueError(f"模型 ID '{config.id}' 已存在")
        data["models"].append(asdict(config))
        self._save(data)

    def list_all(self) -> list[ModelConfig]:
        data = self._load()
        return [ModelConfig(**m) for m in data["models"]]

    def get(self, id: str) -> ModelConfig | None:
        data = self._load()
        for m in data["models"]:
            if m["id"] == id:
                return ModelConfig(**m)
        return None

    def get_current(self) -> ModelConfig | None:
        data = self._load()
        current_id = data.get("current")
        if current_id:
            return self.get(current_id)
        return None

    def set_current(self, id: str) -> None:
        if self.get(id) is None:
            raise ValueError(f"模型 '{id}' 不存在")
        data = self._load()
        data["current"] = id
        self._save(data)
