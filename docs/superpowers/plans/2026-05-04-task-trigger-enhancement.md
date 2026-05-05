# Task Trigger Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance Bitz's task system trigger mechanisms — enrich tool descriptions, add system prompt guidance, and implement task reminder nudges — to match Claude Code's effectiveness.

**Architecture:** Three independent enhancements: (1) replace 1-sentence tool descriptions with detailed Chinese prompts in `builtin_tools.py`, (2) add task tool guidance bullet to `prompt.py` RULES, (3) create `task_reminder.py` pure function module + integrate into `loop.py` + add `add_system_reminder()` to `context.py`.

**Tech Stack:** Python 3.11+, pytest, existing agent framework (loop.py, context.py, builtin_tools.py, prompt.py)

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `agent/builtin_tools.py` | Modify | Replace 4 task tool `description` fields with detailed Chinese prompts |
| `agent/prompt.py` | Modify | Add task tool guidance bullet to RULES |
| `agent/task_reminder.py` | **New** | Pure functions: `should_remind()`, `get_task_summary()`, constants |
| `agent/loop.py` | Modify | Add reminder check after tool results written, track task tool usage |
| `agent/context.py` | Modify | Add `add_system_reminder()`, strip `_meta` in `get_messages()` |
| `tests/test_task_reminder.py` | **New** | Unit tests for `should_remind()` and `get_task_summary()` |
| `tests/test_context.py` | Modify | Tests for `add_system_reminder()` and `_meta` stripping |
| `tests/test_task_tools.py` | Modify | Add description content tests |
| `tests/test_prompt.py` | **New** | Verify RULES contains task guidance |

---

### Task 1: Enrich task_create description

**Files:**
- Modify: `agent/builtin_tools.py:456`
- Test: `tests/test_task_tools.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_task_tools.py`:

```python
class TestTaskToolDescriptions:
    def test_task_create_description_has_when_to_use(self):
        tools = create_tools()
        desc = tools.tools["task_create"].description
        assert "何时使用" in desc
        assert "何时不使用" in desc
        assert "字段" in desc
        assert "提示" in desc
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_task_tools.py::TestTaskToolDescriptions::test_task_create_description_has_when_to_use -v`
Expected: FAIL (current description is 1 sentence, no "何时使用")

- [ ] **Step 3: Replace task_create description**

In `agent/builtin_tools.py`, replace the `description` string in the `task_create` `tools.register()` call (line 456) with:

```python
description=(
    "为当前编码会话创建结构化任务列表，帮助跟踪进度、组织复杂任务。\n"
    "\n"
    "## 何时使用\n"
    "- 复杂多步骤任务（3 步以上）\n"
    "- 需要仔细规划或多步操作的任务\n"
    "- 用户给出多个任务（编号或逗号分隔）\n"
    "- 收到新指令后，立即将需求捕获为任务\n"
    "- 开始工作时，先标记为 in_progress\n"
    "\n"
    "## 何时不使用\n"
    "- 单一简单任务\n"
    "- 任务可在 3 步以内轻松完成\n"
    "- 纯对话或信息查询\n"
    "\n"
    "## 字段\n"
    "- subject: 简短的祈使句标题（如\"修复登录流程的认证 bug\"）\n"
    "- description: 详细需求说明\n"
    "- activeForm: 进行中时显示在 spinner 的文本（如\"修复认证 bug\"），省略则显示 subject\n"
    "\n"
    "所有任务创建时状态为 pending。\n"
    "\n"
    "## 提示\n"
    "- 创建后用 task_update 设置依赖关系（blocks/blockedBy）\n"
    "- 先用 task_list 检查，避免创建重复任务"
),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_task_tools.py::TestTaskToolDescriptions::test_task_create_description_has_when_to_use -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/builtin_tools.py tests/test_task_tools.py
git commit -m "feat: enrich task_create tool description with detailed Chinese prompt"
```

---

