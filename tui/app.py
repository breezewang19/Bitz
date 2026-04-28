from __future__ import annotations

import asyncio
import os
import threading
import time
from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.widgets import Static
from textual.events import Key

from tui.theme import BITZ_CSS
from tui.widgets.banner import BannerWidget, GoodbyeWidget
from tui.widgets.chat import ChatLog, format_tool_content
from tui.widgets.confirm import ConfirmPrompt
from tui.widgets.input import InputBar
from tui.widgets.status import StatusBar

if TYPE_CHECKING:
    from agent.loop import Agent


class BitzApp(App):
    CSS = BITZ_CSS

    BINDINGS = [
        ("ctrl+l", "clear_screen", "Clear"),
    ]

    def __init__(self, agent: Agent, **kwargs) -> None:
        super().__init__(**kwargs)
        self._agent = agent
        self._original_execute = agent.tools.execute
        self._cancel_event = threading.Event()
        self._confirmed_tools: set = set()
        self._step_count = 0
        self._thinking_task: asyncio.Task | None = None
        self._exiting = False
        self._confirm_prompt: ConfirmPrompt | None = None
        self._confirm_result: asyncio.Future | None = None
        self._turn_start: float = 0.0
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0

    def compose(self) -> ComposeResult:
        yield ChatLog()
        yield StatusBar()
        yield InputBar()

    def on_mount(self) -> None:
        chat = self.query_one(ChatLog)
        model_name = os.getenv("ANTHROPIC_MODEL", "unknown")
        chat.mount(BannerWidget(model_name=model_name))
        status = self.query_one(StatusBar)
        status.update_model(model_name)
        bar = self.query_one(InputBar)
        bar.focus_input()
        # 注册主题
        from tui.theme import BITZ_THEMES, detect_theme
        for theme in BITZ_THEMES:
            self.register_theme(theme)
        self.theme = detect_theme()
        self._install_tool_logger()
        self._install_retry_logger()

    def _install_tool_logger(self) -> None:
        """Monkey-patch tools.execute to log tool calls to UI via ToolCard."""
        import difflib

        original = self._original_execute
        app = self

        def logged_execute(name, args, confirmed=False, tool_id=None):
            content = format_tool_content(name, args if isinstance(args, dict) else {})
            app._post_tool_call(name, content)
            app._set_tool_running(name)
            try:
                # 对于 edit_file 和 write_file，在执行前读取原文件内容以生成 diff
                old_content = None
                if name == "edit_file" and isinstance(args, dict):
                    try:
                        with open(args.get("path", ""), "r", encoding="utf-8") as f:
                            old_content = f.read()
                    except Exception:
                        pass
                elif name == "write_file" and isinstance(args, dict):
                    path = args.get("path", "")
                    if os.path.exists(path):
                        try:
                            with open(path, "r", encoding="utf-8") as f:
                                old_content = f.read()
                        except Exception:
                            pass

                result = original(name, args, confirmed=confirmed, tool_id=tool_id)
                is_error = result.startswith("Error") or result.startswith("[CONFIRM_REQUIRED]")

                # 生成 diff
                diff_text = None
                if not is_error and old_content is not None:
                    if name == "edit_file":
                        new_content = old_content.replace(args.get("old_string", ""), args.get("new_string", ""))
                    else:  # write_file
                        new_content = args.get("content", "")
                    diff_lines = list(difflib.unified_diff(
                        old_content.splitlines(keepends=True),
                        new_content.splitlines(keepends=True),
                        fromfile=f"a/{args.get('path', '')}",
                        tofile=f"b/{args.get('path', '')}",
                        n=3,
                    ))
                    if diff_lines:
                        diff_text = "".join(diff_lines)

                app._post_tool_result(name, result, is_error, diff_text)
            finally:
                app._set_tool_running(None)
            return result

        self._agent.tools.execute = logged_execute

    def _install_retry_logger(self) -> None:
        """Set retry callback on LLM adapter to show retry info in UI."""
        app = self
        def on_retry(err_msg: str, attempt: int, max_retries: int) -> None:
            try:
                app.call_from_thread(app._show_retry_info, err_msg, attempt, max_retries)
            except Exception:
                pass
        self._agent.llm_adapter._on_retry = on_retry

    def _show_retry_info(self, err_msg: str, attempt: int, max_retries: int) -> None:
        chat = self.query_one(ChatLog)
        chat.add_message("tool", f"重试 {attempt}/{max_retries}: {err_msg}", tool_name="retry")

    def _set_tool_running(self, tool_name: str | None) -> None:
        """Thread-safe: update thinking indicator to show tool running state."""
        try:
            self.call_from_thread(self._update_tool_running, tool_name)
        except Exception:
            pass

    def _update_tool_running(self, tool_name: str | None) -> None:
        chat = self.query_one(ChatLog)
        chat.set_tool_running(tool_name)

    
    def _post_tool_result(self, tool_name: str, result: str, is_error: bool, diff_text: str = None) -> None:
        """Thread-safe: update the last ToolCard with success/error result."""
        try:
            self.call_from_thread(self._update_tool_result, tool_name, result, is_error, diff_text)
        except Exception:
            pass

    def _update_tool_result(self, tool_name: str, result: str, is_error: bool, diff_text: str = None) -> None:
        from tui.widgets.tool_card import ToolCard
        chat = self.query_one(ChatLog)
        cards = chat.query(ToolCard)
        for card in reversed(list(cards)):
            if card._tool_name == tool_name and card._status == "running":
                if is_error:
                    card.set_error(result)
                elif diff_text:
                    card.set_diff(diff_text)
                else:
                    card.set_success(result)
                return

    def _post_tool_call(self, tool_name: str, content: str) -> None:
        """Thread-safe: schedule a tool message on the UI from any thread."""
        try:
            self.call_from_thread(self._add_tool_message, tool_name, content)
        except Exception:
            pass

    def _add_tool_message(self, tool_name: str, content: str) -> None:
        chat = self.query_one(ChatLog)
        chat.add_message("tool", content, tool_name=tool_name)

    def on_input_bar_message_submitted(self, event: InputBar.MessageSubmitted) -> None:
        # If in confirm mode, treat input as confirm response
        if self._confirm_prompt is not None and self._confirm_result is not None:
            text = event.text.strip().lower()
            if text in ("y", "yes", "批准"):
                self._confirm_prompt.selected = True
                self._resolve_confirm(True)
            elif text in ("n", "no", "拒绝"):
                self._resolve_confirm(False)
            else:
                # Invalid input, just ignore
                bar = self.query_one(InputBar)
                bar._input.value = ""
                bar._input.placeholder = "y/n?"
                bar._input.focus()
            return

        chat = self.query_one(ChatLog)
        chat.add_message("user", event.text)
        self._run_agent(event.text)

    def on_input_bar_command_submitted(self, event: InputBar.CommandSubmitted) -> None:
        """处理斜杠命令。"""
        command = event.command
        args = event.args
        chat = self.query_one(ChatLog)

        if command == "help":
            help_text = (
                "## 可用命令\n\n"
                "| 命令 | 说明 |\n"
                "|------|------|\n"
                "| `/help` | 显示此帮助信息 |\n"
                "| `/clear` | 清屏 |\n"
                "| `/compact` | 压缩上下文 |\n"
                "| `/theme [name]` | 切换主题（无参数时循环切换）|\n"
            )
            chat.add_message("assistant", help_text)
        elif command == "clear":
            self.action_clear_screen()
        elif command == "compact":
            before = len(self._agent.context.messages)
            self._agent.context._trim()
            after = len(self._agent.context.messages)
            removed = before - after
            chat.add_message("assistant", f"上下文已压缩：{before} → {after} 条消息（移除 {removed} 条）")
        elif command == "theme":
            if args:
                from tui.theme import THEME_NAMES
                if args in THEME_NAMES:
                    self.theme = args
                    chat.add_message("assistant", f"主题已切换为 {args}")
                else:
                    chat.add_message("assistant", f"未知主题: {args}。可用: {', '.join(THEME_NAMES)}")
            else:
                from tui.theme import THEME_NAMES
                current = self.theme
                try:
                    idx = THEME_NAMES.index(current)
                    next_idx = (idx + 1) % len(THEME_NAMES)
                except ValueError:
                    next_idx = 0
                self.theme = THEME_NAMES[next_idx]
                chat.add_message("assistant", f"主题已切换为 {THEME_NAMES[next_idx]}")
        else:
            chat.add_message("assistant", f"未知命令: /{command}。输入 /help 查看可用命令。")

    def on_key(self, event: Key) -> None:
        # Handle y/n keys directly during confirm mode
        if self._confirm_prompt is not None and self._confirm_result is not None:
            if event.key == "y":
                self._resolve_confirm(True)
                event.prevent_default()
            elif event.key == "n":
                self._resolve_confirm(False)
                event.prevent_default()
            elif event.key == "left":
                self._confirm_prompt.select_deny()
                event.prevent_default()
            elif event.key == "right":
                self._confirm_prompt.select_allow()
                event.prevent_default()
            elif event.key == "enter":
                self._resolve_confirm(self._confirm_prompt.selected)
                event.prevent_default()
            elif event.key == "escape":
                self._resolve_confirm(False)
                event.prevent_default()
            return

        bar = self.query_one(InputBar)
        # ESC: cancel running agent
        if event.key == "escape" and bar._busy:
            self._cancel_event.set()
            chat = self.query_one(ChatLog)
            chat.set_canceling()
            event.prevent_default()
            return

        # Ctrl+C: cancel if running, quit if idle
        if event.key == "ctrl+c":
            if bar._busy:
                self._cancel_event.set()
                chat = self.query_one(ChatLog)
                chat.set_canceling()
                event.prevent_default()
            else:
                self.action_quit()
                event.prevent_default()

    def _resolve_confirm(self, approved: bool) -> None:
        """Resolve the confirm future and clean up the prompt."""
        if self._confirm_result is not None and not self._confirm_result.done():
            self._confirm_result.set_result(approved)
        # Remove prompt from chat
        if self._confirm_prompt is not None:
            self._confirm_prompt.remove()
            self._confirm_prompt = None
        self._confirm_result = None

    def on_input_bar_cancel_requested(self, event: InputBar.CancelRequested) -> None:
        bar = self.query_one(InputBar)
        if self._confirm_prompt is not None and self._confirm_result is not None:
            self._resolve_confirm(False)
            return
        if bar._busy:
            self._cancel_event.set()
            chat = self.query_one(ChatLog)
            chat.set_canceling()

    def _run_agent(self, user_input: str) -> None:
        self._cancel_event.clear()
        self._confirmed_tools.clear()
        self._turn_start = time.monotonic()
        chat = self.query_one(ChatLog)
        bar = self.query_one(InputBar)
        self._stop_thinking_animation()
        chat.show_thinking()
        bar.set_busy(True)
        self._start_thinking_animation()
        asyncio.create_task(self._agent_loop(user_input))

    async def _agent_loop(self, user_input: str) -> None:
        loop = asyncio.get_event_loop()
        skip_add_user = False
        bar = self.query_one(InputBar)

        while True:
            self._cancel_event.clear()
            chat = self.query_one(ChatLog)
            self._stop_thinking_animation()
            chat.show_thinking()
            self._start_thinking_animation()

            try:
                result = await loop.run_in_executor(
                    None,
                    self._agent.run,
                    user_input,
                    self._cancel_event,
                    self._confirmed_tools,
                    skip_add_user,
                )
            except Exception as e:
                self._stop_thinking_animation()
                chat.hide_thinking()
                chat.add_message("assistant", f"[Error] {e}")
                self._mount_turn_timing(chat)
                bar.set_busy(False)
                return

            self._stop_thinking_animation()
            chat.hide_thinking()

            if self._cancel_event.is_set():
                chat.add_message("assistant", "[ESC] 已中断")
                self._mount_turn_timing(chat)
                bar.set_busy(False)
                return

            if result.startswith("[CONFIRM_REQUIRED]"):
                self._stop_thinking_animation()
                chat.hide_thinking()

                parts = result.split()
                tool_id = parts[1] if len(parts) >= 2 else ""
                pending = getattr(self._agent, '_pending_confirm', None)
                if pending and len(pending) >= 3:
                    _, tool_name, tool_args, _ = pending
                    approved = await self._show_confirm_inline(tool_name, str(tool_args))

                    if approved:
                        self._confirmed_tools.add(tool_id)
                        should_continue, exec_result = await loop.run_in_executor(
                            None,
                            self._agent.confirm_pending,
                            self._confirmed_tools,
                        )
                        content = format_tool_content(tool_name, tool_args if isinstance(tool_args, dict) else {})
                        chat.add_message("tool", f"{content}: approved", tool_name=tool_name)
                        if should_continue:
                            # Continue the loop — agent will get next response
                            user_input = ""
                            skip_add_user = True
                            bar.set_busy(True)
                            continue
                        else:
                            # Agent finished after confirmation
                            self._process_agent_result(exec_result)
                            bar.set_busy(False)
                            return
                    else:
                        if tool_id and self._agent._pending_confirm:
                            _, tname, targs, _ = self._agent._pending_confirm
                            self._agent.context.add_assistant_message([{
                                "type": "tool_use",
                                "id": tool_id,
                                "name": tname,
                                "input": targs,
                            }])
                            self._agent.context.add_tool_result(tool_id, "[已拒绝] 用户拒绝了此危险操作")
                        self._agent._pending_confirm = None
                        self._agent._pending_response = None
                        self._agent._confirmed_results = []
                        content = format_tool_content(tool_name, tool_args if isinstance(tool_args, dict) else {})
                        chat.add_message("tool", f"{content}: rejected", tool_name=tool_name)
                        bar.set_busy(False)
                        return
                else:
                    chat.add_message("assistant", "[Error] Confirmation state lost")
                    bar.set_busy(False)
                    return

            self._process_agent_result(result)
            bar.set_busy(False)
            return

    async def _show_confirm_inline(self, tool_name: str, tool_args: str) -> bool:
        """Show inline confirm prompt in ChatLog, wait for y/n."""
        chat = self.query_one(ChatLog)
        bar = self.query_one(InputBar)

        prompt = ConfirmPrompt(tool_name, tool_args)
        self._confirm_prompt = prompt
        self._confirm_result = asyncio.get_event_loop().create_future()

        chat.mount(prompt)
        chat.call_after_refresh(chat.scroll_end, animate=False)

        # Switch input to confirm mode
        bar._input.value = ""
        bar._input.placeholder = "y/n?"
        bar._input.disabled = False
        bar._input.focus()

        # Wait for user response
        result = await self._confirm_result

        # Restore input to normal mode
        bar.set_busy(False)

        return result

    def _mount_turn_timing(self, chat: ChatLog) -> None:
        """在聊天末尾挂载本轮耗时汇总。"""
        from tui.widgets.chat import TurnTiming
        if self._turn_start > 0:
            elapsed = time.monotonic() - self._turn_start
            chat.mount(TurnTiming(elapsed))
            chat.call_after_refresh(chat.scroll_end, animate=False)

    def _process_agent_result(self, result: str) -> None:
        from tui.widgets.chat import TurnTiming
        chat = self.query_one(ChatLog)
        chat.add_message("assistant", result)
        self._mount_turn_timing(chat)
        self._step_count += 1
        status = self.query_one(StatusBar)
        status.update_steps(self._step_count)
        # 累积 token 使用量
        usage = getattr(self._agent.llm_adapter, '_last_usage', None)
        if usage:
            try:
                self._total_input_tokens += getattr(usage, 'input_tokens', 0) or 0
                self._total_output_tokens += getattr(usage, 'output_tokens', 0) or 0
            except Exception:
                pass
            status.update_tokens(self._total_input_tokens, self._total_output_tokens)

    def _start_thinking_animation(self) -> None:
        self._thinking_task = asyncio.create_task(self._thinking_animation_loop())

    def _stop_thinking_animation(self) -> None:
        if self._thinking_task is not None:
            self._thinking_task.cancel()
            self._thinking_task = None

    async def _thinking_animation_loop(self) -> None:
        chat = self.query_one(ChatLog)
        try:
            while True:
                chat.update_thinking()
                if self._turn_start > 0 and chat._thinking_indicator is not None:
                    elapsed = time.monotonic() - self._turn_start
                    chat._thinking_indicator.set_elapsed(elapsed)
                await asyncio.sleep(0.08)
        except asyncio.CancelledError:
            pass

    def action_clear_screen(self) -> None:
        chat = self.query_one(ChatLog)
        from tui.widgets.chat import UserMessage, AssistantMessage, TurnTiming
        from tui.widgets.tool_card import ToolCard
        for widget_type in (UserMessage, AssistantMessage, ToolCard, TurnTiming):
            chat.query(widget_type).remove()
        chat._thinking_indicator = None
        chat._streaming_message = None

    def action_quit(self) -> None:
        if self._exiting:
            return
        self._exiting = True
        chat = self.query_one(ChatLog)
        chat.mount(GoodbyeWidget())

    def on_goodbye_widget_goodbye_done(self, event: GoodbyeWidget.GoodbyeDone) -> None:
        App.exit(self)

    def exit(self, result=None) -> None:
        self.action_quit()