#!/usr/bin/env python3
"""Minimal Agent TUI - 终端对话界面"""
import os
import sys
import time
import threading
from dotenv import load_dotenv

load_dotenv()

from agent.adapter import LLMAdapter
from agent.context import Context
from agent.loop import Agent
from agent.tools import ToolRegistry


# ANSI 颜色码
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    # 用户消息 - 黑底白字
    USER_BG = "\033[40m"
    USER_FG = "\033[37m"
    # 助手消息 - 绿色
    ASSISTANT = "\033[32m"
    ASSISTANT_BOLD = "\033[1;32m"
    # 工具调用 - 紫色
    TOOL = "\033[35m"
    TOOL_BOLD = "\033[1;35m"
    # 思考动画 - 青色
    THINKING = "\033[36m"
    # 错误 - 红色
    ERROR = "\033[31m"


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
    frames = ["|", "/", "-", "\\"]
    idx = 0
    prefix = f"{Colors.ASSISTANT}o{Colors.RESET} {Colors.THINKING}Thinking..."
    while not stop_event.is_set():
        frame = frames[idx % len(frames)]
        sys.stdout.write(f"\r{prefix} {Colors.THINKING}{frame}{Colors.RESET}  ")
        sys.stdout.flush()
        idx += 1
        time.sleep(0.15)
    # 彻底清除整行
    sys.stdout.write("\r" + " " * 50 + "\r")
    sys.stdout.flush()


def get_input_styled() -> str:
    """获取用户输入，输入时白底黑字，发送后黑底白字填满整行"""
    import msvcrt

    # 打印提示符（白底黑字的小箭头）
    sys.stdout.write(f"{Colors.USER_FG}> {Colors.RESET} ")
    sys.stdout.flush()

    # 读取字符（不回显，我们自己显示）
    line = ""
    while True:
        try:
            ch = msvcrt.getwch()
            if ch == '\r':
                # 清除整行，光标移到行首，显示黑底白字后换行
                sys.stdout.write("\033[2K\r")
                # 获取终端宽度
                try:
                    import shutil
                    width = shutil.get_terminal_size().columns
                except:
                    width = 80
                spaces = " " * (width - len(line) - 4)
                # 显示黑底白字的用户输入
                sys.stdout.write(f"{Colors.USER_BG}{Colors.USER_FG}>  {line}{spaces}{Colors.RESET}")
                # sys.stdout.write("\n")  # 换行到下一行
                sys.stdout.flush()
                break
            elif ch == '\b':
                if line:
                    line = line[:-1]
                    sys.stdout.write('\b \b')
                    sys.stdout.flush()
            elif ch == '\x03':  # Ctrl+C
                raise KeyboardInterrupt
            else:
                line += ch
                sys.stdout.write(ch)
                sys.stdout.flush()
        except KeyboardInterrupt:
            print(f"\n{Colors.ASSISTANT_BOLD}  o{Colors.RESET} {Colors.ASSISTANT}Bye~{Colors.RESET}")
            sys.exit(0)

    return line


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

    if not api_key or api_key == "sk-ant-test":
        print(f"{Colors.ERROR}Error: Please set ANTHROPIC_API_KEY in .env file{Colors.RESET}")
        sys.exit(1)

    adapter = LLMAdapter(api_key=api_key, base_url=base_url, model=model)
    context = Context(
        system_prompt="You are a helpful coding assistant.",
        max_tokens=4096,
        keep_last_n=20
    )
    tools = create_tools()

    # 保存原始 execute 方法来添加日志
    original_execute = tools.execute

    def logged_execute(name, args):
        sys.stdout.write("\r" + " " * 50 + "\n")  # 清除动画
        print(f"{Colors.TOOL}  o{Colors.RESET} {Colors.TOOL_BOLD}[{name}]{Colors.RESET}")
        return original_execute(name, args)

    tools.execute = logged_execute

    agent = Agent(
        llm_adapter=adapter,
        tools=tools,
        context=context,
        max_steps=20
    )

    print()
    print(f"{Colors.BOLD}{Colors.ASSISTANT}    /\\{Colors.RESET} {Colors.BOLD}~ Bitz ~{Colors.RESET} {Colors.ASSISTANT}/\\{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.ASSISTANT}   (  o  o  ){Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.ASSISTANT}    \\____/  {Colors.RESET} AI Agent")
    print()
    print(f"  {Colors.THINKING}Model:{Colors.RESET} {model}")
    print()

    while True:
        try:
            user_input = get_input_styled()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{Colors.ASSISTANT_BOLD}  o{Colors.RESET} {Colors.ASSISTANT}Bye~{Colors.RESET}")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit"):
            print(f"\n{Colors.ASSISTANT_BOLD}  o{Colors.RESET} {Colors.ASSISTANT}Bye~{Colors.RESET}")
            break

        # 启动等待动画
        stop_event = threading.Event()
        anim_thread = threading.Thread(target=thinking_animation, args=(stop_event,))
        anim_thread.start()

        try:
            response = agent.run(user_input)
        finally:
            stop_event.set()
            anim_thread.join()

        print()
        # 助手回复只有第一行有 o，后续行缩进
        lines = response.split("\n")
        for i, line in enumerate(lines):
            if i == 0:
                print(f"{Colors.ASSISTANT_BOLD}  o{Colors.RESET} {Colors.ASSISTANT}{line}{Colors.RESET}")
            else:
                print(f"{Colors.ASSISTANT}    {line}{Colors.RESET}")
        print()


if __name__ == "__main__":
    main()