### Task 2: Enrich task_update, task_list, task_get descriptions

**Files:**
- Modify: `agent/builtin_tools.py:471,506,515`
- Test: `tests/test_task_tools.py`

- [ ] **Step 1: Write the failing tests**

Add to `TestTaskToolDescriptions` in `tests/test_task_tools.py`:

```python
    def test_task_update_description_has_completion_conditions(self):
        tools = create_tools()
        desc = tools.tools["task_update"].description
        assert "何时使用" in desc
        assert "完成条件" in desc
        assert "可更新字段" in desc
        assert "示例" in desc

    def test_task_list_description_has_output(self):
        tools = create_tools()
        desc = tools.tools["task_list"].description
        assert "何时使用" in desc
        assert "输出" in desc

    def test_task_get_description_has_tips(self):
        tools = create_tools()
        desc = tools.tools["task_get"].description
        assert "何时使用" in desc
        assert "提示" in desc
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_task_tools.py::TestTaskToolDescriptions -v`
Expected: FAIL (3 new tests fail)

- [ ] **Step 3: Replace task_update description**

In `agent/builtin_tools.py`, replace the `description` string in the `task_update` `tools.register()` call (line 471) with:

```python
description=(
    "更新任务列表中的任务。\n"
    "\n"
    "## 何时使用\n"
    "- 开始工作时标记为 in_progress\n"
    "- 完成工作时标记为 completed\n"
    "- 任务不再需要时标记为 deleted\n"
    "- 需求变化时更新描述\n"
    "- 设置任务间依赖关系\n"
    "\n"
    "## 完成条件\n"
    "仅在以下情况标记 completed：\n"
    "- 测试通过\n"
    "- 实现完整\n"
    "- 无未解决错误\n"
    "\n"
    "如果遇到阻塞或无法完成，保持 in_progress 并创建新任务描述阻塞原因。\n"
    "\n"
    "## 可更新字段\n"
    "- status: pending → in_progress → completed；deleted 永久删除\n"
    "- subject/description/activeForm: 更新任务内容\n"
    "- metadata: 合并元数据（设为 null 删除键）\n"
    "- add_blocks: 标记此任务完成后才能开始的任务\n"
    "- add_blocked_by: 标记必须先完成的任务\n"
    "\n"
    "## 示例\n"
    "开始工作：{\"task_id\": \"1\", \"status\": \"in_progress\"}\n"
    "完成工作：{\"task_id\": \"1\", \"status\": \"completed\"}\n"
    "删除任务：{\"task_id\": \"1\", \"status\": \"deleted\"}\n"
    "设置依赖：{\"task_id\": \"2\", \"add_blocked_by\": [\"1\"]}"
),
```

- [ ] **Step 4: Replace task_list description**

In `agent/builtin_tools.py`, replace the `description` string in the `task_list` `tools.register()` call (line 506) with:

```python
description=(
    "列出任务列表中的所有任务。\n"
    "\n"
    "## 何时使用\n"
    "- 查看可用任务（pending 且未被阻塞）\n"
    "- 检查项目整体进度\n"
    "- 寻找被阻塞的任务\n"
    "- 完成一个任务后，查看下一个可用任务\n"
    "- 多个任务可用时，优先按 ID 顺序处理（低 ID 先做）\n"
    "\n"
    "## 输出\n"
    "每条任务显示：#id [状态] 标题，如有未解决的阻塞则显示 [blocked by #id]"
),
```

- [ ] **Step 5: Replace task_get description**

In `agent/builtin_tools.py`, replace the `description` string in the `task_get` `tools.register()` call (line 515) with:

