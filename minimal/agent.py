"""ReAct 智能体 — 核心循环 + 最简 REPL"""
from minimal.context import Context
from minimal.llm import LLMAdapter, LLMError
from minimal.tools import ToolRegistry, ToolResult, create_tools


DEFAULT_SYSTEM_PROMPT = """你是一个务实的编程助手，可以使用工具帮助用户完成任务。
执行危险操作前需要用户确认。"""


class Agent:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514",
                 base_url: str = "https://api.anthropic.com",
                 system_prompt: str = DEFAULT_SYSTEM_PROMPT):
        self.context = Context(system_prompt=system_prompt)
        self.llm = LLMAdapter(api_key=api_key, model=model, base_url=base_url)
        self.tools = create_tools()
        self.max_steps = 30
        self.on_text = None  # callback(text: str)

    def run(self, user_input: str) -> str:
        self.context.add_user(user_input)

        for _ in range(self.max_steps):
            messages = self.context.get_messages()
            tool_defs = self.tools.tool_definitions()

            try:
                stop_reason, content_blocks = self.llm.chat(messages, tool_defs)
            except LLMError as e:
                return f"[LLM Error] {e}"

            if stop_reason == "end_turn":
                text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
                self.context.add_assistant_text(text)
                return text

            if stop_reason == "tool_use":
                # 输出中间文字
                text_parts = [b["text"] for b in content_blocks if b.get("type") == "text"]
                if text_parts and self.on_text:
                    self.on_text("\n".join(text_parts))

                # 执行工具
                tool_blocks = [b for b in content_blocks if b.get("type") == "tool_use"]
                results: list[tuple[str, str, bool]] = []
                for tb in tool_blocks:
                    tool_name = tb["name"]
                    tool_args = tb["input"]
                    tool_id = tb["id"]
                    result = self.tools.execute(tool_name, tool_args)

                    if result.needs_confirm:
                        print(f"\n⚠ {result.confirm_message}")
                        answer = input("确认执行? [y/N] ").strip().lower()
                        if answer == "y":
                            result = self.tools.execute(tool_name, tool_args, confirmed=True)
                        else:
                            result = ToolResult.error("用户拒绝执行")

                    results.append((tool_id, result.output, result.is_error))

                self.context.add_assistant_message(content_blocks)
                self.context.add_tool_results(results)
                continue

            # max_tokens: 保存部分文本，注入续传消息
            text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
            self.context.add_assistant_text(text)
            self.context.add_user("请继续输出，不要重复已说过的内容。")
            continue

        return f"[Error] 超过最大步数 ({self.max_steps})"


def main():
    from dotenv import load_dotenv
    import os

    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set (check .env)")
        return

    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    agent = Agent(api_key=api_key, model=model, base_url=base_url)

    print("Bitz Minimal Agent — 输入 /quit 退出, /clear 清空上下文\n")
    while True:
        try:
            user_input = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见!")
            break
        if not user_input:
            continue
        if user_input == "/quit":
            print("再见!")
            break
        if user_input == "/clear":
            agent.context.messages.clear()
            print("上下文已清空")
            continue

        response = agent.run(user_input)
        print(f"\n{response}\n")


if __name__ == "__main__":
    main()
