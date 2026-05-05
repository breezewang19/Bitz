from __future__ import annotations

import asyncio
import os
import threading
import time
from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Static
from textual.events import Key

from tui.theme import BITZ_CSS, set_theme_colors
from tui.widgets.banner import BannerWidget, GoodbyeWidget
from tui.widgets.chat import ChatLog, format_tool_content, ThinkingIndicator, SubAgentCard
from tui.widgets.confirm import ConfirmPrompt
from tui.widgets.input import InputBar
from tui.widgets.status import StatusBar
from tui.widgets.model_select import ModelSelectScreen
from tui.widgets.model_add import ModelAddScreen
from tui.widgets.model_confirm import ModelConfirmScreen
from tui.widgets.task_list import TaskListWidget
from agent.tasks import get_project_slug
from agent.skills import SkillRegistry

if TYPE_CHECKING:
    from agent.loop import Agent


class BitzApp(App):
    CSS = BITZ_CSS

    BINDINGS = [
        ("ctrl+l", "clear_screen", "Clear"),
        Binding("ctrl+c", "copy_text", "Copy", priority=True),
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, agent: Agent, model_store=None, skill_registry=None, session_store=None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._agent = agent
        self._model_store = model_store
        self._skill_registry = skill_registry or SkillRegistry()
        self._session_store = session_store
        self._original_execute = agent.tools.execute
        self._cancel_event = threading.Event()
        self._subagent_cards: dict = {}
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
        yield ThinkingIndicator()
        yield TaskListWidget(id="task-list", project_slug=get_project_slug())
        yield StatusBar()
        yield InputBar(skill_registry=self._skill_registry)

    def on_mount(self) -> None:
        chat = self.query_one(ChatLog)
        model_name = self._agent.llm_adapter.model
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
        set_theme_colors(self.theme)
        self._install_tool_logger()
        self._install_retry_logger()
        self._install_text_callback()
        # Show restore banner if there are history sessions
        if self._session_store:
            latest = self._session_store.get_latest_session()
            if latest and latest.session_id != self._agent.context.session_id:
                from tui.widgets.session_banner import SessionRestoreBanner
                chat.mount(SessionRestoreBanner(title=latest.title or "无标题", turn_count=latest.turn_count))

    def on_theme_changed(self, event) -> None:
        """Sync COLORS dict when user switches theme."""
        set_theme_colors(self.theme)

    def _install_tool_logger(self) -> None:
        """Monkey-patch tools.execute to log tool calls to UI via ToolCard."""
        import difflib

        original = self._original_execute
        app = self

        def logged_execute(name, args, confirmed=False, tool_id=None, agent=None, on_event=None):
            # spawn 工具特殊处理：显示 SubAgentCard + 实时日志
            if name == "spawn":
                tasks = args.get("tasks", []) if isinstance(args, dict) else []
                task_desc = (args.get("task", "") if isinstance(args, dict) else "") or f"{len(tasks)} 个并发任务"
                count = 1 if (args.get("task", "") if isinstance(args, dict) else "") else len(tasks)
                card = SubAgentCard(task=task_desc, count=count, agent_type=args.get("agent_type", "general-purpose") if isinstance(args, dict) else "general-purpose")
                chat = app.query_one(ChatLog)
                app.call_from_thread(chat.mount, card)
                card_key = f"spawn_{id(card)}"
                app._subagent_cards[card_key] = card

                def on_event(event_type, task_index, **kwargs):
                    """桥接 SubAgent 事件到 SubAgentCard"""
                    try:
                        if event_type == "task_start":
                            app.call_from_thread(card.add_task, task_index, kwargs.get("task_name", f"任务{task_index + 1}"))
                        elif event_type == "text":
                            line = f"  {kwargs['text'][:80]}"
                            app.call_from_thread(card.append_log, task_index, line)
                        elif event_type == "tool_start":
                            line = f"⟳ {kwargs['tool_name']}: {kwargs.get('args_summary', '')[:40]}"
                            app.call_from_thread(card.append_log, task_index, line)
                        elif event_type == "tool_end":
                            pass  # 工具结束不单独显示，省空间
                        elif event_type == "done":
                            app.call_from_thread(
                                card.complete_task, task_index,
                                kwargs.get("success", False), kwargs.get("steps", 0),
                                kwargs.get("elapsed", 0.0), kwargs.get("error", ""),
                                tokens=kwargs.get("tokens", 0)
                            )
                    except Exception:
                        pass

                result = original(name, args, confirmed=confirmed, tool_id=tool_id, agent=agent, on_event=on_event)
                app._subagent_cards.pop(card_key, None)
                return result

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

                result = original(name, args, confirmed=confirmed, tool_id=tool_id, agent=agent, on_event=None)
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

                # Refresh task list after task tool execution (thread-safe)
                if name.startswith("task_"):
                    try:
                        task_widget = app.query_one("#task-list", TaskListWidget)
                        app.call_from_thread(task_widget.refresh_tasks)
                    except Exception:
                        pass
                    # Also update task count in StatusBar
                    try:
                        from agent.tasks import list_tasks as _list_tasks, get_project_slug as _get_slug, TaskStatus as _TS
                        _slug = _get_slug()
                        _tasks = _list_tasks(_slug)
                        _in_progress = sum(1 for t in _tasks if t.status == _TS.IN_PROGRESS)
                        status_bar = app.query_one(StatusBar)
                        app.call_from_thread(status_bar.update_task_count, _in_progress, len(_tasks))
                    except Exception:
                        pass
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

    def _install_text_callback(self) -> None:
        """设置 Agent 的中间文字输出回调，让 LLM 的自言自语显示在 UI。"""
        app = self

        def on_text(text: str) -> None:
            try:
                app.call_from_thread(app._show_intermediate_text, text)
            except Exception:
                pass

        self._agent._on_text = on_text

    def _show_intermediate_text(self, text: str) -> None:
        chat = self.query_one(ChatLog)
        chat.add_message("assistant", text)

    def _set_tool_running(self, tool_name: str | None) -> None:
        """Thread-safe: update thinking indicator to show tool running state."""
        try:
            self.call_from_thread(self._update_tool_running, tool_name)
        except Exception:
            pass

    def _update_tool_running(self, tool_name: str | None) -> None:
        try:
            indicator = self.query_one(ThinkingIndicator)
            indicator.set_tool(tool_name)
        except Exception:
            pass

    
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
        # Set first_prompt and title on first user message
        if self._session_store and self._agent.context.session_id:
            meta = self._session_store.get_meta(self._agent.context.session_id)
            if not meta.first_prompt:
                prompt_text = event.text[:80]
                self._session_store.update_meta(
                    self._agent.context.session_id,
                    first_prompt=prompt_text,
                    title=prompt_text,
                )
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
                "| `/new` | 开始新对话 |\n"
                "| `/clear` | 清屏 |\n"
                "| `/compact` | 压缩上下文 |\n"
                "| `/theme [name]` | 切换主题（无参数时循环切换）|\n"
                "| `/models` | 模型管理弹窗 |\n"
                "| `/models list` | 列出已配置模型（文本） |\n"
                "| `/models add <id> <protocol> <base_url> <api_key> <model>` | 添加模型（文本） |\n"
                "| `/models <id>` | 切换模型（文本） |\n"
                "| `/skill` | 列出可用 Skill |\n"
                "| `/skill off` | 清除当前 Skill |\n"
                "| `/sessions` | 打开会话历史列表 |\n"
                "| `/resume [id]` | 恢复指定会话（无id时恢复最近的） |\n"
                "| `/title <text>` | 设置当前会话标题 |\n"
            )
            # 追加 Skill 列表
            skills = self._skill_registry.list_all()
            if skills:
                help_text += "\n\n## 可用 Skill\n"
                for s in skills:
                    help_text += f"- {s.trigger} — {s.description}\n"
            chat.add_message("assistant", help_text)
        elif command == "new":
            self.action_new_conversation()
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
        elif command == "models":
            self._handle_models_command(args, chat)
        elif command == "skill":
            if args == "off":
                if self._agent.context.active_skill:
                    self._agent.context.clear_active_skill()
                    chat.add_message("assistant", "已清除当前 Skill。")
                else:
                    chat.add_message("assistant", "当前没有激活的 Skill。")
            else:
                skills = self._skill_registry.list_all()
                if not skills:
                    chat.add_message("assistant", "没有可用的 Skill。\n在 .bitz/skills/ 目录下创建 .md 文件即可添加自定义 Skill。")
                else:
                    lines = ["## 可用 Skill", ""]
                    for s in skills:
                        lines.append(f"- **{s.trigger}** — {s.description}")
                    active = self._agent.context.active_skill
                    if active:
                        lines.append(f"\n当前激活: **{active.name}** ({active.trigger})")
                    chat.add_message("assistant", "\n".join(lines))
        elif command == "sessions":
            if self._session_store:
                from tui.widgets.session_list import SessionListScreen
                self.push_screen(SessionListScreen(self._session_store))
            else:
                chat.add_message("assistant", "会话管理未启用")
        elif command == "resume":
            if self._session_store:
                target_id = args.strip() if args.strip() else None
                if target_id:
                    self._do_resume_session(target_id)
                else:
                    latest = self._session_store.get_latest_session()
                    if latest:
                        self._do_resume_session(latest.session_id)
                    else:
                        chat.add_message("assistant", "没有历史会话可恢复")
            else:
                chat.add_message("assistant", "会话管理未启用")
        elif command == "title":
            if args.strip() and self._session_store and self._agent.context.session_id:
                self._session_store.update_meta(
                    self._agent.context.session_id,
                    title=args.strip(),
                )
                chat.add_message("assistant", f"会话标题已设置为: {args.strip()}")
            else:
                chat.add_message("assistant", "用法: /title <标题文本>")
        elif self._skill_registry.get_by_trigger(f"/{command}"):
            skill = self._skill_registry.get_by_trigger(f"/{command}")
            self._activate_skill(skill)
        else:
            chat.add_message("assistant", f"未知命令: /{command}。输入 /help 查看可用命令。")

    def _handle_models_command(self, args: str, chat: ChatLog) -> None:
        """处理 /models 命令"""
        if not self._model_store:
            chat.add_message("assistant", "模型管理未启用")
            return

        parts = args.strip().split()

        if not parts:
            # 无参数 → 弹窗模式
            self.push_screen(ModelSelectScreen(self._model_store), self._on_models_result)
            return

        if parts[0] == "list":
            models = self._model_store.list_all()
            current = self._model_store.get_current()
            current_id = current.id if current else None
            rows = []
            for m in models:
                marker = " ←" if m.id == current_id else ""
                rows.append(f"| {m.id} | {m.protocol} | {m.model} | {m.masked_key()} |{marker}")
            table = (
                "## 已配置模型\n\n"
                "| ID | 协议 | 模型 | API Key |\n"
                "|------|------|------|--------|\n"
                + "\n".join(rows)
            )
            chat.add_message("assistant", table)

        elif parts[0] == "add":
            if len(parts) != 6:
                chat.add_message("assistant", "用法: /models add <id> <protocol> <base_url> <api_key> <model>")
                return
            id_, protocol, base_url, api_key, model = parts[1:]
            if protocol not in ("openai", "anthropic"):
                chat.add_message("assistant", f"不支持的协议: {protocol}，可选: openai, anthropic")
                return
            try:
                from agent.models import ModelConfig
                config = ModelConfig(id=id_, protocol=protocol, base_url=base_url, api_key=api_key, model=model)
                self._model_store.add(config)
                chat.add_message("assistant", f"模型 '{id_}' 已添加")
            except ValueError as e:
                chat.add_message("assistant", str(e))

        else:
            # 切换模型: /models <id>
            model_id = parts[0]
            config = self._model_store.get(model_id)
            if config is None:
                chat.add_message("assistant", f"模型 '{model_id}' 不存在")
                return
            self._switch_model(config)

    def _activate_skill(self, skill) -> None:
        """激活 Skill，注入到上下文，提示用户。"""
        self._agent.context.set_active_skill(skill)
        chat = self.query_one(ChatLog)
        msg = f"已激活 Skill: **{skill.name}** — {skill.description}\n输入你的问题，我将按 `{skill.trigger}` 流程处理。"
        if skill.skill_dir:
            msg += f"\n（目录型 Skill，规则文件位于: {skill.skill_dir}）"
        chat.add_message("assistant", msg)

    def _check_auto_trigger(self, text: str):
        """检测 LLM 回复是否以 /skill-name 开头，返回匹配的 Skill 或 None。"""
        stripped = text.strip()
        if not stripped.startswith("/"):
            return None
        for skill in self._skill_registry.list_all():
            if skill.auto_trigger and stripped.startswith(skill.trigger):
                return skill
        return None

    def _switch_model(self, config) -> None:
        """切换当前模型"""
        adapter = self._agent.llm_adapter
        adapter.api_key = config.api_key
        adapter.base_url = config.base_url
        adapter.model = config.model
        adapter.protocol = config.protocol
        if config.protocol == "openai":
            adapter.api_url = f"{config.base_url}/chat/completions"
        else:
            adapter.api_url = f"{config.base_url}/v1/messages"
        adapter._last_usage = None
        self._model_store.set_current(config.id)
        status = self.query_one(StatusBar)
        status.update_model(config.model)
        chat = self.query_one(ChatLog)
        chat.add_message("assistant", f"已切换到模型: {config.id} ({config.protocol}/{config.model})")

    def _on_models_result(self, result) -> None:
        """ModelSelectScreen 回调。"""
        if result is None:
            return
        action, data = result
        chat = self.query_one(ChatLog)
        if action == "switch":
            config = self._model_store.get(data)
            if config:
                self._switch_model(config)
        elif action == "add":
            self.push_screen(ModelAddScreen(), self._on_model_added)
        elif action == "delete":
            # 不允许删除当前模型
            current = self._model_store.get_current()
            if current and data == current.id:
                chat.add_message("assistant", "无法删除当前使用的模型，请先切换")
                return
            # 不允许删除最后一个模型
            if len(self._model_store.list_all()) <= 1:
                chat.add_message("assistant", "至少需要保留一个模型")
                return
            self.push_screen(ModelConfirmScreen(data), self._on_model_deleted)

    def on_session_list_screen_resume(self, event) -> None:
        """SessionListScreen 恢复回调。"""
        self._do_resume_session(event.session_id)

    def on_session_list_screen_delete(self, event) -> None:
        """SessionListScreen 删除回调。"""
        chat = self.query_one(ChatLog)
        chat.add_message("assistant", f"会话 {event.session_id[:8]}... 已删除")

    def _do_resume_session(self, session_id: str) -> None:
        """恢复指定会话。"""
        from agent.session import restore_session
        from agent.prompt import build_system_prompt

        chat = self.query_one(ChatLog)
        if not self._session_store:
            chat.add_message("assistant", "会话管理未启用")
            return

        context, meta = restore_session(
            self._session_store,
            session_id,
            system_prompt=build_system_prompt(cwd=os.getcwd(), skill_registry=self._skill_registry),
        )
        self._agent.context = context

        # Re-render ChatLog
        for child in list(chat.children):
            child.remove()

        for msg in context.messages:
            role = msg["role"]
            content = msg["content"]
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        chat.add_message("tool", block.get("content", "")[:200], tool_name="tool")
                    elif isinstance(block, dict) and block.get("type") == "tool_use":
                        chat.add_message("tool", f"{block['name']}: {str(block.get('input', ''))[:80]}", tool_name=block["name"])
                    elif isinstance(block, dict) and block.get("type") == "text":
                        chat.add_message("assistant", block["text"])
            elif isinstance(content, str):
                if role == "user":
                    chat.add_message("user", content)
                else:
                    chat.add_message("assistant", content)

        chat.mount(BannerWidget(model_name=self._agent.llm_adapter.model))
        chat.add_message("assistant", f"已恢复会话: **{meta.title or '无标题'}** ({meta.turn_count}轮)")

    def _on_model_added(self, result) -> None:
        """ModelAddScreen 回调。"""
        if result is None:
            return
        action, data = result
        if action == "error":
            # 显示带错误信息的表单
            self.push_screen(ModelAddScreen(error=data), self._on_model_added)
            return
        if action == "data":
            from agent.models import ModelConfig
            try:
                config = ModelConfig(**data)
                self._model_store.add(config)
                chat = self.query_one(ChatLog)
                chat.add_message("assistant", f"模型 '{config.id}' 已添加")
            except ValueError as e:
                self.push_screen(ModelAddScreen(error=str(e)), self._on_model_added)

    def _on_model_deleted(self, result) -> None:
        """ModelConfirmScreen 回调。"""
        if result is None:
            return
        action, model_id = result
        self._model_store.remove(model_id)
        chat = self.query_one(ChatLog)
        chat.add_message("assistant", f"模型 '{model_id}' 已删除")

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
            self.query_one(ThinkingIndicator).set_canceling()
            event.prevent_default()

    def copy_to_clipboard(self, text: str) -> None:
        """复制到剪贴板（Windows 用 Win32 API，其他系统用 OSC 52）"""
        if os.name == "nt":
            try:
                import ctypes
                from ctypes import wintypes
                CF_UNICODETEXT = 13
                kernel32 = ctypes.windll.kernel32
                user32 = ctypes.windll.user32
                kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
                kernel32.GlobalLock.restype = wintypes.c_void_p
                buf = (len(text) + 1) * 2
                h = kernel32.GlobalAlloc(0x0042, buf)
                p = kernel32.GlobalLock(h)
                ctypes.cdll.msvcrt.wcscpy_s(wintypes.LPWSTR(p), len(text) + 1, text)
                kernel32.GlobalUnlock(h)
                user32.OpenClipboard(0)
                user32.EmptyClipboard()
                user32.SetClipboardData(CF_UNICODETEXT, h)
                user32.CloseClipboard()
                self._clipboard = text
                return
            except Exception:
                pass
        super().copy_to_clipboard(text)

    def action_copy_text(self) -> None:
        """Ctrl+C: 复制选中文本到剪贴板，不取消运行"""
        selected = self.screen.get_selected_text()
        if selected:
            self.copy_to_clipboard(selected)
            self.notify("已复制到剪贴板", severity="information", timeout=2)
        else:
            self.notify("按 Ctrl+Q 退出", severity="information", timeout=2)

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
            self.query_one(ThinkingIndicator).set_canceling()

    def _run_agent(self, user_input: str) -> None:
        self._cancel_event.clear()
        self._confirmed_tools.clear()
        self._turn_start = time.monotonic()
        bar = self.query_one(InputBar)
        self._stop_thinking_animation()
        self.query_one(ThinkingIndicator).show()
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
            self.query_one(ThinkingIndicator).show()
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
                self.query_one(ThinkingIndicator).hide()
                chat.add_message("assistant", f"[Error] {e}")
                self._mount_turn_timing(chat)
                bar.set_busy(False)
                return

            self._stop_thinking_animation()
            self.query_one(ThinkingIndicator).hide()

            if self._cancel_event.is_set():
                chat.add_message("assistant", "[ESC] 已中断")
                self._mount_turn_timing(chat)
                bar.set_busy(False)
                return

            if result.startswith("[CONFIRM_REQUIRED]"):
                self._stop_thinking_animation()
                self.query_one(ThinkingIndicator).hide()

                parts = result.split()
                tool_id = parts[1] if len(parts) >= 2 else ""
                pending = getattr(self._agent, '_pending_confirms', None)
                if pending:
                    # Show confirm prompt for the first pending tool
                    _, tool_name, tool_args, _ = pending[0]
                    if len(pending) > 1:
                        tool_args = f"{len(pending)} 个操作需要确认: {tool_name} 等"
                    approved = await self._show_confirm_inline(tool_name, str(tool_args))

                    if approved:
                        should_continue, exec_result = await loop.run_in_executor(
                            None,
                            self._agent.confirm_pending,
                            self._confirmed_tools,
                        )
                        if should_continue:
                            user_input = ""
                            skip_add_user = True
                            bar.set_busy(True)
                            continue
                        else:
                            self._process_agent_result(exec_result)
                            bar.set_busy(False)
                            return
                    else:
                        # Deny all pending tools
                        self._update_tool_result(tool_name, "denied", is_error=True)
                        for tid, tname, targs, _ in pending:
                            self._agent.context.add_assistant_message([{
                                "type": "tool_use",
                                "id": tid,
                                "name": tname,
                                "input": targs,
                            }])
                            self._agent.context.add_tool_result(tid, "[已拒绝] 用户拒绝了此危险操作")
                        self._agent._pending_confirms = None
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

        # Switch input to confirm mode — 禁用输入，只允许 y/n/左右键
        bar._input.value = ""
        bar._input.placeholder = "y/n?"
        bar._input.disabled = True

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
        # 自动触发检测：LLM 回复以 /skill-name 开头时自动激活
        triggered = self._check_auto_trigger(result)
        if triggered is not None:
            # 去掉 trigger 前缀，显示剩余内容
            remaining = result.strip()[len(triggered.trigger):].strip()
            if remaining:
                chat.add_message("assistant", remaining)
            self._activate_skill(triggered)
            return
        chat.add_message("assistant", result)
        self._mount_turn_timing(chat)
        self._step_count += 1
        status = self.query_one(StatusBar)
        status.update_steps(self._step_count)
        # 累积 token 使用量（从 adapter 的累积总量读取，而非单次 _last_usage）
        adapter = self._agent.llm_adapter
        self._total_input_tokens = adapter._total_input_tokens
        self._total_output_tokens = adapter._total_output_tokens
        # 加上子 Agent 的 token（如果有的话）
        status = self.query_one(StatusBar)
        if self._total_input_tokens > 0 or self._total_output_tokens > 0:
            status.update_tokens(self._total_input_tokens, self._total_output_tokens)
        # Update session meta after each turn
        if self._session_store and self._agent.context.session_id:
            self._session_store.update_meta(
                self._agent.context.session_id,
                turn_count=self._step_count,
            )
        # Sync persistence error state
        if hasattr(self._agent.context, '_persist_error'):
            status = self.query_one(StatusBar)
            status.update_persistence_error(self._agent.context._persist_error)

    def _start_thinking_animation(self) -> None:
        self._thinking_task = asyncio.create_task(self._thinking_animation_loop())

    def _stop_thinking_animation(self) -> None:
        if self._thinking_task is not None:
            self._thinking_task.cancel()
            self._thinking_task = None

    async def _thinking_animation_loop(self) -> None:
        try:
            while True:
                try:
                    indicator = self.query_one(ThinkingIndicator)
                    indicator.advance()
                    if self._turn_start > 0:
                        elapsed = time.monotonic() - self._turn_start
                        indicator.set_elapsed(elapsed)
                except Exception:
                    pass
                await asyncio.sleep(0.08)
        except asyncio.CancelledError:
            pass

    def action_clear_screen(self) -> None:
        chat = self.query_one(ChatLog)
        from tui.widgets.chat import UserMessage, AssistantMessage, TurnTiming
        from tui.widgets.tool_card import ToolCard
        for widget_type in (UserMessage, AssistantMessage, ToolCard, TurnTiming):
            chat.query(widget_type).remove()

    def action_new_conversation(self) -> None:
        """清空对话和上下文，开始新对话。"""
        # Finalize old session meta
        if self._session_store and self._agent.context.session_id:
            self._session_store.update_meta(self._agent.context.session_id)
        chat = self.query_one(ChatLog)
        # 清空所有聊天内容
        for child in list(chat.children):
            child.remove()
        # 清空 Agent 上下文
        self._agent.context.messages.clear()
        self._agent.context.clear_active_skill()
        # Create new session
        if self._session_store:
            model = self._agent.llm_adapter.model
            new_session_id = self._session_store.create_session(model=model)
            self._agent.context.session_id = new_session_id
            self._agent.context._store = self._session_store
        # 重置计数器
        self._step_count = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._agent.llm_adapter._total_input_tokens = 0
        self._agent.llm_adapter._total_output_tokens = 0
        status = self.query_one(StatusBar)
        status.update_steps(0)
        status.update_tokens(0, 0)
        # 重新挂载 Banner
        model_name = self._agent.llm_adapter.model
        chat.mount(BannerWidget(model_name=model_name))

    def on_session_restore_banner_restore(self, event) -> None:
        if self._session_store:
            latest = self._session_store.get_latest_session()
            if latest:
                self._do_resume_session(latest.session_id)

    def on_session_restore_banner_skip(self, event) -> None:
        pass  # Banner already removed itself

    def action_quit(self) -> None:
        if self._exiting:
            return
        # Finalize session meta on quit
        if self._session_store and self._agent.context.session_id:
            self._session_store.update_meta(self._agent.context.session_id)
        self._exiting = True
        chat = self.query_one(ChatLog)
        chat.mount(GoodbyeWidget())

    def on_goodbye_widget_goodbye_done(self, event: GoodbyeWidget.GoodbyeDone) -> None:
        App.exit(self)

    def exit(self, result=None) -> None:
        self.action_quit()