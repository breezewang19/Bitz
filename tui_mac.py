#!/usr/bin/env python3
"""TUI macOS/Linux 兼容层 - termios 输入处理"""
import sys
import tty
import termios
import shutil

from tui_core import C, display_width, run_agent


def get_input_styled(history: list[str]) -> str:
    """获取用户输入（macOS/Linux termios 版本）"""
    prompt = f"{C.USER_FG}> {C.RESET} "
    sys.stdout.write(prompt)
    sys.stdout.flush()

    line = ""
    cursor = 0
    hist_idx = len(history)

    def refresh():
        nonlocal cursor
        sys.stdout.write(f"\r{prompt}{line}\033[K")
        cursor = min(cursor, len(line))
        after_cursor = display_width(line[cursor:])
        if after_cursor > 0:
            sys.stdout.write(f"\033[{after_cursor}D")
        sys.stdout.flush()

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        tty.setraw(fd)

        while True:
            ch = sys.stdin.read(1)

            if ch == '\r' or ch == '\n':
                sys.stdout.write("\033[2K\r")
                try:
                    width = shutil.get_terminal_size().columns
                except:
                    width = 80
                dw = display_width(line)
                spaces = " " * (width - dw - 4)
                sys.stdout.write(f"{C.USER_BG}{C.USER_FG}>  {line}{spaces}{C.RESET}")
                sys.stdout.flush()
                break
            elif ch == '\x03':  # Ctrl+C
                from tui_core import print_goodbye
                sys.stdout.write("\n")
                sys.stdout.flush()
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                print_goodbye()
                sys.exit(0)
            elif ch == '\x1b':
                ch2 = sys.stdin.read(1)
                if ch2 == '[':
                    ch3 = sys.stdin.read(1)
                    if ch3 == 'D':    # Left
                        if cursor > 0:
                            cursor -= 1
                            move = display_width(line[cursor:cursor + 1])
                            sys.stdout.write(f"\033[{move}D")
                            sys.stdout.flush()
                    elif ch3 == 'C':  # Right
                        if cursor < len(line):
                            move = display_width(line[cursor:cursor + 1])
                            cursor += 1
                            sys.stdout.write(f"\033[{move}C")
                            sys.stdout.flush()
                    elif ch3 == 'A':  # Up
                        if hist_idx > 0:
                            hist_idx -= 1
                            line = history[hist_idx]
                            cursor = len(line)
                            refresh()
                    elif ch3 == 'B':  # Down
                        if hist_idx < len(history) - 1:
                            hist_idx += 1
                            line = history[hist_idx]
                            cursor = len(line)
                            refresh()
                        elif hist_idx == len(history) - 1:
                            hist_idx = len(history)
                            line = ""
                            cursor = 0
                            refresh()
                    elif ch3 == '3' and sys.stdin.read(1) == '~':  # Delete
                        if cursor < len(line):
                            line = line[:cursor] + line[cursor + 1:]
                            refresh()
                    elif ch3 == 'H':  # Home
                        cursor = 0
                        sys.stdout.write(f"\r{prompt}")
                        sys.stdout.flush()
                    elif ch3 == 'F':  # End
                        cursor = len(line)
                        sys.stdout.write(f"\r{prompt}{line}")
                        sys.stdout.flush()
                # discard unknown escape sequences
            elif ch == '\x7f' or ch == '\b':  # Backspace
                if cursor > 0:
                    line = line[:cursor - 1] + line[cursor:]
                    cursor -= 1
                    refresh()
            elif ch == '\x01':  # Ctrl+A
                cursor = 0
                sys.stdout.write(f"\r{prompt}")
                sys.stdout.flush()
            elif ch == '\x05':  # Ctrl+E
                cursor = len(line)
                sys.stdout.write(f"\r{prompt}{line}")
                sys.stdout.flush()
            elif ch == '\x04':  # Ctrl+D
                if cursor < len(line):
                    line = line[:cursor] + line[cursor + 1:]
                    refresh()
            elif ord(ch) >= 32:
                line = line[:cursor] + ch + line[cursor:]
                cursor += 1
                refresh()

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    return line


if __name__ == "__main__":
    run_agent(get_input_styled)
