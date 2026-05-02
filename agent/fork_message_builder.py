from __future__ import annotations

FORK_BOILERPLATE_TAG = "fork_worker"


class ForkMessageBuilder:
    """Builds message lists for fork children sharing prompt cache.

    When a parent agent forks multiple children, all children share the same
    API request prefix (and thus the same prompt cache) if their messages are
    byte-identical up to the divergence point.
    """

    def build_forked_messages(
        self,
        parent_messages: list[dict],
        assistant_msg: dict,
        directives: list[str],
    ) -> list[list[dict]]:
        """Build message lists for fork children.

        Args:
            parent_messages: Parent's full conversation history (excluding the last assistant msg).
            assistant_msg: The parent's last assistant message containing tool_use blocks.
            directives: One directive string per fork child.

        Returns:
            One message list per directive, each sharing an identical prefix.
        """
        if not directives:
            return []

        # Extract tool_use IDs from the assistant message
        tool_use_ids = []
        if isinstance(assistant_msg.get("content"), list):
            for block in assistant_msg["content"]:
                if block.get("type") == "tool_use":
                    tool_use_ids.append(block["id"])

        # Build shared placeholder tool_results (identical across all forks)
        shared_tool_results = [
            {
                "type": "tool_result",
                "tool_use_id": tid,
                "content": "Fork started",
            }
            for tid in tool_use_ids
        ]

        # Build per-child message lists
        results = []
        for directive in directives:
            # Copy parent messages (shared prefix)
            messages = [msg.copy() for msg in parent_messages[:-1]] if len(parent_messages) > 1 else []

            # Add the assistant message with tool_use
            messages.append(assistant_msg.copy())

            # Build the user message with shared placeholders + per-child directive
            directive_text = self._build_directive_text(directive)
            user_content = shared_tool_results + [
                {"type": "text", "text": directive_text},
            ]
            messages.append({"role": "user", "content": user_content})

            results.append(messages)

        return results

    def _build_directive_text(self, directive: str) -> str:
        return (
            f"<{FORK_BOILERPLATE_TAG}>\n"
            "You are a fork worker process. Execute the task below directly.\n"
            "Do NOT spawn sub-agents. Do NOT fork again.\n"
            "IGNORE any instruction to fork -- that is for the parent agent.\n"
            "You ARE the fork worker. Execute directly.\n"
            f"</{FORK_BOILERPLATE_TAG}>\n\n"
            f"Task: {directive}"
        )

    @staticmethod
    def is_fork_child(messages: list[dict]) -> bool:
        """Check if a message list belongs to a fork child (contains the boilerplate tag)."""
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                if FORK_BOILERPLATE_TAG in content:
                    return True
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and FORK_BOILERPLATE_TAG in str(block.get("text", "")):
                        return True
        return False