```python
description=(
    "按 ID 获取任务详情。\n"
    "\n"
    "## 何时使用\n"
    "- 开始工作前获取完整描述和上下文\n"
    "- 理解任务依赖（它阻塞谁、谁阻塞它）\n"
    "- 获取完整需求后再开始工作\n"
    "\n"
    "## 输出\n"
    "- subject: 任务标题\n"
    "- description: 详细需求和上下文\n"
    "- status: pending/in_progress/completed\n"
    "- blocks: 等待此任务完成的任务\n"
    "- blockedBy: 必须先完成的任务\n"
    "\n"
    "## 提示\n"
    "- 获取任务后，先检查 blockedBy 是否为空再开始工作\n"
    "- 用 task_list 查看所有任务概览"
),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_task_tools.py::TestTaskToolDescriptions -v`
Expected: PASS (all 4 tests)

- [ ] **Step 7: Commit**

```bash
git add agent/builtin_tools.py tests/test_task_tools.py
git commit -m "feat: enrich task_update/list/get tool descriptions with detailed Chinese prompts"
```

---

### Task 3: Add task tool guidance to system prompt

**Files:**
- Modify: `agent/prompt.py:13-28`
- Test: `tests/test_prompt.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_prompt.py`:

```python
"""Tests for system prompt assembly."""
from agent.prompt import RULES


def test_rules_contains_task_tool_guidance():
    """RULES should mention task_create and task_update."""
    assert "task_create" in RULES
    assert "task_update" in RULES
    assert "in_progress" in RULES
    assert "completed" in RULES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_prompt.py -v`
Expected: FAIL (RULES currently has no mention of task tools)

- [ ] **Step 3: Add task tool guidance to RULES**

In `agent/prompt.py`, add a bullet to the `## 工具使用` section in `RULES`, after the existing `fetch` bullet (after line 18):

```python
"- 用 task_create 拆分复杂任务，用 task_update 跟踪进度（开始时标记 in_progress，完成时标记 completed），不要批量标记完成\n"
```

The full modified RULES should be:

```python
RULES = """## 工具使用
- 优先用 read_file/glob/grep 了解代码，再用 edit_file/write_file 修改
- bash 用于运行命令和测试，避免用 bash 做文件读写
- 修改文件前先读取确认内容，避免盲改
- 用 glob 按模式搜索文件，用 grep 按内容搜索
- fetch 仅用于获取网页内容，不要用它读本地文件
- 用 task_create 拆分复杂任务，用 task_update 跟踪进度（开始时标记 in_progress，完成时标记 completed），不要批量标记完成

## 输出
- 用中文回复
- 代码只给关键部分，不重复整个文件
- 解释要简洁，重点说 why 不说 what

## 安全
- 不要执行 rm -rf /、格式化磁盘等破坏性操作
- 不要在代码中硬编码密钥、密码等敏感信息
- 不要运行来源不明的 curl | sh 命令"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_prompt.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/prompt.py tests/test_prompt.py
git commit -m "feat: add task tool guidance to system prompt RULES"
```

---

### Task 4: Create task_reminder.py module

**Files:**
- Create: `agent/task_reminder.py`
- Test: `tests/test_task_reminder.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_task_reminder.py`:

```python
"""Tests for task reminder logic."""
import pytest
from agent.task_reminder import should_remind, get_task_summary, TASK_TOOL_NAMES, REMINDER_THRESHOLD, REMINDER_COOLDOWN


class TestShouldRemind:
    def test_returns_none_when_threshold_not_met(self):
        result = should_remind(
            step_count=5,
            last_task_tool_step=0,
            last_reminder_step=None,
            task_summary=None,
        )
        assert result is None

    def test_returns_none_when_cooldown_not_met(self):
        result = should_remind(
            step_count=20,
            last_task_tool_step=0,
            last_reminder_step=15,
            task_summary=None,
        )
        assert result is None

    def test_returns_reminder_when_thresholds_met_no_tasks(self):
        result = should_remind(
            step_count=10,
            last_task_tool_step=0,
            last_reminder_step=None,
            task_summary=None,
        )
        assert result is not None
        assert "task_create" in result
        assert "task_update" in result
        assert "当前任务" not in result

    def test_returns_reminder_with_task_list(self):
        summary = "#1 [pending] Fix bug\n#2 [in_progress] Write tests"
        result = should_remind(
            step_count=10,
            last_task_tool_step=0,
            last_reminder_step=None,
            task_summary=summary,
        )
        assert result is not None
        assert "当前任务" in result
        assert "#1 [pending] Fix bug" in result

    def test_returns_none_when_last_task_tool_step_is_none_and_count_low(self):
        result = should_remind(
            step_count=5,
            last_task_tool_step=None,
            last_reminder_step=None,
            task_summary=None,
        )
        assert result is None

    def test_returns_reminder_when_last_task_tool_step_is_none_and_count_high(self):
        result = should_remind(
            step_count=10,
            last_task_tool_step=None,
            last_reminder_step=None,
            task_summary=None,
        )
        assert result is not None

    def test_cooldown_prevents_rapid_re_reminders(self):
        # First reminder at step 10
        result1 = should_remind(
            step_count=10,
            last_task_tool_step=0,
            last_reminder_step=None,
            task_summary=None,
        )
        assert result1 is not None
        # Step 15: cooldown not met (last_reminder was at step 10)
        result2 = should_remind(
            step_count=15,
            last_task_tool_step=0,
            last_reminder_step=10,
            task_summary=None,
        )
        assert result2 is None
        # Step 20: cooldown met
        result3 = should_remind(
            step_count=20,
            last_task_tool_step=0,
            last_reminder_step=10,
            task_summary=None,
        )
        assert result3 is not None

    def test_reminder_includes_do_not_mention(self):
        result = should_remind(
            step_count=10,
            last_task_tool_step=0,
            last_reminder_step=None,
            task_summary=None,
        )
        assert "不要向用户提及此提醒" in result


class TestGetTaskSummary:
    def test_returns_none_when_no_active_tasks(self, tmp_path):
        from agent.tasks import create_task, TaskStatus
        slug = "test-reminder"
        base_dir = tmp_path / ".bitz" / "tasks"
        # Create a completed task — should be filtered out
        t = create_task(slug, "Done", "Desc", base_dir=base_dir)
        from agent.tasks import update_task
        update_task(slug, t.id, status="completed", base_dir=base_dir)
        result = get_task_summary(slug, base_dir=base_dir)
        assert result is None

    def test_returns_formatted_string_when_active_tasks_exist(self, tmp_path):
        from agent.tasks import create_task
        slug = "test-reminder"
        base_dir = tmp_path / ".bitz" / "tasks"
        create_task(slug, "Fix bug", "Desc", base_dir=base_dir)
        create_task(slug, "Write tests", "Desc", base_dir=base_dir)
        result = get_task_summary(slug, base_dir=base_dir)
        assert result is not None
        assert "#1 [pending] Fix bug" in result
        assert "#2 [pending] Write tests" in result

    def test_filters_internal_tasks(self, tmp_path):
        from agent.tasks import create_task
        slug = "test-reminder"
        base_dir = tmp_path / ".bitz" / "tasks"
        create_task(slug, "Internal", "Desc", metadata={"_internal": True}, base_dir=base_dir)
        create_task(slug, "External", "Desc", base_dir=base_dir)
        result = get_task_summary(slug, base_dir=base_dir)
        assert result is not None
        assert "External" in result
        assert "Internal" not in result

    def test_excludes_completed_tasks(self, tmp_path):
        from agent.tasks import create_task, update_task
        slug = "test-reminder"
        base_dir = tmp_path / ".bitz" / "tasks"
        create_task(slug, "Pending", "Desc", base_dir=base_dir)
        t2 = create_task(slug, "Completed", "Desc", base_dir=base_dir)
        update_task(slug, t2.id, status="completed", base_dir=base_dir)
        result = get_task_summary(slug, base_dir=base_dir)
        assert result is not None
        assert "Pending" in result
        assert "Completed" not in result


class TestConstants:
    def test_task_tool_names(self):
        assert "task_create" in TASK_TOOL_NAMES
        assert "task_update" in TASK_TOOL_NAMES
        assert "task_list" in TASK_TOOL_NAMES
        assert "task_get" in TASK_TOOL_NAMES

    def test_threshold_values(self):
        assert REMINDER_THRESHOLD == 10
        assert REMINDER_COOLDOWN == 10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_task_reminder.py -v`
