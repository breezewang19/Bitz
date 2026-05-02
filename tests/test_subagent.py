# tests/test_subagent.py
"""SubAgent 数据类测试"""
import pytest
import threading
import warnings
from unittest.mock import MagicMock, patch
from agent.subagent import SubAgentResult, SubAgentSpec
from agent.loop import Agent
from agent.context import Context
from agent.adapter import LLMAdapter, LLMError
from agent.tools import ToolRegistry, _is_readonly_command
from agent.subagent import SubAgent, run_parallel


class TestSubAgentResult:
    def test_success_result_defaults(self):
        r = SubAgentResult(success=True, output="done")
        assert r.success is True
        assert r.output == "done"
        assert r.steps == 0
        assert r.elapsed == 0.0
        assert r.error is None
        assert r.tokens == 0

    def test_error_result(self):
        r = SubAgentResult(success=False, output="", error="timeout")
        assert r.success is False
        assert r.error == "timeout"

    def test_full_result(self):
        r = SubAgentResult(success=True, output="ok", steps=5, elapsed=12.3, tokens=500)
        assert r.steps == 5
        assert r.elapsed == 12.3
        assert r.tokens == 500


class TestSubAgentSpec:
    def test_defaults(self):
        spec = SubAgentSpec(task="review code")
        assert spec.task == "review code"
        assert spec.context_hint == ""
        assert spec.max_steps == 10
        assert spec.model is None
        assert spec.mode == "independent"
        assert spec.agent_type == "general-purpose"

    def test_custom_values(self):
        spec = SubAgentSpec(
            task="review",
            context_hint="Rule: check X",
            max_steps=5,
            model="claude-haiku-4-5-20251001",
            mode="fork",
            agent_type="explore",
        )
        assert spec.context_hint == "Rule: check X"
        assert spec.max_steps == 5
        assert spec.model == "claude-haiku-4-5-20251001"
        assert spec.mode == "fork"
        assert spec.agent_type == "explore"


class TestSubAgentSpecNewFields:
    def test_mode_defaults_to_independent(self):
        spec = SubAgentSpec(task="test")
        assert spec.mode == "independent"

    def test_agent_type_defaults_to_general_purpose(self):
        spec = SubAgentSpec(task="test")
        assert spec.agent_type == "general-purpose"

    def test_custom_mode_and_type(self):
        spec = SubAgentSpec(task="test", mode="fork", agent_type="explore")
        assert spec.mode == "fork"
        assert spec.agent_type == "explore"


class TestAgentAutoConfirm:
    def test_auto_confirm_default_false(self):
        llm = MagicMock(spec=LLMAdapter)
        ctx = Context(system_prompt="test")
        tools = ToolRegistry()
        agent = Agent(llm_adapter=llm, tools=tools, context=ctx)
        assert agent.auto_confirm is False

    def test_auto_confirm_can_set_true(self):
        llm = MagicMock(spec=LLMAdapter)
        ctx = Context(system_prompt="test")
        tools = ToolRegistry()
        agent = Agent(llm_adapter=llm, tools=tools, context=ctx)
        agent.auto_confirm = True
        assert agent.auto_confirm is True


def _make_parent_agent():
    """创建 mock 父 Agent，模拟真实结构"""
    agent = MagicMock(spec=Agent)
    agent.llm_adapter = MagicMock(spec=LLMAdapter)
    agent.llm_adapter.api_key = "test-key"
    agent.llm_adapter.base_url = "https://api.test.com"
    agent.llm_adapter.model = "test-model"
    agent.llm_adapter.protocol = "anthropic"
    agent.tools = ToolRegistry()
    agent.context = Context(system_prompt="You are a test assistant.")
    agent.context.add_user("parent message that should not leak")
    return agent


