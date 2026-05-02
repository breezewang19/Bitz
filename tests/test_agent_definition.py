# tests/test_agent_definition.py
import pytest
from agent.agent_definition import AgentDefinition, RuntimeInfo, BUILTIN_AGENTS


class TestRuntimeInfo:
    def test_create_runtime_info(self):
        info = RuntimeInfo(
            working_dir="/tmp",
            platform="darwin",
            shell="/bin/zsh",
            skill_summary="test skills",
        )
        assert info.working_dir == "/tmp"
        assert info.platform == "darwin"
        assert info.shell == "/bin/zsh"
        assert info.skill_summary == "test skills"

    def test_skill_summary_optional(self):
        info = RuntimeInfo(
            working_dir="/tmp", platform="darwin", shell="/bin/zsh"
        )
        assert info.skill_summary is None


class TestAgentDefinition:
    def test_create_minimal_definition(self):
        defn = AgentDefinition(
            name="test-agent",
            description="A test agent",
            disallowed_tools=[],
        )
        assert defn.name == "test-agent"
        assert defn.description == "A test agent"
        assert defn.disallowed_tools == []
        assert defn.model is None
        assert defn.get_system_prompt is None
        assert defn.omit_claude_md is False
        assert defn.max_steps == 10
        assert defn.permission_mode == "auto"

    def test_create_full_definition(self):
        def prompt_fn(info):
            return f"Custom prompt for {info.working_dir}"

        defn = AgentDefinition(
            name="custom",
            description="Custom agent",
            disallowed_tools=["write_file", "edit_file"],
            model="claude-haiku-4-5-20251001",
            get_system_prompt=prompt_fn,
            omit_claude_md=True,
            max_steps=5,
            permission_mode="readonly",
        )
        assert defn.model == "claude-haiku-4-5-20251001"
        assert defn.get_system_prompt is not None
        assert defn.omit_claude_md is True
        assert defn.max_steps == 5
        assert defn.permission_mode == "readonly"

    def test_get_system_prompt_called_with_runtime_info(self):
        def prompt_fn(info):
            return f"Working in {info.working_dir}"

        defn = AgentDefinition(
            name="test", description="test", disallowed_tools=[],
            get_system_prompt=prompt_fn,
        )
        info = RuntimeInfo(
            working_dir="/home", platform="linux", shell="/bin/bash"
        )
        result = defn.get_system_prompt(info)
        assert result == "Working in /home"


class TestBuiltinAgents:
    def test_general_purpose_exists(self):
        assert "general-purpose" in BUILTIN_AGENTS

    def test_explore_exists(self):
        assert "explore" in BUILTIN_AGENTS

    def test_plan_exists(self):
        assert "plan" in BUILTIN_AGENTS

    def test_general_purpose_allows_all_tools(self):
        agent = BUILTIN_AGENTS["general-purpose"]
        assert agent.disallowed_tools == []
        assert agent.permission_mode == "auto"
        assert agent.omit_claude_md is False

    def test_explore_disallows_write_tools(self):
        agent = BUILTIN_AGENTS["explore"]
        assert "write_file" in agent.disallowed_tools
        assert "edit_file" in agent.disallowed_tools
        assert "spawn" in agent.disallowed_tools
        assert agent.permission_mode == "readonly"
        assert agent.omit_claude_md is True

    def test_plan_disallows_write_tools(self):
        agent = BUILTIN_AGENTS["plan"]
        assert "write_file" in agent.disallowed_tools
        assert "edit_file" in agent.disallowed_tools
        assert "spawn" in agent.disallowed_tools
        assert agent.permission_mode == "readonly"
        assert agent.omit_claude_md is True

    def test_all_builtins_have_required_fields(self):
        for name, agent in BUILTIN_AGENTS.items():
            assert agent.name == name
            assert isinstance(agent.description, str)
            assert isinstance(agent.disallowed_tools, list)
            assert agent.permission_mode in ("auto", "readonly")