Expected: FAIL (module `agent.task_reminder` does not exist)

- [ ] **Step 3: Create `agent/task_reminder.py`**

```python
# agent/task_reminder.py
"""Task reminder — nudge agent to use task tools after prolonged disuse."""
from __future__ import annotations


TASK_TOOL_NAMES = {"task_create", "task_update", "task_list", "task_get"}
REMINDER_THRESHOLD = 10  # steps since last task tool use
REMINDER_COOLDOWN = 10   # steps between reminders

_NUDGE = (
    "你最近没有使用任务工具。如果正在处理多步骤任务，"
    "考虑用 task_create 创建新任务，用 task_update 更新状态"
    "（开始时 in_progress，完成时 completed）。"
    "不要向用户提及此提醒。"
)


def should_remind(
    step_count: int,
    last_task_tool_step: int | None,
    last_reminder_step: int | None,
    task_summary: str | None,
) -> str | None:
    """Check whether a task reminder should be injected.

    Args:
        step_count: Current agent step count.
        last_task_tool_step: Step count when a task tool was last used, or None.
        last_reminder_step: Step count when a reminder was last injected, or None.
        task_summary: Formatted task list string, or None if no active tasks.

    Returns the reminder text, or None if no reminder is needed.
    """
    # Check threshold: steps since last task tool use
    if last_task_tool_step is not None:
        if step_count - last_task_tool_step < REMINDER_THRESHOLD:
            return None
    else:
        # Never used a task tool — use step_count as proxy
        if step_count < REMINDER_THRESHOLD:
            return None

    # Check cooldown: steps since last reminder
    if last_reminder_step is not None:
        if step_count - last_reminder_step < REMINDER_COOLDOWN:
            return None

    # Build reminder
    if task_summary:
        return f"{_NUDGE}\n\n当前任务：\n{task_summary}"
    return _NUDGE


def get_task_summary(project_slug: str, base_dir: str | None = None) -> str | None:
    """Return a formatted task list string for active tasks, or None.

    Filtering mirrors task_list_handler in builtin_tools.py:
    exclude _internal tasks, show only pending/in_progress.
    """
    from agent.tasks import list_tasks
    all_tasks = list_tasks(project_slug, base_dir=base_dir)
    active = [t for t in all_tasks
              if t.status.value in ("pending", "in_progress")
              and not t.metadata.get("_internal")]
    if not active:
        return None
    lines = [f"#{t.id} [{t.status.value}] {t.subject}" for t in active]
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_task_reminder.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add agent/task_reminder.py tests/test_task_reminder.py
git commit -m "feat: add task_reminder module with should_remind and get_task_summary"
```

---

### Task 5: Add add_system_reminder to Context and strip _meta in get_messages

**Files:**
- Modify: `agent/context.py:102-115`
- Test: `tests/test_context.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_context.py`:

