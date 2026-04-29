# Bitz/tests/test_skills.py
import pytest
import tempfile
import os
from agent.skills import Skill, SkillRegistry


class TestSkillDataclass:
    def test_skill_creation(self):
        skill = Skill(
            name="code-review",
            description="审查代码质量",
            trigger="/review",
            prompt="你是代码审查专家...",
            source="builtin",
        )
        assert skill.name == "code-review"
        assert skill.trigger == "/review"
        assert skill.source == "builtin"


class TestSkillRegistryLoad:
    def test_load_single_skill_file(self, tmp_path):
        """测试从目录加载单个 Skill 文件"""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        (skill_dir / "code-review.md").write_text(
            "---\nname: code-review\ndescription: 审查代码质量\ntrigger: /review\n---\n你是代码审查专家。\n",
            encoding="utf-8",
        )
        registry = SkillRegistry()
        registry.load_builtin(str(skill_dir))
        skill = registry.get("code-review")
        assert skill is not None
        assert skill.name == "code-review"
        assert skill.description == "审查代码质量"
        assert skill.trigger == "/review"
        assert "代码审查专家" in skill.prompt
        assert skill.source == "builtin"

    def test_load_multiple_skill_files(self, tmp_path):
        """测试从目录加载多个 Skill 文件"""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        (skill_dir / "code-review.md").write_text(
            "---\nname: code-review\ndescription: 审查代码\ntrigger: /review\n---\n审查流程\n",
            encoding="utf-8",
        )
        (skill_dir / "debug.md").write_text(
            "---\nname: debug\ndescription: 调试排错\ntrigger: /debug\n---\n调试流程\n",
            encoding="utf-8",
        )
        registry = SkillRegistry()
        registry.load_builtin(str(skill_dir))
        assert len(registry.list_all()) == 2
        assert registry.get("code-review") is not None
        assert registry.get("debug") is not None

    def test_user_skill_overrides_builtin(self, tmp_path):
        """测试用户 Skill 同名覆盖内置 Skill"""
        builtin_dir = tmp_path / "builtin"
        builtin_dir.mkdir()
        (builtin_dir / "review.md").write_text(
            "---\nname: review\ndescription: 内置审查\ntrigger: /review\n---\n内置流程\n",
            encoding="utf-8",
        )
        user_dir = tmp_path / "user"
        user_dir.mkdir()
        (user_dir / "review.md").write_text(
            "---\nname: review\ndescription: 用户审查\ntrigger: /review\n---\n用户流程\n",
            encoding="utf-8",
        )
        registry = SkillRegistry()
        registry.load_builtin(str(builtin_dir))
        registry.load_user(str(user_dir))
        skill = registry.get("review")
        assert skill.source == "user"
        assert "用户流程" in skill.prompt

    def test_invalid_frontmatter_skipped(self, tmp_path):
        """测试 frontmatter 解析失败时跳过文件"""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        (skill_dir / "bad.md").write_text(
            "---\ninvalid yaml [\n---\n内容\n",
            encoding="utf-8",
        )
        (skill_dir / "good.md").write_text(
            "---\nname: good\ndescription: 好的\ntrigger: /good\n---\n好的流程\n",
            encoding="utf-8",
        )
        registry = SkillRegistry()
        registry.load_builtin(str(skill_dir))
        assert registry.get("bad") is None
        assert registry.get("good") is not None

    def test_missing_required_field_skipped(self, tmp_path):
        """测试缺少必填字段时跳过文件"""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        (skill_dir / "no-trigger.md").write_text(
            "---\nname: no-trigger\ndescription: 缺少 trigger\n---\n内容\n",
            encoding="utf-8",
        )
        registry = SkillRegistry()
        registry.load_builtin(str(skill_dir))
        assert registry.get("no-trigger") is None

    def test_non_md_files_ignored(self, tmp_path):
        """测试非 .md 文件被忽略"""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        (skill_dir / "notes.txt").write_text("不是 Skill 文件", encoding="utf-8")
        (skill_dir / "review.md").write_text(
            "---\nname: review\ndescription: 审查\ntrigger: /review\n---\n流程\n",
            encoding="utf-8",
        )
        registry = SkillRegistry()
        registry.load_builtin(str(skill_dir))
        assert len(registry.list_all()) == 1


class TestSkillRegistryQuery:
    def test_get_by_trigger(self, tmp_path):
        """测试按 trigger 查找 Skill"""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        (skill_dir / "code-review.md").write_text(
            "---\nname: code-review\ndescription: 审查\ntrigger: /review\n---\n流程\n",
            encoding="utf-8",
        )
        registry = SkillRegistry()
        registry.load_builtin(str(skill_dir))
        skill = registry.get_by_trigger("/review")
        assert skill is not None
        assert skill.name == "code-review"
        assert registry.get_by_trigger("/nonexistent") is None

    def test_triggers_list(self, tmp_path):
        """测试返回所有 trigger 列表"""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        (skill_dir / "code-review.md").write_text(
            "---\nname: code-review\ndescription: 审查\ntrigger: /review\n---\n流程\n",
            encoding="utf-8",
        )
        (skill_dir / "debug.md").write_text(
            "---\nname: debug\ndescription: 调试\ntrigger: /debug\n---\n流程\n",
            encoding="utf-8",
        )
        registry = SkillRegistry()
        registry.load_builtin(str(skill_dir))
        triggers = registry.triggers()
        assert "/review" in triggers
        assert "/debug" in triggers

    def test_list_all(self, tmp_path):
        """测试列出所有 Skill"""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        (skill_dir / "code-review.md").write_text(
            "---\nname: code-review\ndescription: 审查\ntrigger: /review\n---\n流程\n",
            encoding="utf-8",
        )
        registry = SkillRegistry()
        registry.load_builtin(str(skill_dir))
        all_skills = registry.list_all()
        assert len(all_skills) == 1
        assert all_skills[0].name == "code-review"

    def test_empty_directory(self, tmp_path):
        """测试空目录不报错"""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        registry = SkillRegistry()
        registry.load_builtin(str(skill_dir))
        assert len(registry.list_all()) == 0

    def test_nonexistent_directory(self, tmp_path):
        """测试不存在的目录不报错"""
        registry = SkillRegistry()
        registry.load_builtin(str(tmp_path / "nonexistent"))
        assert len(registry.list_all()) == 0


