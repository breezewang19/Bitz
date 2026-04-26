#!/usr/bin/env python3
"""TUI 入口 - 自动检测平台"""
import platform

if platform.system() == "Windows":
    from tui_win import get_input_styled
else:
    from tui_mac import get_input_styled

from tui_core import run_agent

if __name__ == "__main__":
    run_agent(get_input_styled)
