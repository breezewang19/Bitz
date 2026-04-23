#!/usr/bin/env python3
"""Minimal Agent TUI - Windows 版本"""
import os
import sys
import time
import threading
import shutil
from dotenv import load_dotenv

load_dotenv()

from agent.adapter import LLMAdapter
from agent.context import Context
from agent.loop import Agent
from agent.tools import ToolRegistry


# ANSI 颜色码
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    # 用户输入 - 黑底白字
    USER_BG = "\033[40m"
    USER_FG = "\033[37m"
    # 助手回复 - 绿色
    ASSISTANT_FG = "\033[32m"
    ASSISTANT_BOLD = "\033[1;32m"
    # 工具调用 - 紫色
    TOOL_FG = "\033[35m"
    TOOL_BOLD = "\033[1;35m"
    # 思考动画 - 青色
    THINKING_FG = "\033[36m"
    # 错误 - 红色
    ERROR_FG = "\033[31m"
    # 标题 - 蓝色
    TITLE_FG = "\033[34m"
    TITLE_BOLD = "\033[1;34m"
    # 分割线 - 灰色
    SEPARATOR_FG = "\033[90m"


def get_width() -> int:
    """获取终端宽度"""
    try:
        return shutil.get_terminal_size().columns
    except:
        return 80


def separator():
    """打印分隔线"""
    width = get_width()
    print(f"{C.SEPARATOR_FG}{'─' * width}{C.RESET}")


def print_banner():
    """打印启动 Banner"""
    banner = [
        f"  {C.TITLE_FG}  /\\_____/\\{C.RESET}",
        f"  {C.TITLE_FG} /  o   o  \\{C.RESET}",
        f"  {C.TITLE_FG}( =  ^  y  = ){C.RESET}",
        f"  {C.TITLE_FG}  \\_____/{C.RESET}  {C.TITLE_BOLD}~ Bitz ~{C.RESET}",
    ]

    print()
    for line in banner:
        print(line)
    print()

    # Model 信息
    model = os.getenv("ANTHROPIC_MODEL", "MiniMax-M2.7")
    print(f"  {C.THINKING_FG}Model:{C.RESET} {model}")
    print()


def create_tools():
    """创建工具注册表"""
    tools = ToolRegistry()

    def bash_handler(command: str) -> str:
        import subprocess
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=30
            )
            return result.stdout or result.stderr or "(no output)"
        except Exception as e:
            return f"Error: {e}"

    def read_file_handler(path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error: {e}"

    tools.register(
        name="bash",
        description="Execute a bash command",
        input_schema={
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"]
        },
        handler=bash_handler
    )

    tools.register(
        name="read_file",
        description="Read file contents",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"]
        },
        handler=read_file_handler
    )

    return tools


def thinking_animation(stop_event):
    """后台动画线程"""
    frames = ["◐", "◓", "◒", "◔"]
    idx = 0
    prefix = f"{C.THINKING_FG}◉ Thinking{C.RESET} "
    while not stop_event.is_set():
        frame = frames[idx % len(frames)]
        sys.stdout.write(f"\r{prefix}{frame}{C.RESET}  ")
        sys.stdout.flush()
        idx += 1
        time.sleep(0.15)
    sys.stdout.write("\r" + " " * 30 + "\r")
    sys.stdout.flush()


def print_tool_call(name: str, args: dict = None):
    """打印工具调用"""
    width = get_width()

    if name == "bash":
        cmd = args.get('command', '') if args else ''
        if len(cmd) > width - 20:
            cmd = cmd[:width - 23] + "..."
        content = cmd
    elif name == "read_file":
        path = args.get('path', '') if args else ''
        if len(path) > width - 20:
            path = path[:width - 23] + "..."
        content = path
    else:
        content = ""

    print(f"{C.TOOL_FG}┌─ {C.TOOL_BOLD}[{name}]{C.RESET}{C.TOOL_FG} ─┐{C.RESET}")
    if content:
        print(f"{C.TOOL_FG}│{C.RESET} {content}")
    print(f"{C.TOOL_FG}└{'─' * (width - 3)}┘{C.RESET}")


