# Bitz/tests/test_skills.py
import pytest
import tempfile
import os
from agent.skills import Skill, SkillRegistry, _parse_skill_file


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


class TestDirectoryTypeSkill:
    def test_load_directory_skill(self, tmp_path):
        """测试子目录含 SKILL.md 时正确加载"""
        skill_dir = tmp_path / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: 目录型Skill\ntrigger: /my-skill\n---\n流程内容\n",
            encoding="utf-8",
        )
        registry = SkillRegistry()
        registry.load_builtin(str(tmp_path / "skills"))
        skill = registry.get("my-skill")
        assert skill is not None
        assert skill.name == "my-skill"
        assert skill.skill_dir is not None
        assert "流程内容" in skill.prompt

    def test_directory_skill_with_references(self, tmp_path):
        """测试目录型 Skill 的 skill_dir 指向正确目录"""
        skill_dir = tmp_path / "skills" / "admin-review"
        skill_dir.mkdir(parents=True)
        refs_dir = skill_dir / "references"
        refs_dir.mkdir()
        (refs_dir / "execution-order.yaml").write_text("test: true", encoding="utf-8")
        (skill_dir / "SKILL.md").write_text(
            "---\nname: admin-review\ndescription: 审查\ntrigger: /admin-review\n---\n审查流程\n",
            encoding="utf-8",
        )
        registry = SkillRegistry()
        registry.load_builtin(str(tmp_path / "skills"))
        skill = registry.get("admin-review")
        assert skill is not None
        assert skill.skill_dir is not None
        import os
        ref_path = os.path.join(skill.skill_dir, "references", "execution-order.yaml")
        assert os.path.isfile(ref_path)

    def test_mixed_single_and_directory_skills(self, tmp_path):
        """测试同一目录下单文件和目录型 Skill 共存"""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        # 单文件 Skill
        (skills_dir / "debug.md").write_text(
            "---\nname: debug\ndescription: 调试\ntrigger: /debug\n---\n调试流程\n",
            encoding="utf-8",
        )
        # 目录型 Skill
        dir_skill = skills_dir / "my-skill"
        dir_skill.mkdir()
        (dir_skill / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: 目录型\ntrigger: /my-skill\n---\n流程\n",
            encoding="utf-8",
        )
        registry = SkillRegistry()
        registry.load_builtin(str(skills_dir))
        debug = registry.get("debug")
        my_skill = registry.get("my-skill")
        assert debug is not None
        assert debug.skill_dir is None
        assert my_skill is not None
        assert my_skill.skill_dir is not None

    def test_directory_without_skill_md_ignored(self, tmp_path):
        """测试子目录不含 SKILL.md 时忽略"""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        sub = skills_dir / "not-a-skill"
        sub.mkdir()
        (sub / "notes.txt").write_text("不是 Skill", encoding="utf-8")
        registry = SkillRegistry()
        registry.load_builtin(str(skills_dir))
        assert len(registry.list_all()) == 0

    def test_skill_dir_is_absolute_path(self, tmp_path):
        """测试 skill_dir 始终为绝对路径"""
        skill_dir = tmp_path / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: 测试\ntrigger: /my-skill\n---\n流程\n",
            encoding="utf-8",
        )
        registry = SkillRegistry()
        registry.load_builtin(str(tmp_path / "skills"))
        skill = registry.get("my-skill")
        assert skill is not None
        import os
        assert os.path.isabs(skill.skill_dir)


class TestContextDirectorySkill:
    def test_get_messages_with_directory_skill_injects_path(self):
        """测试目录型 Skill 激活时 system 消息包含 L1 摘要（含资源目录路径）"""
        from agent.context import Context
        ctx = Context(system_prompt="你是 Bitz-Cat")
        ctx.add_user("你好")
        skill = Skill(
            name="admin-review",
            description="审查",
            trigger="/admin-review",
            prompt="审查流程",
            source="builtin",
            skill_dir="/abs/path/to/skill",
        )
        ctx.set_active_skill(skill)
        msgs = ctx.get_messages()
        assert msgs[0]["role"] == "system"
        # 分层注入后，目录型 skill 仅注入 summary
        assert "[Skill: admin-review]" in msgs[0]["content"]
        assert "/abs/path/to/skill" in msgs[0]["content"]
        assert "read_file" in msgs[0]["content"]

    def test_get_messages_with_single_file_skill_no_path_injection(self):
        """测试单文件 Skill 不注入资源目录路径"""
        from agent.context import Context
        ctx = Context(system_prompt="你是 Bitz-Cat")
        ctx.add_user("你好")
        skill = Skill(
            name="review",
            description="审查",
            trigger="/review",
            prompt="审查流程",
            source="builtin",
        )
        ctx.set_active_skill(skill)
        msgs = ctx.get_messages()
        assert msgs[0]["role"] == "system"
        assert "当前 Skill: review" in msgs[0]["content"]
        assert "Skill 资源目录" not in msgs[0]["content"]


