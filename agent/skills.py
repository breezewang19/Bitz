# Bitz/agent/skills.py
from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace

import yaml


@dataclass
class Skill:
    name: str
    description: str
    trigger: str
    prompt: str
    source: str  # "builtin" 或 "user"
    skill_dir: str | None = None  # 目录型 Skill 的根路径
    auto_trigger: bool = True  # 是否自动触发（缺省为 True）

    def summary(self, max_description_chars: int = 200) -> str:
        """生成 L1 摘要文本。目录型 skill 仅含摘要+路径提示，单文件 skill 含完整 prompt。"""
        desc = self.description
        if len(desc) > max_description_chars:
            desc = desc[:max_description_chars - 1] + "…"
        if self.skill_dir:
            return (
                f"[Skill: {self.name}] {desc}\n"
                f"资源目录: {self.skill_dir}\n"
                f"使用 read_file 读取 {self.skill_dir}/SKILL.md 获取完整指令。"
            )
        return f"[Skill: {self.name}] {desc}\n{self.prompt}"


_REQUIRED_FIELDS = {"name", "description", "trigger"}

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_skill_file(filepath: str, source: str) -> Skill | None:
    """解析单个 Skill .md 文件，失败返回 None。"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return None

    match = _FRONTMATTER_RE.match(content)
    if not match:
        return None

    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None

    if not isinstance(meta, dict):
        return None

    # 检查必填字段
    if not _REQUIRED_FIELDS.issubset(meta.keys()):
        return None

    prompt = content[match.end():].strip()

    # 解析 auto_trigger，支持多种格式
    auto_trigger_raw = meta.get("auto_trigger", True)
    auto_trigger: bool = True
    if isinstance(auto_trigger_raw, bool):
        auto_trigger = auto_trigger_raw
    elif isinstance(auto_trigger_raw, str):
        auto_trigger = auto_trigger_raw.lower() in ("true", "yes", "1")
    elif isinstance(auto_trigger_raw, (int, float)):
        auto_trigger = bool(auto_trigger_raw)

    return Skill(
        name=meta["name"],
        description=meta["description"],
        trigger=meta["trigger"],
        prompt=prompt,
        source=source,
        auto_trigger=auto_trigger,
    )


class SkillRegistry:
    def __init__(self, max_description_chars: int = 200, max_skills_chars: int = 2000) -> None:
        self.skills: dict[str, Skill] = {}
        self.max_description_chars = max_description_chars
        self.max_skills_chars = max_skills_chars

    def load_builtin(self, path: str) -> None:
        """从目录加载内置 Skill。"""
        self._load_from_dir(path, source="builtin")

    def load_user(self, path: str) -> None:
        """从目录加载用户 Skill（同名覆盖内置）。"""
        self._load_from_dir(path, source="user")

    def list_all(self) -> list[Skill]:
        return list(self.skills.values())

    def get(self, name: str) -> Skill | None:
        return self.skills.get(name)

    def get_by_trigger(self, trigger: str) -> Skill | None:
        for skill in self.skills.values():
            if skill.trigger == trigger:
                return skill
        return None

    def triggers(self) -> list[str]:
        return [s.trigger for s in self.skills.values()]

    def build_skills_summary(self) -> str:
        """生成所有 auto_trigger=True 的 skill 摘要，总长不超过 max_skills_chars。"""
        parts = []
        total = 0
        for skill in self.list_all():
            if not skill.auto_trigger:
                continue
            s = skill.summary(max_description_chars=self.max_description_chars)
            if total + len(s) > self.max_skills_chars:
                break
            parts.append(s)
            total += len(s)
        return "\n\n".join(parts)

    def _load_from_dir(self, path: str, source: str) -> None:
        """从目录扫描 .md 文件和 SKILL.md 目录型 Skill 并加载。"""
        if not os.path.isdir(path):
            return
        for filename in sorted(os.listdir(path)):
            filepath = os.path.join(path, filename)

            # 目录型 Skill：子目录包含 SKILL.md
            if os.path.isdir(filepath):
                skill_md = os.path.join(filepath, "SKILL.md")
                if os.path.isfile(skill_md):
                    skill = _parse_skill_file(skill_md, source)
                    if skill is not None:
                        skill = replace(skill, skill_dir=os.path.abspath(filepath))
                        self.skills[skill.name] = skill
                continue

            # 单文件 Skill：.md 文件
            if not filename.endswith(".md"):
                continue
            skill = _parse_skill_file(filepath, source)
            if skill is not None:
                self.skills[skill.name] = skill