def print_user_input(text: str):
    """打印用户输入"""
    width = get_width()

    display_text = text
    if len(display_text) > width - 4:
        display_text = display_text[:width - 7] + "..."

    padding = " " * (width - len(display_text) - 1)
    print(f"{C.USER_BG}{C.USER_FG}{display_text}{padding}{C.RESET}")


def print_assistant_response(response: str):
    """打印助手回复"""
    width = get_width()
    lines = response.split("\n")

    for i, line in enumerate(lines):
        if len(line) > width - 6:
            line = line[:width - 9] + "..."

        if i == 0:
            print(f"{C.ASSISTANT_FG}│{C.RESET}  {C.ASSISTANT_BOLD}{line}{C.RESET}")
        else:
            print(f"{C.ASSISTANT_FG}│{C.RESET}  {C.ASSISTANT_FG}{line}{C.RESET}")


def print_welcome():
    """打印欢迎信息"""
    separator()
    print_banner()
    separator()


def get_input_styled() -> str:
    """获取用户输入（Windows 版本）"""
    import msvcrt

    sys.stdout.write(f"{C.USER_FG}> {C.RESET} ")
    sys.stdout.flush()

    line = ""
    while True:
        try:
            ch = msvcrt.getwch()
            if ch == '\r':
                sys.stdout.write("\033[2K\r")
                try:
                    width = shutil.get_terminal_size().columns
                except:
                    width = 80
                spaces = " " * (width - len(line) - 4)
                sys.stdout.write(f"{C.USER_BG}{C.USER_FG}>  {line}{spaces}{C.RESET}")
                sys.stdout.flush()
                break
            elif ch == '\b':
                if line:
                    line = line[:-1]
                    sys.stdout.write('\b \b')
                    sys.stdout.flush()
            elif ch == '\x03':
                raise KeyboardInterrupt
            else:
                line += ch
                sys.stdout.write(ch)
                sys.stdout.flush()
        except KeyboardInterrupt:
            print(f"\n  {C.ASSISTANT_BOLD}o{C.RESET}  {C.ASSISTANT_FG}Bye~{C.RESET}")
            sys.exit(0)

    return line


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    model_name = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

    if not api_key or api_key == "sk-ant-test":
        print(f"{C.ERROR_FG}Error: Please set ANTHROPIC_API_KEY in .env file{C.RESET}")
        sys.exit(1)

    adapter = LLMAdapter(api_key=api_key, base_url=base_url, model=model_name)
    context = Context(
        system_prompt="You are a helpful coding assistant.",
        max_tokens=4096,
        keep_last_n=20
    )
    tools = create_tools()

    original_execute = tools.execute

    def logged_execute(name, args):
        sys.stdout.write("\r" + " " * 30 + "\n")
        print_tool_call(name, args)
        return original_execute(name, args)

    tools.execute = logged_execute

    agent = Agent(
        llm_adapter=adapter,
        tools=tools,
        context=context,
        max_steps=20
    )

    print_welcome()

    while True:
        try:
            user_input = get_input_styled()
        except (EOFError, KeyboardInterrupt):
            print(f"\n  {C.ASSISTANT_BOLD}o{C.RESET}  {C.ASSISTANT_FG}Bye~{C.RESET}")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit"):
            print(f"  {C.ASSISTANT_BOLD}o{C.RESET}  {C.ASSISTANT_FG}Bye~{C.RESET}")
            break

        print()
        separator()
        print_user_input(user_input)
        print()

        stop_event = threading.Event()
        anim_thread = threading.Thread(target=thinking_animation, args=(stop_event,))
        anim_thread.start()

        try:
            response = agent.run(user_input)
        finally:
            stop_event.set()
            anim_thread.join()

        separator()
        print_assistant_response(response)
        separator()
        print()


if __name__ == "__main__":
    main()