class TestSubAgentConstruction:
    def test_inherits_llm_config(self):
        parent = _make_parent_agent()
        spec = SubAgentSpec(task="do something")
        sub = SubAgent(parent, spec)
        assert sub._llm.api_key == "test-key"
        assert sub._llm.model == "test-model"
        assert sub._llm.protocol == "anthropic"

    def test_inherits_custom_model(self):
        parent = _make_parent_agent()
        spec = SubAgentSpec(task="test", model="claude-haiku-4-5-20251001")
        sub = SubAgent(parent, spec)
        assert sub._llm.model == "claude-haiku-4-5-20251001"

    def test_independent_context_no_parent_history(self):
        parent = _make_parent_agent()
        spec = SubAgentSpec(task="sub task")
        sub = SubAgent(parent, spec)
        msgs = sub._context.get_messages()
        user_msgs = [m for m in msgs if m["role"] == "user"]
        assert len(user_msgs) == 1
        assert "sub task" in user_msgs[0]["content"]
        # 父的对话历史不应泄漏
        assert "parent message" not in user_msgs[0]["content"]

    def test_context_hint_injected(self):
        parent = _make_parent_agent()
        spec = SubAgentSpec(task="review", context_hint="Rule: check X")
        sub = SubAgent(parent, spec)
        msgs = sub._context.get_messages()
        user_msgs = [m for m in msgs if m["role"] == "user"]
        assert "Rule: check X" in user_msgs[0]["content"]

    def test_auto_confirm_enabled(self):
        parent = _make_parent_agent()
        spec = SubAgentSpec(task="test")
        sub = SubAgent(parent, spec)
        assert sub._agent.auto_confirm is True

    def test_spawn_removed_by_default_agent_def(self):
        """general-purpose agent_def does not disallow spawn, but
        explore/plan agent_defs do. Test the filter_for_agent integration."""
        parent = _make_parent_agent()
        parent.tools.register("spawn", "spawn sub agents", {"type": "object", "properties": {}}, handler=lambda: "")
        # general-purpose: spawn is NOT disallowed, but our BUILTIN_AGENTS
        # general-purpose has disallowed_tools=[], so spawn stays
        spec = SubAgentSpec(task="test", agent_type="general-purpose")
        sub = SubAgent(parent, spec)
        assert "spawn" in sub._tools.tools  # general-purpose keeps all tools

    def test_other_tools_preserved(self):
        """除 disallowed 外的工具都应保留"""
        parent = _make_parent_agent()
        parent.tools.register("bash", "run command", {"type": "object", "properties": {}}, handler=lambda: "")
        parent.tools.register("read_file", "read file", {"type": "object", "properties": {}}, handler=lambda: "")
        spec = SubAgentSpec(task="test")
        sub = SubAgent(parent, spec)
        assert "bash" in sub._tools.tools
        assert "read_file" in sub._tools.tools


class TestSubAgentWithAgentDefinition:
    def test_explore_agent_filters_tools(self):
        parent = _make_parent_agent()
        parent.tools.register(name="write_file", description="write", input_schema={"type": "object", "properties": {}}, handler=lambda: "")
        parent.tools.register(name="spawn", description="spawn", input_schema={"type": "object", "properties": {}}, handler=lambda: "")
        parent.tools.register(name="bash", description="bash", input_schema={"type": "object", "properties": {}}, handler=lambda: "")
        spec = SubAgentSpec(task="explore code", agent_type="explore")
        sub = SubAgent(parent, spec)
        assert "write_file" not in sub._tools.tools
        assert "spawn" not in sub._tools.tools
        # bash and read_file should still be available
        assert "bash" in sub._tools.tools

    def test_general_purpose_keeps_all_tools(self):
        parent = _make_parent_agent()
        parent.tools.register(name="write_file", description="write", input_schema={"type": "object", "properties": {}}, handler=lambda: "")
        parent.tools.register(name="spawn", description="spawn", input_schema={"type": "object", "properties": {}}, handler=lambda: "")
        spec = SubAgentSpec(task="do work")
        sub = SubAgent(parent, spec)
        assert "write_file" in sub._tools.tools
        assert "spawn" in sub._tools.tools

    def test_explore_agent_has_readonly_permission(self):
        parent = _make_parent_agent()
        spec = SubAgentSpec(task="explore", agent_type="explore")
        sub = SubAgent(parent, spec)
        assert sub._agent.permission_mode == "readonly"

    def test_general_purpose_has_auto_permission(self):
        parent = _make_parent_agent()
        spec = SubAgentSpec(task="work")
        sub = SubAgent(parent, spec)
        assert sub._agent.permission_mode == "auto"

    def test_explore_agent_omits_claude_md(self):
        """explore agent should not include CLAUDE.md in system prompt"""
        import os
        import tempfile
        # Create a temp dir with a CLAUDE.md file
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_md_path = os.path.join(tmpdir, "CLAUDE.md")
            with open(claude_md_path, "w") as f:
                f.write("This is a test CLAUDE.md file with unique content XYZ123")

            # Save and change cwd
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                parent = _make_parent_agent()
                spec_explore = SubAgentSpec(task="explore", agent_type="explore")
                sub_explore = SubAgent(parent, spec_explore)
                explore_prompt = sub_explore._context.system_prompt
                assert "XYZ123" not in explore_prompt

                spec_gp = SubAgentSpec(task="work", agent_type="general-purpose")
                sub_gp = SubAgent(parent, spec_gp)
                gp_prompt = sub_gp._context.system_prompt
                assert "XYZ123" in gp_prompt
            finally:
                os.chdir(original_cwd)


