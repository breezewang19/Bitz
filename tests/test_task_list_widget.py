"""TaskListWidget TUI tests"""
import pytest
from pathlib import Path
from textual.app import App, ComposeResult
from tui.widgets.task_list import TaskListWidget
from agent.tasks import (
    create_task,
    list_tasks,
    update_task,
    block_task,
    TaskStatus,
)


class TaskListTestApp(App):
    CSS = ""

    def __init__(self, project_slug: str, base_dir: Path, **kwargs):
        super().__init__(**kwargs)
        self.project_slug = project_slug
        self.base_dir = base_dir

    def compose(self) -> ComposeResult:
        yield TaskListWidget(project_slug=self.project_slug, base_dir=self.base_dir)


@pytest.fixture
def task_app(tmp_path):
    slug = "test-project"
    base_dir = tmp_path / ".bitz" / "tasks"
    base_dir.mkdir(parents=True, exist_ok=True)
    app = TaskListTestApp(project_slug=slug, base_dir=base_dir)
    return app, base_dir, slug


@pytest.mark.asyncio
async def test_renders_empty_state(task_app):
    """No tasks -> widget has no content."""
    app, tdir, slug = task_app
    async with app.run_test() as pilot:
        widget = app.query_one(TaskListWidget)
        assert widget.has_content is False


@pytest.mark.asyncio
async def test_renders_tasks(task_app):
    """Create a task -> shows in widget."""
    app, tdir, slug = task_app
    create_task(slug, "Do something", "desc", base_dir=tdir)
    async with app.run_test() as pilot:
        widget = app.query_one(TaskListWidget)
        assert widget.has_content is True
        content = str(widget.renderable)
        assert "Do something" in content


@pytest.mark.asyncio
async def test_shows_active_form_for_in_progress(task_app):
    """In-progress task shows activeForm instead of subject."""
    app, tdir, slug = task_app
    t = create_task(slug, "Build feature", "desc", active_form="Building feature",
                    base_dir=tdir)
    update_task(slug, t.id, status="in_progress", base_dir=tdir)
    async with app.run_test() as pilot:
        widget = app.query_one(TaskListWidget)
        content = str(widget.renderable)
        assert "Building feature" in content


@pytest.mark.asyncio
async def test_shows_blocked_status(task_app):
    """Blocked task shows 'blocked' indicator."""
    app, tdir, slug = task_app
    t1 = create_task(slug, "First task", "desc", base_dir=tdir)
    t2 = create_task(slug, "Second task", "desc", base_dir=tdir)
    block_task(slug, t1.id, t2.id, base_dir=tdir)
    async with app.run_test() as pilot:
        widget = app.query_one(TaskListWidget)
        content = str(widget.renderable)
        assert "blocked" in content.lower()
