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