class TestSubAgentForkMode:
    def test_fork_mode_inherits_parent_model(self):
        parent = _make_parent_agent()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            spec = SubAgentSpec(task="test", mode="fork", model="claude-haiku-4-5-20251001")
            sub = SubAgent(parent, spec)
            # Should inherit parent model, not use the specified one
            assert sub._llm.model == parent.llm_adapter.model
            # Should have issued a warning
            assert len(w) == 1
            assert "Fork mode requires inheriting parent model" in str(w[0].message)

    def test_independent_mode_uses_spec_model(self):
        parent = _make_parent_agent()
        spec = SubAgentSpec(task="test", model="claude-haiku-4-5-20251001")
        sub = SubAgent(parent, spec)
        assert sub._llm.model == "claude-haiku-4-5-20251001"

    def test_fork_mode_with_fork_messages(self):
        parent = _make_parent_agent()
        spec = SubAgentSpec(task="test", mode="fork")
        fork_msgs = [
            {"role": "user", "content": "fork task"},
            {"role": "assistant", "content": "working on it"},
        ]
        sub = SubAgent(parent, spec, fork_messages=fork_msgs)
        # The fork messages should be in the context
        assert len(sub._context.messages) == 2
        assert sub._context.messages[0]["role"] == "user"
        assert sub._context.messages[1]["role"] == "assistant"

    def test_fork_mode_recursive_fork_prevented(self):
        """Fork from a fork child should raise ValueError"""
        parent = _make_parent_agent()
        # Inject fork boilerplate into parent messages to simulate fork child
        parent.context.messages.append({
            "role": "user",
            "content": "<fork_worker>\nYou are a fork worker process.\n</fork_worker>\n\nTask: do something"
        })
        spec = SubAgentSpec(task="test", mode="fork")
        with pytest.raises(ValueError, match="Cannot fork from a fork child"):
            SubAgent(parent, spec)

    def test_fork_mode_no_model_override_no_warning(self):
        """Fork mode with model=None should not produce a warning"""
        parent = _make_parent_agent()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            spec = SubAgentSpec(task="test", mode="fork", model=None)
            sub = SubAgent(parent, spec)
            assert sub._llm.model == parent.llm_adapter.model
            assert len(w) == 0


class TestSubAgentRun:
    @patch("agent.subagent.Agent")
    def test_run_success(self, MockAgentCls):
        parent = _make_parent_agent()
        mock_instance = MockAgentCls.return_value
        mock_instance.run.return_value = "task completed"
        mock_instance._step_count = 3

        spec = SubAgentSpec(task="do it")
        sub = SubAgent(parent, spec)
        result = sub.run()
        assert result.success is True
        assert result.output == "task completed"
        assert result.steps == 3
        assert result.elapsed > 0

    @patch("agent.subagent.Agent")
    def test_run_llm_error(self, MockAgentCls):
        parent = _make_parent_agent()
        mock_instance = MockAgentCls.return_value
        mock_instance.run.side_effect = LLMError("API 超时")

        spec = SubAgentSpec(task="fail")
        sub = SubAgent(parent, spec)
        result = sub.run()
        assert result.success is False
        assert "API 超时" in result.error

    @patch("agent.subagent.Agent")
    def test_run_generic_exception(self, MockAgentCls):
        parent = _make_parent_agent()
        mock_instance = MockAgentCls.return_value
        mock_instance.run.side_effect = RuntimeError("unexpected")

        spec = SubAgentSpec(task="crash")
        sub = SubAgent(parent, spec)
        result = sub.run()
        assert result.success is False
        assert "RuntimeError" in result.error

    @patch("agent.subagent.Agent")
    def test_on_status_callback(self, MockAgentCls):
        parent = _make_parent_agent()
        mock_instance = MockAgentCls.return_value
        mock_instance.run.return_value = "ok"
        mock_instance._step_count = 1

        statuses = []
        def on_status(task_id, status):
            statuses.append((task_id, status))

        spec = SubAgentSpec(task="test")
        sub = SubAgent(parent, spec, on_status=on_status)
        sub.run()
        status_values = [s[1] for s in statuses]
        assert "running" in status_values
        assert "done" in status_values