```python
def test_context_add_system_reminder():
    """add_system_reminder appends a user message with _meta flag."""
    ctx = Context(system_prompt="test")
    ctx.add_system_reminder("Don't forget to use task tools!")
    assert len(ctx.messages) == 1
    assert ctx.messages[0]["role"] == "user"
    assert ctx.messages[0]["content"] == "Don't forget to use task tools!"
    assert ctx.messages[0].get("_meta") is True


def test_context_get_messages_strips_meta():
    """get_messages strips _meta key before returning to API."""
    ctx = Context(system_prompt="test", keep_last_n=5)
    ctx.add_user("Hello")
    ctx.add_system_reminder("Use task tools!")
    msgs = ctx.get_messages()
    # System prompt + user message + reminder message
    assert len(msgs) == 3
    # Reminder message should NOT have _meta key
    reminder_msg = msgs[2]
    assert reminder_msg["role"] == "user"
    assert reminder_msg["content"] == "Use task tools!"
    assert "_meta" not in reminder_msg


def test_context_add_system_reminder_trims():
    """add_system_reminder calls _trim like other add methods."""
    ctx = Context(system_prompt="test", keep_last_n=2)
    ctx.add_user("Message 1")
    ctx.add_user("Message 2")
    ctx.add_system_reminder("Reminder")
    # After trim, only last 2 messages kept
    assert len(ctx.messages) == 2
    assert ctx.messages[0]["content"] == "Message 2"
    assert ctx.messages[1]["content"] == "Reminder"


def test_context_add_system_reminder_no_persist():
    """add_system_reminder intentionally skips _persist (ephemeral)."""
    store = FakeSessionStore()
    ctx = Context(system_prompt="test", session_id="s1", session_store=store)
    ctx.add_user("hello")
    ctx.add_system_reminder("reminder")
    # Only the user message should be persisted, not the reminder
    assert len(store.entries) == 1
    assert store.entries[0]["content"] == "hello"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_context.py::test_context_add_system_reminder -v`
Expected: FAIL (AttributeError: 'Context' object has no attribute 'add_system_reminder')

- [ ] **Step 3: Add add_system_reminder method to Context**

In `agent/context.py`, add after the `add_tool_results` method (after line 60):

```python
    def add_system_reminder(self, text: str) -> None:
        """Add a system reminder as a user message.

        The reminder is stored with a _meta key for internal tracking.
        get_messages() strips _meta before returning messages to the API.
        Intentionally skips _persist(): reminders are ephemeral nudges.
        """
        self.messages.append({
            "role": "user",
            "content": text,
            "_meta": True,
        })
        self._trim()
```

- [ ] **Step 4: Modify get_messages to strip _meta**

In `agent/context.py`, replace the `get_messages` method (lines 102-115) with:

```python
    def get_messages(self) -> list[dict]:
        """返回完整消息列表（system 作为独立条目），剥离非标准键"""
        msgs = [{"role": "system", "content": self.system_prompt}]
        for msg in self.messages:
            clean = {k: v for k, v in msg.items() if k in ("role", "content")}
            msgs.append(clean)

        if self._active_skill:
            skill = self._active_skill
            if skill.skill_dir:
                skill_section = f"\n\n{skill.summary()}"
            else:
                skill_section = f"\n\n[当前 Skill: {skill.name}]\n{skill.prompt}"
            msgs[0] = {**msgs[0], "content": msgs[0]["content"] + skill_section}

        return msgs
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_context.py -v`
Expected: PASS (all existing + 4 new tests)

- [ ] **Step 6: Commit**

```bash
git add agent/context.py tests/test_context.py
git commit -m "feat: add add_system_reminder to Context, strip _meta in get_messages"
```

---

### Task 6: Integrate task reminder into Agent loop

**Files:**
- Modify: `agent/loop.py:10-24,127-131,141-187`
- Test: `tests/test_task_reminder.py` (add integration-level tests)

- [ ] **Step 1: Write the failing tests for loop integration**

Add to `tests/test_task_reminder.py`:

```python
class TestReminderIntegration:
    """Tests for how should_remind would be called from the loop."""

    def test_step_count_resets_after_task_tool_use(self):
        """After using a task tool, the threshold counter resets."""
        # Step 5: task tool used
        last_task_tool_step = 5
        # Step 14: threshold met (14 - 5 = 9, not yet)
        result = should_remind(14, last_task_tool_step, None, None)
        assert result is None
        # Step 15: threshold met (15 - 5 = 10)
        result = should_remind(15, last_task_tool_step, None, None)
        assert result is not None

    def test_reminder_not_injected_when_task_tool_recently_used(self):
        """If task tool was used recently, no reminder even at high step count."""
        result = should_remind(100, 95, None, None)
        assert result is None

    def test_all_four_task_tools_count(self):
        """All 4 task tools should be in TASK_TOOL_NAMES."""
        assert TASK_TOOL_NAMES == {"task_create", "task_update", "task_list", "task_get"}
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_task_reminder.py::TestReminderIntegration -v`
Expected: PASS (these test should_remind logic, not loop.py directly)

