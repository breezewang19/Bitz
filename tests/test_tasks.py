"""Task data model and persistence CRUD tests"""
import json
import pytest
from pathlib import Path
from agent.tasks import (
    Task,
    TaskStatus,
    get_project_slug,
    _get_tasks_dir,
    _read_highwatermark,
    _write_highwatermark,
    _max_id_from_filenames,
    _next_id,
    _ensure_dir,
    create_task,
    get_task,
    list_tasks,
    update_task,
    delete_task,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tasks_dir(tmp_path):
    """Return a tasks directory path under tmp_path."""
    slug = "test-project"
    d = tmp_path / ".bitz" / "tasks" / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def slug():
    return "test-project"


@pytest.fixture
def base_dir(tmp_path):
    """Override base dir so tasks go to tmp_path instead of ~/.bitz."""
    return tmp_path / ".bitz" / "tasks"


def _write_task_file(tasks_dir: Path, task: Task):
    """Helper: write a task JSON file directly."""
    path = tasks_dir / f"{task.id}.json"
    path.write_text(json.dumps(task.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# TestTaskModel
# ---------------------------------------------------------------------------

class TestTaskModel:
    def test_task_status_enum_values(self):
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.IN_PROGRESS == "in_progress"
        assert TaskStatus.COMPLETED == "completed"

    def test_task_creation_defaults(self):
        t = Task(id="1", subject="Fix bug", description="Details here")
        assert t.id == "1"
        assert t.subject == "Fix bug"
        assert t.description == "Details here"
        assert t.activeForm is None
        assert t.status == TaskStatus.PENDING
        assert t.blocks == []
        assert t.blockedBy == []
        assert t.metadata == {}

    def test_task_creation_with_all_fields(self):
        t = Task(
            id="2",
            subject="Write tests",
            description="Write unit tests",
            activeForm="Writing tests",
            status=TaskStatus.IN_PROGRESS,
            blocks=["3"],
            blockedBy=["1"],
            metadata={"priority": "high"},
        )
        assert t.activeForm == "Writing tests"
        assert t.status == TaskStatus.IN_PROGRESS
        assert t.blocks == ["3"]
        assert t.blockedBy == ["1"]
        assert t.metadata == {"priority": "high"}

    def test_task_to_dict(self):
        t = Task(id="1", subject="Test", description="Desc")
        d = t.to_dict()
        assert d["id"] == "1"
        assert d["subject"] == "Test"
        assert d["status"] == "pending"  # string, not enum
        assert isinstance(d["status"], str)

    def test_task_to_dict_in_progress(self):
        t = Task(id="1", subject="Test", description="Desc", status=TaskStatus.IN_PROGRESS)
        d = t.to_dict()
        assert d["status"] == "in_progress"

    def test_task_from_dict(self):
        data = {
            "id": "5",
            "subject": "Refactor",
            "description": "Refactor the code",
            "activeForm": "Refactoring",
            "status": "in_progress",
            "blocks": ["6"],
            "blockedBy": ["3"],
            "metadata": {"tag": "cleanup"},
        }
        t = Task.from_dict(data)
        assert t.id == "5"
        assert t.status == TaskStatus.IN_PROGRESS
        assert t.blocks == ["6"]
        assert t.metadata == {"tag": "cleanup"}

    def test_task_from_dict_minimal(self):
        data = {"id": "1", "subject": "Test", "description": "Desc", "status": "pending"}
        t = Task.from_dict(data)
        assert t.activeForm is None
        assert t.blocks == []
        assert t.blockedBy == []
        assert t.metadata == {}


# ---------------------------------------------------------------------------
# TestCreateTask
# ---------------------------------------------------------------------------

class TestCreateTask:
    def test_create_first_task(self, slug, base_dir):
        t = create_task(slug, "Fix bug", "Fix the login bug", base_dir=base_dir)
        assert t.id == "1"
        assert t.subject == "Fix bug"
        assert t.description == "Fix the login bug"
        assert t.status == TaskStatus.PENDING
        assert t.blocks == []
        assert t.blockedBy == []
        assert t.metadata == {}

    def test_create_second_task_increments_id(self, slug, base_dir):
        t1 = create_task(slug, "First", "First task", base_dir=base_dir)
        t2 = create_task(slug, "Second", "Second task", base_dir=base_dir)
        assert t1.id == "1"
        assert t2.id == "2"

    def test_create_with_active_form(self, slug, base_dir):
        t = create_task(slug, "Run tests", "Run all tests", active_form="Running tests", base_dir=base_dir)
        assert t.activeForm == "Running tests"

    def test_create_with_metadata(self, slug, base_dir):
        t = create_task(slug, "Task", "Desc", metadata={"priority": "high"}, base_dir=base_dir)
        assert t.metadata == {"priority": "high"}

    def test_create_writes_json_file(self, slug, base_dir):
        t = create_task(slug, "Task", "Desc", base_dir=base_dir)
        tasks_dir = _get_tasks_dir(slug, base_dir)
        assert (tasks_dir / "1.json").exists()
        data = json.loads((tasks_dir / "1.json").read_text(encoding="utf-8"))
        assert data["id"] == "1"
        assert data["subject"] == "Task"

    def test_create_updates_highwatermark(self, slug, base_dir):
        create_task(slug, "Task 1", "Desc", base_dir=base_dir)
        create_task(slug, "Task 2", "Desc", base_dir=base_dir)
        tasks_dir = _get_tasks_dir(slug, base_dir)
        hw = _read_highwatermark(tasks_dir)
        assert hw == 2

    def test_create_auto_creates_directory(self, slug, base_dir):
        # base_dir may not exist yet
        t = create_task(slug, "Task", "Desc", base_dir=base_dir)
        tasks_dir = _get_tasks_dir(slug, base_dir)
        assert tasks_dir.exists()
        assert (tasks_dir / "1.json").exists()


# ---------------------------------------------------------------------------
# TestGetTask
# ---------------------------------------------------------------------------

class TestGetTask:
    def test_get_existing_task(self, slug, base_dir):
        create_task(slug, "Test task", "A test", base_dir=base_dir)
        t = get_task(slug, "1", base_dir=base_dir)
        assert t is not None
        assert t.id == "1"
        assert t.subject == "Test task"

    def test_get_nonexistent_task(self, slug, base_dir):
        t = get_task(slug, "999", base_dir=base_dir)
        assert t is None

    def test_get_task_from_corrupt_json(self, slug, base_dir):
        tasks_dir = _get_tasks_dir(slug, base_dir)
        _ensure_dir(tasks_dir)
        # Write a corrupt JSON file
        (tasks_dir / "1.json").write_text("NOT JSON{{{", encoding="utf-8")
        t = get_task(slug, "1", base_dir=base_dir)
        assert t is None  # should not crash, just return None


# ---------------------------------------------------------------------------
# TestListTasks
# ---------------------------------------------------------------------------

class TestListTasks:
    def test_list_empty(self, slug, base_dir):
        tasks = list_tasks(slug, base_dir=base_dir)
        assert tasks == []

    def test_list_multiple_tasks(self, slug, base_dir):
        create_task(slug, "First", "Desc 1", base_dir=base_dir)
        create_task(slug, "Second", "Desc 2", base_dir=base_dir)
        tasks = list_tasks(slug, base_dir=base_dir)
        assert len(tasks) == 2
        ids = {t.id for t in tasks}
        assert ids == {"1", "2"}

    def test_list_includes_internal_tasks(self, slug, base_dir):
        create_task(slug, "Internal", "Desc", metadata={"_internal": True}, base_dir=base_dir)
        create_task(slug, "External", "Desc", base_dir=base_dir)
        tasks = list_tasks(slug, base_dir=base_dir)
        # list_tasks returns ALL tasks including _internal
        assert len(tasks) == 2

    def test_list_skips_corrupt_json(self, slug, base_dir):
        create_task(slug, "Good task", "Desc", base_dir=base_dir)
        tasks_dir = _get_tasks_dir(slug, base_dir)
        # Write a corrupt file
        (tasks_dir / "99.json").write_text("BAD JSON", encoding="utf-8")
        tasks = list_tasks(slug, base_dir=base_dir)
        assert len(tasks) == 1
        assert tasks[0].subject == "Good task"

    def test_list_nonexistent_directory(self, slug, base_dir):
        # Use a slug that has no directory
        tasks = list_tasks("nonexistent-project-slug", base_dir=base_dir)
        assert tasks == []


# ---------------------------------------------------------------------------
# TestUpdateTask
# ---------------------------------------------------------------------------

class TestUpdateTask:
    def test_update_subject(self, slug, base_dir):
        create_task(slug, "Old subject", "Desc", base_dir=base_dir)
        t = update_task(slug, "1", subject="New subject", base_dir=base_dir)
        assert t is not None
        assert t.subject == "New subject"

    def test_update_status(self, slug, base_dir):
        create_task(slug, "Task", "Desc", base_dir=base_dir)
        t = update_task(slug, "1", status=TaskStatus.IN_PROGRESS, base_dir=base_dir)
        assert t is not None
        assert t.status == TaskStatus.IN_PROGRESS

    def test_update_active_form(self, slug, base_dir):
        create_task(slug, "Task", "Desc", base_dir=base_dir)
        t = update_task(slug, "1", active_form="Working on task", base_dir=base_dir)
        assert t is not None
        assert t.activeForm == "Working on task"

    def test_update_description(self, slug, base_dir):
        create_task(slug, "Task", "Old desc", base_dir=base_dir)
        t = update_task(slug, "1", description="New desc", base_dir=base_dir)
        assert t is not None
        assert t.description == "New desc"

    def test_update_metadata_merges(self, slug, base_dir):
        create_task(slug, "Task", "Desc", metadata={"a": 1, "b": 2}, base_dir=base_dir)
        t = update_task(slug, "1", metadata={"b": 20, "c": 3}, base_dir=base_dir)
        assert t is not None
        assert t.metadata == {"a": 1, "b": 20, "c": 3}

    def test_update_metadata_null_deletes_key(self, slug, base_dir):
        create_task(slug, "Task", "Desc", metadata={"a": 1, "b": 2}, base_dir=base_dir)
        t = update_task(slug, "1", metadata={"a": None}, base_dir=base_dir)
        assert t is not None
        assert "a" not in t.metadata
        assert t.metadata == {"b": 2}

    def test_update_add_blocks(self, slug, base_dir):
        create_task(slug, "Task 1", "Desc", base_dir=base_dir)
        create_task(slug, "Task 2", "Desc", base_dir=base_dir)
        t = update_task(slug, "1", add_blocks=["2"], base_dir=base_dir)
        assert t is not None
        assert "2" in t.blocks
        # Also check task 2 got blockedBy
        t2 = get_task(slug, "2", base_dir=base_dir)
        assert "1" in t2.blockedBy

    def test_update_add_blocked_by(self, slug, base_dir):
        create_task(slug, "Task 1", "Desc", base_dir=base_dir)
        create_task(slug, "Task 2", "Desc", base_dir=base_dir)
        t = update_task(slug, "2", add_blocked_by=["1"], base_dir=base_dir)
        assert t is not None
        assert "1" in t.blockedBy
        # Also check task 1 got blocks
        t1 = get_task(slug, "1", base_dir=base_dir)
        assert "2" in t1.blocks

    def test_update_nonexistent_task(self, slug, base_dir):
        t = update_task(slug, "999", subject="Nope", base_dir=base_dir)
        assert t is None

    def test_update_status_deleted_calls_delete(self, slug, base_dir):
        create_task(slug, "Task", "Desc", base_dir=base_dir)
        result = update_task(slug, "1", status="deleted", base_dir=base_dir)
        # After deletion, get_task should return None
        assert get_task(slug, "1", base_dir=base_dir) is None

    def test_update_persists_to_disk(self, slug, base_dir):
        create_task(slug, "Task", "Desc", base_dir=base_dir)
        update_task(slug, "1", subject="Updated", base_dir=base_dir)
        # Read from disk directly
        tasks_dir = _get_tasks_dir(slug, base_dir)
        data = json.loads((tasks_dir / "1.json").read_text(encoding="utf-8"))
        assert data["subject"] == "Updated"


# ---------------------------------------------------------------------------
# TestDeleteTask
# ---------------------------------------------------------------------------

class TestDeleteTask:
    def test_delete_existing_task(self, slug, base_dir):
        create_task(slug, "Task", "Desc", base_dir=base_dir)
        result = delete_task(slug, "1", base_dir=base_dir)
        assert result is True
        assert get_task(slug, "1", base_dir=base_dir) is None

    def test_delete_nonexistent_task(self, slug, base_dir):
        result = delete_task(slug, "999", base_dir=base_dir)
        assert result is False

    def test_delete_updates_highwatermark(self, slug, base_dir):
        create_task(slug, "Task 1", "Desc", base_dir=base_dir)
        create_task(slug, "Task 2", "Desc", base_dir=base_dir)
        delete_task(slug, "2", base_dir=base_dir)
        tasks_dir = _get_tasks_dir(slug, base_dir)
        hw = _read_highwatermark(tasks_dir)
        assert hw == 2  # highwatermark should be at least 2

    def test_delete_does_not_lower_highwatermark(self, slug, base_dir):
        create_task(slug, "Task 1", "Desc", base_dir=base_dir)
        create_task(slug, "Task 2", "Desc", base_dir=base_dir)
        create_task(slug, "Task 3", "Desc", base_dir=base_dir)
        # Highwatermark is 3
        delete_task(slug, "2", base_dir=base_dir)
        # highwatermark should still be 3 (max of current_hw and deleted_id)
        tasks_dir = _get_tasks_dir(slug, base_dir)
        hw = _read_highwatermark(tasks_dir)
        assert hw == 3

    def test_deleted_id_not_reused(self, slug, base_dir):
        t1 = create_task(slug, "Task 1", "Desc", base_dir=base_dir)
        t2 = create_task(slug, "Task 2", "Desc", base_dir=base_dir)
        delete_task(slug, "2", base_dir=base_dir)
        t3 = create_task(slug, "Task 3", "Desc", base_dir=base_dir)
        # Task 3 should get id "3", not "2"
        assert t3.id == "3"

    def test_delete_cleans_up_dependency_references(self, slug, base_dir):
        # Task 1 blocks task 2
        create_task(slug, "Task 1", "Desc", base_dir=base_dir)
        create_task(slug, "Task 2", "Desc", base_dir=base_dir)
        update_task(slug, "1", add_blocks=["2"], base_dir=base_dir)
        # Verify dependency is set
        t1 = get_task(slug, "1", base_dir=base_dir)
        t2 = get_task(slug, "2", base_dir=base_dir)
        assert "2" in t1.blocks
        assert "1" in t2.blockedBy
        # Delete task 1
        delete_task(slug, "1", base_dir=base_dir)
        # Task 2's blockedBy should no longer reference task 1
        t2 = get_task(slug, "2", base_dir=base_dir)
        assert "1" not in t2.blockedBy

    def test_delete_removes_json_file(self, slug, base_dir):
        create_task(slug, "Task", "Desc", base_dir=base_dir)
        tasks_dir = _get_tasks_dir(slug, base_dir)
        assert (tasks_dir / "1.json").exists()
        delete_task(slug, "1", base_dir=base_dir)
        assert not (tasks_dir / "1.json").exists()


# ---------------------------------------------------------------------------
# Test helper functions
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_get_project_slug(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        slug = get_project_slug()
        assert isinstance(slug, str)
        assert len(slug) > 0

    def test_get_tasks_dir(self, slug, base_dir):
        d = _get_tasks_dir(slug, base_dir)
        assert str(d).endswith(slug)

    def test_read_highwatermark_missing_file(self, tasks_dir):
        assert _read_highwatermark(tasks_dir) == 0

    def test_write_and_read_highwatermark(self, tasks_dir):
        _write_highwatermark(tasks_dir, 5)
        assert _read_highwatermark(tasks_dir) == 5

    def test_max_id_from_filenames_empty(self, tasks_dir):
        assert _max_id_from_filenames(tasks_dir) == 0

    def test_max_id_from_filenames_with_files(self, tasks_dir):
        (tasks_dir / "1.json").write_text("{}", encoding="utf-8")
        (tasks_dir / "3.json").write_text("{}", encoding="utf-8")
        assert _max_id_from_filenames(tasks_dir) == 3

    def test_max_id_ignores_non_numeric(self, tasks_dir):
        (tasks_dir / "abc.json").write_text("{}", encoding="utf-8")
        (tasks_dir / "2.json").write_text("{}", encoding="utf-8")
        assert _max_id_from_filenames(tasks_dir) == 2

    def test_next_id_increments(self, tasks_dir):
        assert _next_id(tasks_dir) == 1
        _write_highwatermark(tasks_dir, 1)
        assert _next_id(tasks_dir) == 2

    def test_next_id_respects_highwatermark(self, tasks_dir):
        # Write a highwatermark but no files
        _write_highwatermark(tasks_dir, 5)
        assert _next_id(tasks_dir) == 6

    def test_ensure_dir_creates_directory(self, tmp_path):
        d = tmp_path / "nested" / "dir"
        assert not d.exists()
        _ensure_dir(d)
        assert d.exists()