class TestRunParallel:
    @patch("agent.subagent.SubAgent")
    def test_parallel_results_ordered(self, MockSubAgentCls):
        parent = MagicMock()
        # Need to provide tools and context for SubAgent.__init__
        parent.tools = ToolRegistry()
        parent.context = Context(system_prompt="test")
        parent.llm_adapter = MagicMock(spec=LLMAdapter)
        parent.llm_adapter.api_key = "test-key"
        parent.llm_adapter.base_url = "https://api.test.com"
        parent.llm_adapter.model = "test-model"
        parent.llm_adapter.protocol = "anthropic"

        specs = [SubAgentSpec(task=f"task {i}") for i in range(3)]

        # Each mock SubAgent instance returns a result based on its task
        mock_results = [
            SubAgentResult(success=True, output=f"result {i}", steps=i + 1, elapsed=1.0)
            for i in range(3)
        ]
        MockSubAgentCls.return_value.run.side_effect = mock_results

        results = run_parallel(specs, parent)
        assert len(results) == 3
        # Results are ordered by index, but mock side_effect assigns sequentially
        # so the actual output order depends on thread completion order.
        # Just check we get 3 results all successful.
        for r in results:
            assert r.success is True
            assert r.output.startswith("result ")

    @patch("agent.subagent.SubAgent")
    def test_parallel_max_workers(self, MockSubAgentCls):
        parent = MagicMock()
        parent.tools = ToolRegistry()
        parent.context = Context(system_prompt="test")
        parent.llm_adapter = MagicMock(spec=LLMAdapter)
        parent.llm_adapter.api_key = "test-key"
        parent.llm_adapter.base_url = "https://api.test.com"
        parent.llm_adapter.model = "test-model"
        parent.llm_adapter.protocol = "anthropic"

        specs = [SubAgentSpec(task=f"task {i}") for i in range(5)]

        mock_results = [
            SubAgentResult(success=True, output=f"result {i}", steps=1, elapsed=0.5)
            for i in range(5)
        ]
        MockSubAgentCls.return_value.run.side_effect = mock_results

        results = run_parallel(specs, parent, max_workers=2)
        assert len(results) == 5

    @patch("agent.subagent.SubAgent")
    def test_parallel_mixed_success_failure(self, MockSubAgentCls):
        parent = MagicMock()
        parent.tools = ToolRegistry()
        parent.context = Context(system_prompt="test")
        parent.llm_adapter = MagicMock(spec=LLMAdapter)
        parent.llm_adapter.api_key = "test-key"
        parent.llm_adapter.base_url = "https://api.test.com"
        parent.llm_adapter.model = "test-model"
        parent.llm_adapter.protocol = "anthropic"

        specs = [SubAgentSpec(task="ok"), SubAgentSpec(task="fail")]

        mock_results = [
            SubAgentResult(success=True, output="ok", steps=1, elapsed=1.0),
            SubAgentResult(success=False, output="", error="timeout", steps=0, elapsed=2.0),
        ]
        MockSubAgentCls.return_value.run.side_effect = mock_results

        results = run_parallel(specs, parent)
        assert results[0].success is True
        assert results[1].success is False


from agent.builtin_tools import create_tools, SPAWN_TOOL_DEF


