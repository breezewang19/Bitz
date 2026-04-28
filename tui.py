import os
import sys
import argparse


def main():
    parser = argparse.ArgumentParser(description="Bitz AI Agent TUI")
    parser.add_argument("--legacy", action="store_true", help="Use legacy TUI (pure ANSI)")
    args, remaining = parser.parse_known_args()

    if args.legacy:
        import platform
        if platform.system() == "Windows":
            from tui_win import main as legacy_main
        else:
            from tui_mac import main as legacy_main
        legacy_main()
    else:
        from dotenv import load_dotenv
        load_dotenv()

        from agent.adapter import LLMAdapter
        from agent.context import Context
        from agent.loop import Agent
        from agent.builtin_tools import create_tools
        from agent.prompt import build_system_prompt
        from tui import BitzApp

        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        model_name = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

        if not api_key or api_key == "sk-ant-test":
            print("Error: Please set ANTHROPIC_API_KEY in .env file")
            sys.exit(1)

        adapter = LLMAdapter(api_key=api_key, base_url=base_url, model=model_name)
        context = Context(
            system_prompt=build_system_prompt(cwd=os.getcwd()),
            max_tokens=4096,
            keep_last_n=20,
        )
        tools = create_tools()
        agent = Agent(
            llm_adapter=adapter,
            tools=tools,
            context=context,
            max_steps=20,
        )

        app = BitzApp(agent=agent)
        app.run()


if __name__ == "__main__":
    main()