- [ ] **Step 3: Add import and state fields to Agent.__init__**

In `agent/loop.py`, add import at the top (after line 4):

```python
from agent.task_reminder import should_remind, get_task_summary, TASK_TOOL_NAMES
from agent.tasks import get_project_slug
```

Add fields to `Agent.__init__` (after line 23, before `self.permission_mode`):

```python
        self._last_task_tool_step: int | None = None
        self._last_reminder_step: int | None = None
```

- [ ] **Step 2: Add reminder check after tool results in tool_use branch**

In `agent/loop.py`, after the `self.context.add_tool_results(...)` call (after line 130, before `continue`), add:

```python
                # Task reminder: check for task tool usage and inject reminder
                for tool_id, tool_name, tool_args, result in confirmed_results:
                    if tool_name in TASK_TOOL_NAMES:
                        self._last_task_tool_step = self._step_count
                        break
                summary = get_task_summary(get_project_slug())
                reminder = should_remind(
                    step_count=self._step_count,
                    last_task_tool_step=self._last_task_tool_step,
                    last_reminder_step=self._last_reminder_step,
                    task_summary=summary,
                )
                if reminder:
                    self.context.add_system_reminder(reminder)
                    self._last_reminder_step = self._step_count
```

- [ ] **Step 3: Add reminder check in confirm_pending path**

In `agent/loop.py`, after the `self.context.add_tool_results(...)` call in `confirm_pending` (after line 186, before `return`), add:

```python
        # Task reminder: check for task tool usage in confirmed results
        for tool_id, tool_name, tool_args, result in all_results:
            if tool_name in TASK_TOOL_NAMES:
                self._last_task_tool_step = self._step_count
                break
        summary = get_task_summary(get_project_slug())
        reminder = should_remind(
            step_count=self._step_count,
            last_task_tool_step=self._last_task_tool_step,
            last_reminder_step=self._last_reminder_step,
            task_summary=summary,
        )
        if reminder:
            self.context.add_system_reminder(reminder)
            self._last_reminder_step = self._step_count
```

- [ ] **Step 4: Run existing tests to verify no regressions**

Run: `.venv/bin/python -m pytest tests/ -v --timeout=30`
Expected: PASS (all existing tests still pass)

- [ ] **Step 5: Commit**

```bash
git add agent/loop.py
git commit -m "feat: integrate task reminder into Agent loop and confirm_pending"
```

---

### Task 7: Final verification

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v --timeout=30`
Expected: All tests pass

- [ ] **Step 2: Verify tool descriptions are rich**

Run: `.venv/bin/python -c "from agent.builtin_tools import create_tools; t = create_tools(); [print(k, len(v.description)) for k, v in t.tools.items() if k.startswith('task_')]"`
Expected: Each task tool description is >100 chars (was ~30-50 before)

- [ ] **Step 3: Verify RULES contains task guidance**

Run: `.venv/bin/python -c "from agent.prompt import RULES; print('task_create' in RULES, 'task_update' in RULES)"`
Expected: True True

- [ ] **Step 4: Verify task_reminder module works**

Run: `.venv/bin/python -c "from agent.task_reminder import should_remind; print(should_remind(10, 0, None, None))"`
Expected: Non-None output with nudge text

- [ ] **Step 5: Final commit if any fixes needed**

```bash
git add agent/ tests/ docs/
git commit -m "fix: address any issues found during final verification"
```