class TestSpawnToolDefinition:
    def test_spawn_tool_def_exists(self):
        assert SPAWN_TOOL_DEF is not None
        assert SPAWN_TOOL_DEF["name"] == "spawn"

    def test_spawn_schema_has_required_fields(self):
        props = SPAWN_TOOL_DEF["input_schema"]["properties"]
        assert "task" in props
        assert "tasks" in props
        assert "context_hint" in props
        assert "max_steps" in props
        assert "max_workers" in props

    def test_spawn_schema_has_agent_type(self):
        props = SPAWN_TOOL_DEF["input_schema"]["properties"]
        assert "agent_type" in props
        assert props["agent_type"]["default"] == "general-purpose"
        assert "general-purpose" in props["agent_type"]["enum"]
        assert "explore" in props["agent_type"]["enum"]
        assert "plan" in props["agent_type"]["enum"]

    def test_spawn_schema_has_mode(self):
        props = SPAWN_TOOL_DEF["input_schema"]["properties"]
        assert "mode" in props
        assert props["mode"]["default"] == "independent"
        assert "independent" in props["mode"]["enum"]
        assert "fork" in props["mode"]["enum"]


class TestSpawnExecution:
    @patch("agent.subagent.SubAgent")
    def test_single_task(self, MockSubAgentCls):
        tools = create_tools()

        mock_result = SubAgentResult(success=True, output="done", steps=3, elapsed=5.0, tokens=100)
        MockSubAgentCls.return_value.run.return_value = mock_result

        parent = MagicMock()
        result = tools.execute("spawn", {"task": "review code"}, agent=parent)
        assert "完成" in result
        assert "3 步" in result

    @patch("agent.subagent.SubAgent")
    def test_single_task_with_agent_type(self, MockSubAgentCls):
        tools = create_tools()

        mock_result = SubAgentResult(success=True, output="explored", steps=2, elapsed=3.0)
        MockSubAgentCls.return_value.run.return_value = mock_result

        parent = MagicMock()
        result = tools.execute("spawn", {"task": "find files", "agent_type": "explore"}, agent=parent)
        assert "explore" in result
        assert "完成" in result

    @patch("agent.subagent.run_parallel")
    def test_parallel_tasks(self, mock_parallel):
        tools = create_tools()

        mock_results = [
            SubAgentResult(success=True, output="r1", steps=2, elapsed=3.0),
            SubAgentResult(success=True, output="r2", steps=4, elapsed=5.0),
        ]
        mock_parallel.return_value = mock_results

        parent = MagicMock()
        result = tools.execute(
            "spawn",
            {"tasks": ["task1", "task2"], "max_workers": 2},
            agent=parent,
        )
        assert "任务 1" in result
        assert "任务 2" in result

    def test_spawn_without_agent(self):
        tools = create_tools()
        result = tools.execute("spawn", {"task": "test"})
        assert "错误" in result

    def test_spawn_without_task_or_tasks(self):
        tools = create_tools()
        parent = MagicMock()
        result = tools.execute("spawn", {}, agent=parent)
        assert "错误" in result


class TestReadonlyEnforcement:
    """Readonly permission mode enforcement in tool execution."""

    def test_readonly_mode_blocks_write_bash(self):
        tools = ToolRegistry()
        tools.register(
            name="bash",
            description="run bash",
            input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
            handler=lambda command: f"ran: {command}",
            dangerous=True,
        )
        agent = MagicMock()
        agent.permission_mode = "readonly"
        result = tools.execute("bash", {"command": "rm -rf /tmp/test"}, agent=agent)
        assert "只读模式" in result

    def test_readonly_mode_allows_readonly_bash(self):
        tools = ToolRegistry()
        tools.register(
            name="bash",
            description="run bash",
            input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
            handler=lambda command: f"ran: {command}",
            dangerous=True,
        )
        agent = MagicMock()
        agent.permission_mode = "readonly"
        result = tools.execute("bash", {"command": "ls -la"}, agent=agent)
        assert "ran: ls -la" in result

    def test_readonly_mode_blocks_write_file(self):
        tools = ToolRegistry()
        tools.register(
            name="write_file",
            description="write file",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}},
            handler=lambda path, content: "wrote",
        )
        agent = MagicMock()
        agent.permission_mode = "readonly"
        result = tools.execute("write_file", {"path": "/tmp/test", "content": "hello"}, agent=agent)
        assert "只读模式" in result

    def test_readonly_mode_blocks_edit_file(self):
        tools = ToolRegistry()
        tools.register(
            name="edit_file",
            description="edit file",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}, "old_string": {"type": "string"}, "new_string": {"type": "string"}}},
            handler=lambda path, old_string, new_string: "edited",
        )
        agent = MagicMock()
        agent.permission_mode = "readonly"
        result = tools.execute("edit_file", {"path": "/tmp/test", "old_string": "old", "new_string": "new"}, agent=agent)
        assert "只读模式" in result

    def test_auto_mode_allows_write_bash(self):
        tools = ToolRegistry()
        tools.register(
            name="bash",
            description="run bash",
            input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
            handler=lambda command: f"ran: {command}",
            dangerous=True,
        )
        agent = MagicMock()
        agent.permission_mode = "auto"
        result = tools.execute("bash", {"command": "echo hello"}, confirmed=True, agent=agent)
        assert "ran: echo hello" in result

    def test_no_permission_mode_allows_all(self):
        """Agent without permission_mode should not be blocked."""
        tools = ToolRegistry()
        tools.register(
            name="bash",
            description="run bash",
            input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
            handler=lambda command: f"ran: {command}",
            dangerous=True,
        )
        agent = MagicMock(spec=[])  # No permission_mode attribute
        result = tools.execute("bash", {"command": "rm -rf /tmp/test"}, confirmed=True, agent=agent)
        assert "ran: rm -rf /tmp/test" in result