class TestAutoTrigger:
    def test_auto_trigger_default_true(self):
        """不传 auto_trigger 时默认 True"""
        skill = Skill(name="test", description="测试", trigger="/test", prompt="流程", source="builtin")
        assert skill.auto_trigger is True

    def test_auto_trigger_explicit_false(self):
        """显式设置 auto_trigger=False"""
        skill = Skill(name="test", description="测试", trigger="/test", prompt="流程", source="builtin", auto_trigger=False)
        assert skill.auto_trigger is False

    def test_parse_auto_trigger_from_frontmatter(self, tmp_path):
        """从 frontmatter 解析 auto_trigger: false"""
        f = tmp_path / "skill.md"
        f.write_text(
            "---\nname: heavy\ndescription: 重型\ntrigger: /heavy\nauto_trigger: false\n---\n流程\n",
            encoding="utf-8",
        )
        skill = _parse_skill_file(str(f), "builtin")
        assert skill is not None
        assert skill.auto_trigger is False

    def test_parse_auto_trigger_missing_defaults_true(self, tmp_path):
        """frontmatter 缺少 auto_trigger 时默认 True"""
        f = tmp_path / "skill.md"
        f.write_text(
            "---\nname: light\ndescription: 轻型\ntrigger: /light\n---\n流程\n",
            encoding="utf-8",
        )
        skill = _parse_skill_file(str(f), "builtin")
        assert skill is not None
        assert skill.auto_trigger is True


class TestSkillSummary:
    def test_summary_single_file_skill(self):
        """单文件 skill 的 summary 包含完整 prompt"""
        skill = Skill(name="debug", description="调试排错", trigger="/debug", prompt="调试流程", source="builtin")
        s = skill.summary()
        assert "[Skill: debug]" in s
        assert "调试排错" in s
        assert "调试流程" in s

    def test_summary_directory_skill(self):
        """目录型 skill 的 summary 不包含完整 prompt，包含 skill_dir 提示"""
        skill = Skill(
            name="admin-review", description="行政案件审查", trigger="/admin-review",
            prompt="很长的审查流程...", source="builtin", skill_dir="/path/to/skill",
        )
        s = skill.summary()
        assert "[Skill: admin-review]" in s
        assert "行政案件审查" in s
        assert "/path/to/skill" in s
        assert "read_file" in s
        assert "很长的审查流程" not in s

    def test_summary_description_truncation(self):
        """description 超过 max_description_chars 时截断"""
        long_desc = "这是一个非常非常长的描述" * 50
        skill = Skill(name="test", description=long_desc, trigger="/test", prompt="流程", source="builtin")
        s = skill.summary(max_description_chars=100)
        assert len(s) < len(long_desc)
        assert "…" in s

    def test_registry_max_description_chars(self):
        """SkillRegistry 的 max_description_chars 配置传递到 summary"""
        registry = SkillRegistry(max_description_chars=50)
        assert registry.max_description_chars == 50

    def test_registry_default_max_description_chars(self):
        """SkillRegistry 默认 max_description_chars=200"""
        registry = SkillRegistry()
        assert registry.max_description_chars == 200


class TestLayeredInjection:
    def test_directory_skill_injects_summary_only(self):
        """目录型 skill 激活时 system 消息仅包含 L1 摘要，不包含完整 prompt"""
        from agent.context import Context
        ctx = Context(system_prompt="你是 Bitz-Cat")
        ctx.add_user("你好")
        skill = Skill(
            name="admin-review", description="行政案件审查", trigger="/admin-review",
            prompt="这是很长的审查流程指令，包含4个阶段...", source="builtin",
            skill_dir="/path/to/admin-review",
        )
        ctx.set_active_skill(skill)
        msgs = ctx.get_messages()
        system_content = msgs[0]["content"]
        assert "[Skill: admin-review]" in system_content
        assert "/path/to/admin-review" in system_content
        assert "read_file" in system_content
        assert "这是很长的审查流程指令" not in system_content

    def test_single_file_skill_injects_full_prompt(self):
        """单文件 skill 激活时 system 消息包含完整 prompt"""
        from agent.context import Context
        ctx = Context(system_prompt="你是 Bitz-Cat")
        ctx.add_user("你好")
        skill = Skill(
            name="debug", description="调试排错", trigger="/debug",
            prompt="调试流程指令", source="builtin",
        )
        ctx.set_active_skill(skill)
        msgs = ctx.get_messages()
        system_content = msgs[0]["content"]
        assert "当前 Skill: debug" in system_content
        assert "调试流程指令" in system_content

    def test_no_active_skill_no_injection(self):
        """无活跃 skill 时不注入任何内容"""
        from agent.context import Context
        ctx = Context(system_prompt="你是 Bitz-Cat")
        ctx.add_user("你好")
        msgs = ctx.get_messages()
        assert msgs[0]["content"] == "你是 Bitz-Cat"