class TestContextActiveSkill:
    def test_set_active_skill(self):
        """测试设置 active_skill"""
        from agent.context import Context
        from agent.skills import Skill
        ctx = Context(system_prompt="你是 Bitz-Cat")
        skill = Skill(name="review", description="审查", trigger="/review", prompt="按步骤审查", source="builtin")
        ctx.set_active_skill(skill)
        assert ctx.active_skill is not None
        assert ctx.active_skill.name == "review"

    def test_clear_active_skill(self):
        """测试清除 active_skill"""
        from agent.context import Context
        from agent.skills import Skill
        ctx = Context(system_prompt="你是 Bitz-Cat")
        skill = Skill(name="review", description="审查", trigger="/review", prompt="按步骤审查", source="builtin")
        ctx.set_active_skill(skill)
        ctx.clear_active_skill()
        assert ctx.active_skill is None

    def test_get_messages_with_active_skill(self):
        """测试 get_messages 动态拼接 Skill prompt"""
        from agent.context import Context
        from agent.skills import Skill
        ctx = Context(system_prompt="你是 Bitz-Cat")
        ctx.add_user("你好")
        skill = Skill(name="review", description="审查", trigger="/review", prompt="按步骤审查代码", source="builtin")
        ctx.set_active_skill(skill)
        msgs = ctx.get_messages()
        assert msgs[0]["role"] == "system"
        assert "当前 Skill: review" in msgs[0]["content"]
        assert "按步骤审查代码" in msgs[0]["content"]

    def test_get_messages_without_active_skill(self):
        """测试没有 active_skill 时不拼接"""
        from agent.context import Context
        ctx = Context(system_prompt="你是 Bitz-Cat")
        ctx.add_user("你好")
        msgs = ctx.get_messages()
        assert msgs[0]["role"] == "system"
        assert "当前 Skill" not in msgs[0]["content"]

    def test_switch_skill_replaces(self):
        """测试切换 Skill 时替换而非累积"""
        from agent.context import Context
        from agent.skills import Skill
        ctx = Context(system_prompt="你是 Bitz-Cat")
        skill1 = Skill(name="review", description="审查", trigger="/review", prompt="审查流程", source="builtin")
        skill2 = Skill(name="debug", description="调试", trigger="/debug", prompt="调试流程", source="builtin")
        ctx.set_active_skill(skill1)
        ctx.set_active_skill(skill2)
        msgs = ctx.get_messages()
        assert "当前 Skill: debug" in msgs[0]["content"]
        assert "调试流程" in msgs[0]["content"]
        assert "审查流程" not in msgs[0]["content"]

    def test_clear_skill_removes_from_messages(self):
        """测试清除 Skill 后 get_messages 不再拼接"""
        from agent.context import Context
        from agent.skills import Skill
        ctx = Context(system_prompt="你是 Bitz-Cat")
        skill = Skill(name="review", description="审查", trigger="/review", prompt="审查流程", source="builtin")
        ctx.set_active_skill(skill)
        ctx.clear_active_skill()
        msgs = ctx.get_messages()
        assert "当前 Skill" not in msgs[0]["content"]

    def test_skill_does_not_modify_original_messages(self):
        """测试 Skill 拼接不修改原始 messages 列表"""
        from agent.context import Context
        from agent.skills import Skill
        ctx = Context(system_prompt="你是 Bitz-Cat")
        ctx.add_user("你好")  # 添加一条消息，确保 messages 非空
        skill = Skill(name="review", description="审查", trigger="/review", prompt="审查流程", source="builtin")
        ctx.set_active_skill(skill)
        msgs = ctx.get_messages()
        assert "当前 Skill" in msgs[0]["content"]
        # messages[0] 是用户消息，不是 system 消息
        # 检查 system 消息（msgs[0]）包含 Skill，但原始 messages 不受影响
        assert "当前 Skill" not in ctx.messages[0]["content"]


class TestCommandPopupWithSkills:
    def test_build_commands_includes_skills(self):
        """测试 build_commands 包含 Skill trigger"""
        from tui.widgets.command_popup import build_commands, BASE_COMMANDS
        registry = SkillRegistry()
        registry.skills["review"] = Skill(name="review", description="审查代码", trigger="/review", prompt="流程", source="builtin")
        commands = build_commands(registry)
        assert len([c for c in commands if c[0] == "/help"]) == 1
        assert len([c for c in commands if c[0] == "/review"]) == 1

    def test_build_commands_no_registry(self):
        """测试没有 registry 时只有基础命令"""
        from tui.widgets.command_popup import build_commands, BASE_COMMANDS
        commands = build_commands(None)
        assert len(commands) == len(BASE_COMMANDS)