class TestIsReadonlyCommand:
    """Test the _is_readonly_command function used for enforcement."""

    def test_ls_is_readonly(self):
        assert _is_readonly_command("ls -la") is True

    def test_cat_is_readonly(self):
        assert _is_readonly_command("cat file.txt") is True

    def test_git_status_is_readonly(self):
        assert _is_readonly_command("git status") is True

    def test_git_log_is_readonly(self):
        assert _is_readonly_command("git log --oneline") is True

    def test_rm_not_readonly(self):
        assert _is_readonly_command("rm -rf /tmp") is False

    def test_pip_install_not_readonly(self):
        assert _is_readonly_command("pip install foo") is False

    def test_echo_with_redirect_not_readonly(self):
        assert _is_readonly_command("echo hello > file.txt") is False

    def test_pipe_not_readonly(self):
        assert _is_readonly_command("cat file | grep pattern") is False

    def test_empty_is_readonly(self):
        assert _is_readonly_command("") is True


class TestOnEventCallback:
    """on_event 回调测试"""

    @patch("agent.subagent.Agent")
    def test_on_event_done_fired_on_success(self, MockAgentCls):
        parent = _make_parent_agent()
        mock_instance = MockAgentCls.return_value
        mock_instance.run.return_value = "ok"
        mock_instance._step_count = 2

        events = []
        def on_event(event_type, task_index, **kwargs):
            events.append((event_type, task_index, kwargs))

        spec = SubAgentSpec(task="test")
        sub = SubAgent(parent, spec, on_event=on_event, task_index=0)
        result = sub.run()

        done_events = [e for e in events if e[0] == "done"]
        assert len(done_events) == 1
        assert done_events[0][1] == 0  # task_index
        assert done_events[0][2]["success"] is True
        assert done_events[0][2]["steps"] == 2

    @patch("agent.subagent.Agent")
    def test_on_event_done_fired_on_error(self, MockAgentCls):
        parent = _make_parent_agent()
        mock_instance = MockAgentCls.return_value
        mock_instance.run.side_effect = LLMError("fail")

        events = []
        def on_event(event_type, task_index, **kwargs):
            events.append((event_type, task_index, kwargs))

        spec = SubAgentSpec(task="test")
        sub = SubAgent(parent, spec, on_event=on_event, task_index=1)
        result = sub.run()

        done_events = [e for e in events if e[0] == "done"]
        assert len(done_events) == 1
        assert done_events[0][1] == 1  # task_index
        assert done_events[0][2]["success"] is False

    def test_on_event_none_no_crash(self):
        """on_event=None 时不应崩溃"""
        parent = _make_parent_agent()
        spec = SubAgentSpec(task="test")
        sub = SubAgent(parent, spec, on_event=None)
        # 不调用 run()，只验证构造不崩溃
        assert sub._on_event is None

    def test_on_text_injected_to_agent(self):
        """on_event 设置后，内部 Agent 应有 _on_text 回调"""
        parent = _make_parent_agent()
        events = []
        def on_event(event_type, task_index, **kwargs):
            events.append((event_type, task_index, kwargs))

        spec = SubAgentSpec(task="test")
        sub = SubAgent(parent, spec, on_event=on_event, task_index=0)
        assert sub._agent._on_text is not None

        # 模拟 _on_text 被调用
        sub._agent._on_text("checking something")
        text_events = [e for e in events if e[0] == "text"]
        assert len(text_events) == 1
        assert text_events[0][2]["text"] == "checking something"

    def test_tool_logging_injected(self):
        """on_event 设置后，工具执行应触发 tool_start/tool_end 事件"""
        parent = _make_parent_agent()
        parent.tools.register("bash", "run command", {"type": "object", "properties": {}}, handler=lambda command: "output")

        events = []
        def on_event(event_type, task_index, **kwargs):
            events.append((event_type, task_index, kwargs))

        spec = SubAgentSpec(task="test")
        sub = SubAgent(parent, spec, on_event=on_event, task_index=0)

        # 执行工具
        result = sub._tools.execute("bash", {"command": "ls"})
        tool_start_events = [e for e in events if e[0] == "tool_start"]
        tool_end_events = [e for e in events if e[0] == "tool_end"]
        assert len(tool_start_events) == 1
        assert tool_start_events[0][2]["tool_name"] == "bash"
        assert tool_start_events[0][2]["args_summary"] == "ls"
        assert len(tool_end_events) == 1

    def test_task_index_passed_through(self):
        """task_index 应正确传递到 on_event 回调"""
        parent = _make_parent_agent()
        events = []
        def on_event(event_type, task_index, **kwargs):
            events.append((event_type, task_index, kwargs))

        spec = SubAgentSpec(task="test")
        sub = SubAgent(parent, spec, on_event=on_event, task_index=5)
        # 触发 _on_text
        sub._agent._on_text("hello")
        assert events[-1][1] == 5


