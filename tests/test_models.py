"""Tests for ModelConfig and ModelStore"""
import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch
from agent.models import ModelConfig, ModelStore


class TestModelConfig:
    def test_create_config(self):
        config = ModelConfig(
            id="gpt-4o",
            protocol="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            model="gpt-4o",
        )
        assert config.id == "gpt-4o"
        assert config.protocol == "openai"

    def test_invalid_protocol_raises(self):
        with pytest.raises(ValueError):
            ModelConfig(
                id="bad",
                protocol="invalid",
                base_url="https://example.com",
                api_key="key",
                model="m",
            )


class TestModelStore:
    def test_init_from_env(self, tmp_path):
        """从环境变量种子初始化"""
        config_path = tmp_path / "models.json"
        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "sk-test-key",
            "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
            "ANTHROPIC_MODEL": "claude-3-5-sonnet-20241022",
        }):
            store = ModelStore(config_path=config_path)
            config = store.init_from_env()
        assert config.id == "default"
        assert config.protocol == "anthropic"
        assert config.model == "claude-3-5-sonnet-20241022"
        # 持久化验证
        assert config_path.exists()
        data = json.loads(config_path.read_text())
        assert data["current"] == "default"
        assert len(data["models"]) == 1

    def test_add_and_list(self, tmp_path):
        """添加模型并列出"""
        config_path = tmp_path / "models.json"
        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "sk-test",
            "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
            "ANTHROPIC_MODEL": "claude-3-5-sonnet-20241022",
        }):
            store = ModelStore(config_path=config_path)
            store.init_from_env()

        store.add(ModelConfig(
            id="gpt-4o", protocol="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-openai", model="gpt-4o",
        ))
        models = store.list_all()
        assert len(models) == 2
        assert models[1].id == "gpt-4o"

    def test_get_by_id(self, tmp_path):
        """按 ID 获取模型"""
        config_path = tmp_path / "models.json"
        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "sk-test",
            "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
            "ANTHROPIC_MODEL": "claude-3-5-sonnet-20241022",
        }):
            store = ModelStore(config_path=config_path)
            store.init_from_env()

        result = store.get("default")
        assert result is not None
        assert result.protocol == "anthropic"
        assert store.get("nonexistent") is None

    def test_set_current(self, tmp_path):
        """切换当前模型"""
        config_path = tmp_path / "models.json"
        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "sk-test",
            "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
            "ANTHROPIC_MODEL": "claude-3-5-sonnet-20241022",
        }):
            store = ModelStore(config_path=config_path)
            store.init_from_env()

        store.add(ModelConfig(
            id="gpt-4o", protocol="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-openai", model="gpt-4o",
        ))
        store.set_current("gpt-4o")
        current = store.get_current()
        assert current.id == "gpt-4o"

    def test_set_current_nonexistent_raises(self, tmp_path):
        """切换到不存在的模型应报错"""
        config_path = tmp_path / "models.json"
        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "sk-test",
            "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
            "ANTHROPIC_MODEL": "claude-3-5-sonnet-20241022",
        }):
            store = ModelStore(config_path=config_path)
            store.init_from_env()

        with pytest.raises(ValueError, match="不存在"):
            store.set_current("nonexistent")

    def test_add_duplicate_id_raises(self, tmp_path):
        """添加重复 ID 应报错"""
        config_path = tmp_path / "models.json"
        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "sk-test",
            "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
            "ANTHROPIC_MODEL": "claude-3-5-sonnet-20241022",
        }):
            store = ModelStore(config_path=config_path)
            store.init_from_env()

        with pytest.raises(ValueError, match="已存在"):
            store.add(ModelConfig(
                id="default", protocol="anthropic",
                base_url="https://api.anthropic.com",
                api_key="sk-test", model="claude-3-5-sonnet-20241022",
            ))

    def test_load_existing_file(self, tmp_path):
        """从已有文件加载"""
        config_path = tmp_path / "models.json"
        data = {
            "models": [
                {"id": "default", "protocol": "anthropic", "base_url": "https://api.anthropic.com", "api_key": "sk-test", "model": "claude-3-5-sonnet-20241022"},
                {"id": "gpt-4o", "protocol": "openai", "base_url": "https://api.openai.com/v1", "api_key": "sk-openai", "model": "gpt-4o"},
            ],
            "current": "gpt-4o",
        }
        config_path.write_text(json.dumps(data))
        store = ModelStore(config_path=config_path)
        current = store.get_current()
        assert current.id == "gpt-4o"
        assert len(store.list_all()) == 2

    def test_file_permissions(self, tmp_path):
        """验证文件权限为 0600"""
        config_path = tmp_path / "models.json"
        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "sk-test",
            "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
            "ANTHROPIC_MODEL": "claude-3-5-sonnet-20241022",
        }):
            store = ModelStore(config_path=config_path)
            store.init_from_env()
        if os.name != "nt":
            mode = config_path.stat().st_mode & 0o777
            assert mode == 0o600

    def test_mask_api_key(self, tmp_path):
        """验证 API key 脱敏"""
        config_path = tmp_path / "models.json"
        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "sk-ant-longkey123",
            "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
            "ANTHROPIC_MODEL": "claude-3-5-sonnet-20241022",
        }):
            store = ModelStore(config_path=config_path)
            store.init_from_env()
        config = store.get("default")
        assert config.masked_key() == "sk-a...123"
