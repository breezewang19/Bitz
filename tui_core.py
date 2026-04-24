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
from agent.builtin_tools import create_tools


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
    """打印彩虹猫 banner - 从左到右波浪点亮动效"""
    # 小猫每行定义: (颜色, 内容, 后缀)
    cat_lines = [
        ("\033[31m", "  /\\_____/\\", ""),
        ("\033[33m", " /  o   o  \\", ""),
        ("\033[32m", "( =  ^  y  = )", ""),
        ("\033[34m", "  \\_____/  ", f"  ~ Bitz ~"),
    ]

    print()

    # 先以暗色打印全部行
    for color, text, suffix in cat_lines:
        print(f"  {C.DIM}{color}{text}{C.RESET}{C.DIM}{suffix}{C.RESET}")

    # 光标上移 4 行回到起点
    sys.stdout.write("\033[4A")
    sys.stdout.flush()

    # 从左到右逐列点亮，每帧多亮 2 列
    max_len = max(len(text) + len(suffix) for _, text, suffix in cat_lines)
    for lit in range(2, max_len + 2, 2):
        for color, text, suffix in cat_lines:
            combined = text + suffix
            bright = combined[:lit]
            dim = combined[lit:]
            # 后缀部分用 TITLE_BOLD 色，小猫部分用原色
            bright_text = bright[:len(text)]
            bright_suffix = bright[len(text):]
            dim_text = dim[:max(0, len(text) - lit)]
            dim_suffix = dim[max(0, len(text) - lit):]
            out = f"  {C.BOLD}{color}{bright_text}{C.RESET}"
            if dim_text:
                out += f"{C.DIM}{color}{dim_text}{C.RESET}"
            if bright_suffix:
                out += f"{C.BOLD}{C.TITLE_BOLD}{bright_suffix}{C.RESET}"
            if dim_suffix:
                out += f"{C.DIM}{dim_suffix}{C.RESET}"
            sys.stdout.write(f"\r{out}\033[K\n")
        sys.stdout.flush()
        time.sleep(0.1)
        # 光标上移 4 行回到起点，准备下一帧
        sys.stdout.write("\033[4A")
        sys.stdout.flush()

    # 最终光标移到最底行下方
    sys.stdout.write("\033[4B")
    sys.stdout.flush()

    model = os.getenv("ANTHROPIC_MODEL", "MiniMax-M2.7")
    print(f"  {C.THINKING_FG}Model:{C.RESET} {model}")
    print()


def thinking_animation(stop_event):
    """后台思考动画"""
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
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
    elif name == "edit_file":
        path = args.get('path', '') if args else ''
        content = f"{path}" if args else ''
    elif name == "glob":
        content = args.get('pattern', '') if args else ''
    elif name == "grep":
        pattern = args.get('pattern', '') if args else ''
        path = args.get('path', '.') if args else '.'
        content = f"{pattern} in {path}"
    elif name == "fetch":
        content = args.get('url', '') if args else ''
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