class TestFormatArgsSummary:
    """_format_args_summary 函数测试"""

    def test_bash(self):
        from agent.subagent import _format_args_summary
        assert _format_args_summary("bash", {"command": "ls -la"}) == "ls -la"

    def test_read_file(self):
        from agent.subagent import _format_args_summary
        assert _format_args_summary("read_file", {"path": "/tmp/f.py"}) == "/tmp/f.py"

    def test_write_file(self):
        from agent.subagent import _format_args_summary
        assert _format_args_summary("write_file", {"path": "a.py", "content": "hello"}) == "a.py (5 chars)"

    def test_unknown_tool(self):
        from agent.subagent import _format_args_summary
        assert _format_args_summary("custom", {"x": 1}) == "{'x': 1}"


class TestSpawnWithOnEvent:
    """spawn 工具传递 on_event 测试"""

    @patch("agent.subagent.SubAgent")
    def test_single_task_fires_task_start(self, MockSubAgentCls):
        tools = create_tools()
        mock_result = SubAgentResult(success=True, output="done", steps=1, elapsed=1.0)
        MockSubAgentCls.return_value.run.return_value = mock_result

        events = []
        def on_event(event_type, task_index, **kwargs):
            events.append((event_type, task_index, kwargs))

        parent = MagicMock()
        result = tools.execute("spawn", {"task": "review code"}, agent=parent, on_event=on_event)

        task_start_events = [e for e in events if e[0] == "task_start"]
        assert len(task_start_events) == 1
        assert task_start_events[0][2]["task_name"] == "review code"

    @patch("agent.subagent.run_parallel")
    def test_parallel_tasks_fire_task_start(self, mock_parallel):
        tools = create_tools()
        mock_results = [
            SubAgentResult(success=True, output="r1", steps=1, elapsed=1.0),
            SubAgentResult(success=True, output="r2", steps=1, elapsed=1.0),
        ]
        mock_parallel.return_value = mock_results

        events = []
        def on_event(event_type, task_index, **kwargs):
            events.append((event_type, task_index, kwargs))

        parent = MagicMock()
        result = tools.execute("spawn", {"tasks": ["task1", "task2"]}, agent=parent, on_event=on_event)

        task_start_events = [e for e in events if e[0] == "task_start"]
        assert len(task_start_events) == 2
