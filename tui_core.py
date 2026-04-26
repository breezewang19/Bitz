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
    GREEN = "\033[32m"
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
    """打印彩虹猫 banner - 从左到右彩虹渐变点亮动效"""
    # 小猫每行定义: (内容, 后缀)
    cat_lines = [
        ("  /\\_____/\\", ""),
        (" /  o   o  \\", ""),
        ("( =  w  y  = )", ""),
        ("  \\_____/  ", f"  ~ Bitz ~"),
    ]

    # 彩虹色序列：从左到右渐变
    rainbow = [
        "\033[31m", "\033[31m",  # 红
        "\033[33m", "\033[33m",  # 黄
        "\033[32m", "\033[32m",  # 绿
        "\033[36m", "\033[36m",  # 青
        "\033[34m", "\033[34m",  # 蓝
        "\033[35m", "\033[35m",  # 紫
        "\033[31m", "\033[31m",  # 红（循环）
        "\033[33m", "\033[33m",  # 黄
        "\033[32m", "\033[32m",  # 绿
        "\033[36m", "\033[36m",  # 青
        "\033[34m", "\033[34m",  # 蓝
        "\033[35m", "\033[35m",  # 紫
        "\033[31m", "\033[31m",  # 红
    ]

    def colorize(text, dim=False):
        """给文本上彩虹色"""
        result = ""
        for i, ch in enumerate(text):
            c = rainbow[i % len(rainbow)]
            if dim:
                result += f"{C.DIM}{c}{ch}{C.RESET}"
            else:
                result += f"{C.BOLD}{c}{ch}{C.RESET}"
        return result

    print()

    # 先以暗色打印全部行
    for text, suffix in cat_lines:
        out = f"  {colorize(text, dim=True)}"
        if suffix:
            out += f"{C.DIM}{suffix}{C.RESET}"
        print(out)

    # 光标上移 4 行回到起点
    sys.stdout.write("\033[4A")
    sys.stdout.flush()

    # 从左到右逐列点亮
    max_len = max(len(text) + len(suffix) for text, suffix in cat_lines)
    for lit in range(2, max_len + 2, 2):
        for text, suffix in cat_lines:
            combined = text + suffix
            bright_part = combined[:lit]
            dim_part = combined[lit:]
            # 分离小猫文本和后缀
            bright_text = bright_part[:len(text)]
            bright_suffix = bright_part[len(text):]
            dim_text = dim_part[:max(0, len(text) - lit)]
            dim_suffix = dim_part[max(0, len(text) - lit):]

            out = f"  {colorize(bright_text)}"
            if dim_text:
                out += colorize(dim_text, dim=True)
            if bright_suffix:
                out += f"{C.BOLD}{C.TITLE_BOLD}{bright_suffix}{C.RESET}"
            if dim_suffix:
                out += f"{C.DIM}{dim_suffix}{C.RESET}"
            sys.stdout.write(f"\r{out}\033[K\n")
        sys.stdout.flush()
        time.sleep(0.1)
        sys.stdout.write("\033[4A")
        sys.stdout.flush()

    sys.stdout.write("\033[4B")
    sys.stdout.flush()

    model = os.getenv("ANTHROPIC_MODEL", "MiniMax-M2.7")
    print(f"  {C.THINKING_FG}Model:{C.RESET} {model}")
    print()


def print_goodbye():
    """彩虹波浪 Goodbye~ 动效"""
    # Goodbye~ 用彩虹色逐字点亮
    text = "Goodbye~"
    colors = ["\033[31m", "\033[33m", "\033[32m", "\033[36m", "\033[34m", "\033[35m", "\033[31m", "\033[33m", "\033[32m"]

    # 先暗色铺底
    dim_line = "  "
    for i, ch in enumerate(text):
        dim_line += f"{C.DIM}{colors[i]}{ch}{C.RESET}"
    print(dim_line)

    # 光标上移 1 行
    sys.stdout.write("\033[1A")
    sys.stdout.flush()

    # 从左到右逐字点亮
    for lit in range(1, len(text) + 1):
        out = "  "
        for i, ch in enumerate(text):
            if i < lit:
                out += f"{C.BOLD}{colors[i]}{ch}{C.RESET}"
            else:
                out += f"{C.DIM}{colors[i]}{ch}{C.RESET}"
        sys.stdout.write(f"\r{out}\033[K")
        sys.stdout.flush()
        time.sleep(0.06)

    print()


def thinking_animation(stop_event, cancel_event=None):
    """后台思考动画，cancel_event 触发后切换为取消中动画"""
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    idx = 0
    while not stop_event.is_set():
        if cancel_event and cancel_event.is_set():
            prefix = f"  {C.ERROR_FG}[ESC] Canceling{C.RESET} "
        else:
            prefix = f"  {C.THINKING_FG}Thinking{C.RESET} "
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


