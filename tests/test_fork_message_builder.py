from agent.fork_message_builder import ForkMessageBuilder, FORK_BOILERPLATE_TAG


class TestForkMessageBuilder:
    def _make_parent_messages(self):
        """Create a minimal parent conversation."""
        return [
            {"role": "user", "content": "Please analyze these files"},
            {"role": "assistant", "content": [
                {"type": "text", "text": "I'll analyze them in parallel"},
                {"type": "tool_use", "id": "tool_1", "name": "spawn", "input": {"task": "analyze file 1"}},
                {"type": "tool_use", "id": "tool_2", "name": "spawn", "input": {"task": "analyze file 2"}},
            ]},
        ]

    def test_build_forked_messages_returns_one_per_directive(self):
        builder = ForkMessageBuilder()
        parent_msgs = self._make_parent_messages()
        assistant_msg = parent_msgs[-1]
        directives = ["analyze file 1", "analyze file 2"]

        results = builder.build_forked_messages(parent_msgs, assistant_msg, directives)
        assert len(results) == 2

    def test_forked_messages_include_parent_history(self):
        builder = ForkMessageBuilder()
        parent_msgs = self._make_parent_messages()
        assistant_msg = parent_msgs[-1]
        directives = ["task 1"]

        results = builder.build_forked_messages(parent_msgs, assistant_msg, directives)
        # First message should be the parent's first user message
        assert results[0][0]["role"] == "user"
        assert results[0][0]["content"] == "Please analyze these files"

    def test_forked_messages_include_assistant_msg(self):
        builder = ForkMessageBuilder()
        parent_msgs = self._make_parent_messages()
        assistant_msg = parent_msgs[-1]
        directives = ["task 1"]

        results = builder.build_forked_messages(parent_msgs, assistant_msg, directives)
        # Should contain the assistant message
        assistant_msgs = [m for m in results[0] if m["role"] == "assistant"]
        assert len(assistant_msgs) == 1

    def test_forked_messages_include_placeholder_tool_results(self):
        builder = ForkMessageBuilder()
        parent_msgs = self._make_parent_messages()
        assistant_msg = parent_msgs[-1]
        directives = ["task 1"]

        results = builder.build_forked_messages(parent_msgs, assistant_msg, directives)
        # The user message after assistant should have tool_results for each tool_use
        user_msg = results[0][-1]
        assert user_msg["role"] == "user"
        # Should have tool_result blocks + directive text
        tool_results = [b for b in user_msg["content"] if b.get("type") == "tool_result"]
        assert len(tool_results) == 2  # One for each tool_use

    def test_forked_messages_include_directive_text(self):
        builder = ForkMessageBuilder()
        parent_msgs = self._make_parent_messages()
        assistant_msg = parent_msgs[-1]
        directives = ["analyze authentication module"]

        results = builder.build_forked_messages(parent_msgs, assistant_msg, directives)
        user_msg = results[0][-1]
        text_blocks = [b for b in user_msg["content"] if b.get("type") == "text"]
        assert len(text_blocks) == 1
        assert "analyze authentication module" in text_blocks[0]["text"]
        assert FORK_BOILERPLATE_TAG in text_blocks[0]["text"]

    def test_different_directives_produce_different_messages(self):
        builder = ForkMessageBuilder()
        parent_msgs = self._make_parent_messages()
        assistant_msg = parent_msgs[-1]
        directives = ["task A", "task B"]

        results = builder.build_forked_messages(parent_msgs, assistant_msg, directives)
        # The directives should differ
        text_0 = [b for b in results[0][-1]["content"] if b.get("type") == "text"][0]["text"]
        text_1 = [b for b in results[1][-1]["content"] if b.get("type") == "text"][0]["text"]
        assert "task A" in text_0
        assert "task B" in text_1

    def test_shared_prefix_is_identical(self):
        """All fork children should share identical message prefix for cache sharing."""
        builder = ForkMessageBuilder()
        parent_msgs = self._make_parent_messages()
        assistant_msg = parent_msgs[-1]
        directives = ["task A", "task B", "task C"]

        results = builder.build_forked_messages(parent_msgs, assistant_msg, directives)
        # All messages except the last user message should be identical
        for i in range(1, len(results)):
            assert results[i][:-1] == results[0][:-1]

    def test_incomplete_tool_calls_filtered(self):
        """Assistant messages with tool_use but no corresponding tool_result should be handled."""
        parent_msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": [
                {"type": "text", "text": "let me check"},
                {"type": "tool_use", "id": "tool_99", "name": "bash", "input": {"command": "ls"}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tool_99", "content": "file1.txt"},
            ]},
            {"role": "assistant", "content": [
                {"type": "text", "text": "I'll spawn workers"},
                {"type": "tool_use", "id": "tool_1", "name": "spawn", "input": {"task": "work"}},
            ]},
        ]
        builder = ForkMessageBuilder()
        assistant_msg = parent_msgs[-1]
        directives = ["task 1"]

        results = builder.build_forked_messages(parent_msgs, assistant_msg, directives)
        # Should succeed — the incomplete tool_use in the last assistant msg gets placeholders
        assert len(results) == 1

    def test_empty_directives_returns_empty(self):
        builder = ForkMessageBuilder()
        parent_msgs = self._make_parent_messages()
        assistant_msg = parent_msgs[-1]

        results = builder.build_forked_messages(parent_msgs, assistant_msg, [])
        assert results == []

    def test_fork_boilerplate_prevents_re_forking(self):
        """The boilerplate tag should be detectable to prevent recursive forking."""
        builder = ForkMessageBuilder()
        parent_msgs = self._make_parent_messages()
        assistant_msg = parent_msgs[-1]
        directives = ["task 1"]

        results = builder.build_forked_messages(parent_msgs, assistant_msg, directives)
        text = [b for b in results[0][-1]["content"] if b.get("type") == "text"][0]["text"]
        assert "Do NOT spawn sub-agents" in text
        assert "Do NOT fork again" in text
