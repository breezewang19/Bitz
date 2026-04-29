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
        from agent.models import ModelStore
        from agent.skills import SkillRegistry
        from tui import BitzApp

        store = ModelStore()
        current = store.init_from_env()

        if not current.api_key:
            print("Error: Please set ANTHROPIC_API_KEY in .env file")
            sys.exit(1)

        adapter = LLMAdapter(
            api_key=current.api_key,
            base_url=current.base_url,
            model=current.model,
            protocol=current.protocol,
        )
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

        # 加载 Skill
        skill_registry = SkillRegistry()
        skill_registry.load_builtin(os.path.join(os.path.dirname(__file__), "skills"))
        skill_registry.load_user(os.path.join(".", ".bitz", "skills"))

        app = BitzApp(agent=agent, model_store=store, skill_registry=skill_registry)
        app.run()


if __name__ == "__main__":
    main()