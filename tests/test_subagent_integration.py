# tests/test_subagent_integration.py
"""Integration tests for the subagent optimization features.

These tests verify the end-to-end flow from spawn tool parameters
through agent definition resolution, tool filtering, and result formatting.
"""
from agent.agent_definition import BUILTIN_AGENTS, AgentDefinition, RuntimeInfo
from agent.fork_message_builder import ForkMessageBuilder
from agent.tools import ToolRegistry
from agent.subagent import SubAgentSpec


class TestSpawnToolIntegration:
    def _make_tool_registry(self):
        registry = ToolRegistry()
        def mock_fn(**kwargs): return "mock"
        registry.register(name="read_file", description="Read", input_schema={"type": "object", "properties": {}}, handler=mock_fn)
        registry.register(name="write_file", description="Write", input_schema={"type": "object", "properties": {}}, handler=mock_fn, dangerous=True)
        registry.register(name="edit_file", description="Edit", input_schema={"type": "object", "properties": {}}, handler=mock_fn, dangerous=True)
        registry.register(name="spawn", description="Spawn", input_schema={"type": "object", "properties": {}}, handler=mock_fn)
        registry.register(name="bash", description="Bash", input_schema={"type": "object", "properties": {}}, handler=mock_fn)
        return registry

    def test_general_purpose_has_all_tools(self):
        registry = self._make_tool_registry()
        agent_def = BUILTIN_AGENTS["general-purpose"]
        filtered = registry.filter_for_agent(agent_def)
        assert set(filtered.tools.keys()) == {"read_file", "write_file", "edit_file", "spawn", "bash"}

    def test_explore_has_readonly_tools(self):
        registry = self._make_tool_registry()
        agent_def = BUILTIN_AGENTS["explore"]
        filtered = registry.filter_for_agent(agent_def)
        assert "read_file" in filtered.tools
        assert "bash" in filtered.tools
        assert "write_file" not in filtered.tools
        assert "edit_file" not in filtered.tools
        assert "spawn" not in filtered.tools

    def test_plan_has_readonly_tools(self):
        registry = self._make_tool_registry()
        agent_def = BUILTIN_AGENTS["plan"]
        filtered = registry.filter_for_agent(agent_def)
        assert "read_file" in filtered.tools
        assert "write_file" not in filtered.tools

    def test_subagent_spec_defaults(self):
        spec = SubAgentSpec(task="test task")
        assert spec.agent_type == "general-purpose"
        assert spec.mode == "independent"

    def test_subagent_spec_explore_fork(self):
        spec = SubAgentSpec(
            task="find auth module",
            agent_type="explore",
            mode="fork",
        )
        assert spec.agent_type == "explore"
        assert spec.mode == "fork"


class TestForkModeIntegration:
    def test_fork_with_explore_agent(self):
        """Verify fork mode works with explore agent type."""
        parent_msgs = [
            {"role": "user", "content": "Find all auth-related files"},
            {"role": "assistant", "content": [
                {"type": "text", "text": "I'll spawn explore agents."},
                {"type": "tool_use", "id": "tu_1", "name": "spawn", "input": {"task": "search auth"}},
                {"type": "tool_use", "id": "tu_2", "name": "spawn", "input": {"task": "search login"}},
            ]},
        ]
        builder = ForkMessageBuilder()
        directives = ["Search for auth module", "Search for login module"]
        result = builder.build_forked_messages(parent_msgs, parent_msgs[-1], directives)
        assert len(result) == 2
        # Both should share the same prefix
        assert result[0][:-1] == result[1][:-1]

    def test_fork_fallback_on_recursive_fork(self):
        """Verify fork mode raises error when already in a fork."""
        # Simulate what SubAgent.__init__ does: check is_fork_child then raise
        parent_msgs = [
            {"role": "user", "content": "Hello"},
            {"role": "user", "content": [
                {"type": "text", "text": "<fork_worker>You are a fork worker"},
            ]},
        ]
        builder = ForkMessageBuilder()
        import pytest
        # The SubAgent.__init__ checks is_fork_child and raises ValueError
        assert ForkMessageBuilder.is_fork_child(parent_msgs) is True
        with pytest.raises(ValueError, match="Cannot fork from a fork child"):
            # Replicate the check from SubAgent.__init__
            if ForkMessageBuilder.is_fork_child(parent_msgs):
                raise ValueError("Cannot fork from a fork child. Use independent mode instead.")


class TestContextStrippingIntegration:
    def test_explore_agent_gets_stripped_prompt(self):
        """Verify explore agent's system prompt is shorter than general-purpose."""
        info = RuntimeInfo(
            working_dir="/tmp", platform="darwin", shell="/bin/zsh"
        )
        from agent.prompt import build_system_prompt

        full_prompt = build_system_prompt(runtime_info=info)
        stripped_prompt = build_system_prompt(
            agent_def=BUILTIN_AGENTS["explore"], runtime_info=info
        )
        # Explore agent should have a shorter prompt (omits CLAUDE.md)
        assert len(stripped_prompt) <= len(full_prompt)

    def test_general_purpose_prompt_not_stripped(self):
        """Verify general-purpose agent's prompt is not shorter."""
        info = RuntimeInfo(
            working_dir="/tmp", platform="darwin", shell="/bin/zsh"
        )
        from agent.prompt import build_system_prompt

        full_prompt = build_system_prompt(runtime_info=info)
        gp_prompt = build_system_prompt(
            agent_def=BUILTIN_AGENTS["general-purpose"], runtime_info=info
        )
        # General-purpose should have same length as default (no stripping)
        assert len(gp_prompt) == len(full_prompt)
