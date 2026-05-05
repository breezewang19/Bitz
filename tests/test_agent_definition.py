# tests/test_agent_definition.py
from agent.agent_definition import AgentDefinition, RuntimeInfo, BUILTIN_AGENTS
from agent.prompt import build_system_prompt
from agent.tools import ToolRegistry
from agent.builtin_tools import bash_is_readonly
from agent.adapter import LLMAdapter


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


class TestBuildSystemPromptStripping:
    def test_default_includes_claude_md(self):
        info = RuntimeInfo(
            working_dir="/tmp", platform="darwin", shell="/bin/zsh"
        )
        result = build_system_prompt(runtime_info=info)
        # Default (no agent_def) should produce a non-empty prompt
        assert result  # non-empty
        # Should contain persona/rules at minimum
        assert "工具使用" in result or "环境" in result

    def test_explore_agent_omits_claude_md(self):
        info = RuntimeInfo(
            working_dir="/tmp", platform="darwin", shell="/bin/zsh"
        )
        agent_def = BUILTIN_AGENTS["explore"]
        result_with = build_system_prompt(runtime_info=info)
        result_without = build_system_prompt(agent_def=agent_def, runtime_info=info)
        # Explore agent's prompt should be shorter (omits CLAUDE.md)
        assert len(result_without) <= len(result_with)

    def test_general_purpose_includes_claude_md(self):
        info = RuntimeInfo(
            working_dir="/tmp", platform="darwin", shell="/bin/zsh"
        )
        agent_def = BUILTIN_AGENTS["general-purpose"]
        result = build_system_prompt(agent_def=agent_def, runtime_info=info)
        assert result  # non-empty


class TestToolFiltering:
    def _make_registry_with_tools(self):
        """Create a registry with mock tools for testing."""
        registry = ToolRegistry()

        def mock_fn(**kwargs):
            return "mock"

        registry.register(
            name="read_file",
            description="Read a file",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            handler=mock_fn,
        )
        registry.register(
            name="write_file",
            description="Write a file",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}},
            handler=mock_fn,
            dangerous=True,
        )
        registry.register(
            name="edit_file",
            description="Edit a file",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}}},
            handler=mock_fn,
            dangerous=True,
        )
        registry.register(
            name="spawn",
            description="Spawn subagent",
            input_schema={"type": "object", "properties": {"task": {"type": "string"}}},
            handler=mock_fn,
        )
        return registry

    def test_general_purpose_keeps_all_tools(self):
        registry = self._make_registry_with_tools()
        agent_def = BUILTIN_AGENTS["general-purpose"]
        filtered = registry.filter_for_agent(agent_def)
        assert len(filtered.tools) == 4

    def test_explore_removes_write_tools(self):
        registry = self._make_registry_with_tools()
        agent_def = BUILTIN_AGENTS["explore"]
        filtered = registry.filter_for_agent(agent_def)
        tool_names = set(filtered.tools.keys())
        assert "read_file" in tool_names
        assert "write_file" not in tool_names
        assert "edit_file" not in tool_names
        assert "spawn" not in tool_names

    def test_plan_removes_write_tools(self):
        registry = self._make_registry_with_tools()
        agent_def = BUILTIN_AGENTS["plan"]
        filtered = registry.filter_for_agent(agent_def)
        tool_names = set(filtered.tools.keys())
        assert "read_file" in tool_names
        assert "write_file" not in tool_names


class TestReadonlyPermission:
    def test_ls_is_readonly(self):
        assert bash_is_readonly("ls -la") is True

    def test_cat_is_readonly(self):
        assert bash_is_readonly("cat file.txt") is True

    def test_git_status_is_readonly(self):
        assert bash_is_readonly("git status") is True

    def test_git_log_is_readonly(self):
        assert bash_is_readonly("git log --oneline") is True

    def test_grep_is_readonly(self):
        assert bash_is_readonly("grep -r 'pattern' src/") is True

    def test_find_is_readonly(self):
        assert bash_is_readonly("find . -name '*.py'") is True

    def test_rm_is_not_readonly(self):
        assert bash_is_readonly("rm -rf /tmp/test") is False

    def test_pip_install_is_not_readonly(self):
        assert bash_is_readonly("pip install requests") is False

    def test_python_is_not_readonly(self):
        assert bash_is_readonly("python script.py") is False

    def test_git_push_is_not_readonly(self):
        assert bash_is_readonly("git push") is False

    def test_git_checkout_is_not_readonly(self):
        assert bash_is_readonly("git checkout -b new-branch") is False

    def test_empty_command_is_readonly(self):
        assert bash_is_readonly("") is True

    def test_echo_redirect_is_not_readonly(self):
        assert bash_is_readonly("echo 'test' > file.txt") is False

    def test_export_is_not_readonly(self):
        assert bash_is_readonly("export FOO=bar") is False

    def test_semicolon_is_not_readonly(self):
        assert bash_is_readonly("ls; rm -rf /") is False

    def test_command_substitution_is_not_readonly(self):
        assert bash_is_readonly("echo $(cat /etc/passwd)") is False


class TestLLMAdapterCacheControl:
    def test_system_prompt_with_cache_control(self):
        """Verify system prompt is sent as content blocks with cache_control."""
        adapter = LLMAdapter(api_key="test-key")
        blocks = adapter._build_system_prompt_blocks("Hello world")
        assert isinstance(blocks, list)
        assert len(blocks) >= 1
        # Last block should have cache_control
        last_block = blocks[-1]
        assert last_block.get("cache_control") == {"type": "ephemeral"}

    def test_system_prompt_blocks_are_text_type(self):
        adapter = LLMAdapter(api_key="test-key")
        blocks = adapter._build_system_prompt_blocks("Test prompt")
        for block in blocks:
            assert block["type"] == "text"

    def test_client_reuse(self):
        """Verify the Anthropic client is reused across calls."""
        from unittest.mock import MagicMock
        adapter = LLMAdapter(api_key="test-key")
        mock_client = MagicMock()
        adapter._client = mock_client
        client1 = adapter._get_client()
        client2 = adapter._get_client()
        assert client1 is client2
        assert client1 is mock_client
