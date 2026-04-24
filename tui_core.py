#!/usr/bin/env python3
"""TUI Core - 跨平台共性逻辑"""
import os
import sys
import time
import threading
import shutil
import unicodedata
from typing import Callable

from dotenv import load_dotenv

load_dotenv()

from agent.adapter import LLMAdapter
from agent.context import Context
from agent.loop import Agent
from agent.tools import ToolRegistry


class C:
    """ANSI 颜色码"""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    # 用户输入 - 绿色
    USER_BG = "\033[40m"
    USER_FG = "\033[32m"
    # 助手回复 - 白色
    ASSISTANT_FG = "\033[37m"
    ASSISTANT_BOLD = "\033[1;37m"
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


def display_width(s: str) -> int:
    """计算字符串在终端中的显示宽度（CJK 字符占 2 列）"""
    w = 0
    for ch in s:
        if unicodedata.east_asian_width(ch) in ('W', 'F'):
            w += 2
        else:
            w += 1
    return w


def get_width() -> int:
    """获取终端宽度"""
    try:
        return shutil.get_terminal_size().columns
    except:
        return 80


def print_banner():
    """打印彩虹猫 banner"""
    print()
    print(f"  \033[31m  /\\_____/\\{C.RESET}")
    print(f"  \033[33m /  o   o  \\{C.RESET}")
    print(f"  \033[32m( =  ^  y  = ){C.RESET}")
    print(f"  \033[34m  \\_____/{C.RESET}  {C.TITLE_BOLD}~ Bitz ~{C.RESET}")
    print()
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

    def write_file_handler(path: str, content: str) -> str:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"OK: wrote {len(content)} chars to {path}"
        except Exception as e:
            return f"Error: {e}"

    def glob_handler(pattern: str) -> str:
        import glob
        try:
            matches = glob.glob(pattern, recursive=True)
            if not matches:
                return "No files found"
            return "\n".join(matches)
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

    tools.register(
        name="write_file",
        description="Write content to a file",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["path", "content"]
        },
        handler=write_file_handler
    )

    tools.register(
        name="glob",
        description="Search files by pattern (supports **/*.py etc.)",
        input_schema={
            "type": "object",
            "properties": {"pattern": {"type": "string"}},
            "required": ["pattern"]
        },
        handler=glob_handler
    )

    return tools


def thinking_animation(stop_event):
    """后台思考动画"""
    frames = ["◐", "◓", "◒", "◔"]
    idx = 0
    prefix = f"  {C.THINKING_FG}Thinking{C.RESET} "
    while not stop_event.is_set():
        frame = frames[idx % len(frames)]
        sys.stdout.write(f"\r{prefix}{C.THINKING_FG}{frame}{C.RESET}  ")
        sys.stdout.flush()
        idx += 1
        time.sleep(0.15)
    sys.stdout.write("\r" + " " * 30 + "\r")
    sys.stdout.flush()


def print_tool_call(name: str, args: dict = None):
    """打印工具调用"""
    if name == "bash":
        content = args.get('command', '') if args else ''
    elif name == "read_file":
        content = args.get('path', '') if args else ''
    elif name == "write_file":
        path = args.get('path', '') if args else ''
        content = f"{path} ({len(args.get('content', ''))} chars)" if args else ''
    elif name == "glob":
        content = args.get('pattern', '') if args else ''
    else:
        content = ""

    width = get_width()
    max_len = width - 8
    if len(content) > max_len:
        content = content[:max_len - 3] + "..."

    print(f"  {C.TOOL_BOLD}[{name}]{C.RESET} {C.TOOL_FG}{content}{C.RESET}")


def print_assistant_response(response: str):
    """打印助手回复"""
    lines = response.split("\n")
    for i, line in enumerate(lines):
        if i == 0:
            print(f"  {C.ASSISTANT_BOLD}{line}{C.RESET}")
        else:
            print(f"  {C.ASSISTANT_FG}{line}{C.RESET}")


def run_agent(get_input_fn: Callable[[list[str]], str]):
    """主循环 - 接收平台特定的输入函数"""
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
        sys.stdout.write("\r" + " " * 30 + "\r")
        print_tool_call(name, args)
        return original_execute(name, args)

    tools.execute = logged_execute

    agent = Agent(
        llm_adapter=adapter,
        tools=tools,
        context=context,
        max_steps=20
    )

    print_banner()

    history: list[str] = []

    while True:
        try:
            user_input = get_input_fn(history)
        except (EOFError, KeyboardInterrupt):
            print(f"\n  {C.ASSISTANT_BOLD}o{C.RESET}  {C.ASSISTANT_FG}Bye~{C.RESET}")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        history.append(user_input)

        if user_input.lower() in ("quit", "exit"):
            print(f"  {C.ASSISTANT_BOLD}o{C.RESET}  {C.ASSISTANT_FG}Bye~{C.RESET}")
            break

        print()

        stop_event = threading.Event()
        anim_thread = threading.Thread(target=thinking_animation, args=(stop_event,))
        anim_thread.start()

        try:
            response = agent.run(user_input)
        finally:
            stop_event.set()
            anim_thread.join()

        print_assistant_response(response)
        print()