def esc_listener(cancel_event: threading.Event, stop_event: threading.Event):
    """后台监听 ESC 键，按下后设置 cancel_event"""
    import select
    while not stop_event.is_set():
        if select.select([sys.stdin], [], [], 0.05)[0]:
            ch = sys.stdin.read(1)
            if ch == '\x1b':
                cancel_event.set()
                return


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
        system_prompt="你叫 Bitz-Cat，是一只小巧玲珑的 mini agent 助手。你聪明、活泼、乐于助人，擅长编程、调试、文件操作和各种技术任务。用温暖友好的方式与用户交流，偶尔会像猫咪一样表现出好奇心和调皮。",
        max_tokens=4096,
        keep_last_n=20
    )
    tools = create_tools()

    original_execute = tools.execute

    def logged_execute(name, args, confirmed=False, tool_id=None):
        sys.stdout.write("\r" + " " * 30 + "\r")
        print_tool_call(name, args)
        return original_execute(name, args, confirmed=confirmed, tool_id=tool_id)

    tools.execute = logged_execute

    agent = Agent(
        llm_adapter=adapter,
        tools=tools,
        context=context,
        max_steps=20
    )

    print_banner()

    history: list[str] = []
    confirmed_tools: set = set()

    while True:
        try:
            user_input = get_input_fn(history)
        except (EOFError, KeyboardInterrupt):
            print()
            print_goodbye()
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        history.append(user_input)

        if user_input.lower() in ("quit", "exit"):
            print_goodbye()
            break

        print()

        cancel_event = threading.Event()
        stop_event = threading.Event()

        anim_thread = threading.Thread(target=thinking_animation, args=(stop_event, cancel_event), daemon=True)
        esc_thread = threading.Thread(target=esc_listener, args=(cancel_event, stop_event), daemon=True)
        anim_thread.start()
        esc_thread.start()

        confirmed_tools.clear()

        try:
            response = agent.run(
                user_input,
                cancel_event=cancel_event,
                confirmed_tools=confirmed_tools
            )

            # 检查是否需要确认
            if response.startswith("[CONFIRM_REQUIRED]"):
                stop_event.set()  # 停止动画
                anim_thread.join(timeout=0.5)

                # 上下箭头选择确认
                selected = 1  # 0=拒绝, 1=批准 (默认批准)
                render_count = 0
                while True:
                    deny_txt = f"{C.ERROR_FG}✗ 拒绝 (n){C.RESET}" if selected == 0 else "  拒绝 (n)"
                    allow_txt = f"{C.GREEN}{C.BOLD}✓ 批准 (y){C.RESET}" if selected == 1 else "  批准 (y)"

                    if render_count > 0:
                        # 重新渲染：光标在第2行，先回到第1行
                        sys.stdout.write("\033[1A")
                    render_count += 1

                    # 清除第1行并打印拒绝选项
                    sys.stdout.write("\033[2K\r")
                    sys.stdout.write(f"  {deny_txt}")
                    # 换行到第2行
                    sys.stdout.write("\n")
                    # 清除第2行并打印批准选项
                    sys.stdout.write("\033[2K\r")
                    sys.stdout.write(f"  {allow_txt}")
                    sys.stdout.flush()

                    # 使用 readchar 读取按键
                    try:
                        import readchar
                        ch = readchar.readchar()
                        if ch == '\x1b':
                            ch2 = readchar.readchar()
                            if ch2 == '[':
                                ch3 = readchar.readchar()
                                if ch3 == 'A':
                                    selected = 0
                                elif ch3 == 'B':
                                    selected = 1
                        elif ch == '\r' or ch == '\n':
                            break
                        elif ch in ('y', 'Y'):
                            selected = 1
                            break
                        elif ch in ('n', 'N'):
                            selected = 0
                            break
                    except ImportError:
                        # readchar 不可用时跳过
                        selected = 1
                        break

                # 清除两行选项：光标在第2行
                sys.stdout.write("\r\033[2K")
                sys.stdout.write("\033[1A\r\033[2K")
                sys.stdout.flush()

                if selected == 1:
                    # 提取 tool_id
                    parts = response.split()
                    if len(parts) >= 2:
                        confirmed_tools.add(parts[1])
                    # 执行待确认的工具
                    should_continue, exec_result = agent.confirm_pending(confirmed_tools)
                    if should_continue:
                        # 继续获取 LLM 响应
                        stop_event.clear()
                        anim_thread = threading.Thread(target=thinking_animation, args=(stop_event, cancel_event), daemon=True)
                        anim_thread.start()
                        response = agent.run(
                            None,
                            cancel_event=cancel_event,
                            confirmed_tools=confirmed_tools,
                            skip_add_user=True
                        )
                else:
                    # 用户拒绝，添加拒绝标记到上下文
                    tool_id = response.split()[1] if len(response.split()) > 1 else ""
                    if tool_id and hasattr(agent, '_pending_confirm') and agent._pending_confirm:
                        _, tool_name, tool_args, _ = agent._pending_confirm
                        # 添加 assistant 消息（因为之前没有添加）
                        agent.context.add_assistant_message([{
                            "type": "tool_use",
                            "id": tool_id,
                            "name": tool_name,
                            "input": tool_args
                        }])
                        # 添加拒绝结果
                        agent.context.add_tool_result(tool_id, "[已拒绝] 用户拒绝了此危险操作")
                        agent._pending_confirm = None
                    response = "[已取消] 危险操作被用户拒绝"
        except KeyboardInterrupt:
            # 清理 Agent 残留状态
            agent._pending_confirm = None
            agent._pending_response = None
            agent._confirmed_results = []
            response = "[中断] 请求被用户取消"
        except Exception as e:
            # 兜底：清理状态，显示友好错误
            agent._pending_confirm = None
            agent._pending_response = None
            agent._confirmed_results = []
            response = f"[错误] {type(e).__name__}: {e}"
        finally:
            stop_event.set()
            anim_thread.join(timeout=1)
            esc_thread.join(timeout=1)

        if cancel_event.is_set():
            print(f"  {C.ERROR_FG}[ESC] 已中断{C.RESET}")
        else:
            print_assistant_response(response)
        print()