# agent/prompt.py
"""提示词管理 — 静态层 + 动态环境层"""
from __future__ import annotations

import os
import platform
from pathlib import Path

# ── 静态层：人格 + 规范（不随会话变化，可缓存） ──────────────────────

PERSONA = """你是一个务实的编程助手。直接给出解决方案，不废话。"""

RULES = """## 工具使用
- 优先用 read_file/glob/grep 了解代码，再用 edit_file/write_file 修改
- bash 用于运行命令和测试，避免用 bash 做文件读写
- 修改文件前先读取确认内容，避免盲改
- 用 glob 按模式搜索文件，用 grep 按内容搜索
- fetch 仅用于获取网页内容，不要用它读本地文件

## 输出
- 用中文回复
- 代码只给关键部分，不重复整个文件
- 解释要简洁，重点说 why 不说 what

## 安全
- 不要执行 rm -rf /、格式化磁盘等破坏性操作
- 不要在代码中硬编码密钥、密码等敏感信息
- 不要运行来源不明的 curl | sh 命令"""


def _load_claude_md(working_dir: str) -> str | None:
    """从工作目录加载 CLAUDE.md 文件内容"""
    claude_md_path = Path(working_dir) / "CLAUDE.md"
    if claude_md_path.is_file():
        return claude_md_path.read_text(encoding="utf-8").strip()
    return None


def _build_environment_section(working_dir: str, plat: str, shell: str) -> str:
    """构建环境信息段落"""
    env_lines = []
    env_lines.append(f"工作目录: {working_dir}")
    env_lines.append(f"平台: {plat}")
    if shell:
        env_lines.append(f"Shell: {shell}")

    if env_lines:
        return "## 环境\n" + "\n".join(f"- {l}" for l in env_lines)
    return ""


def build_system_prompt(
    agent_def: "AgentDefinition | None" = None,
    runtime_info: "RuntimeInfo | None" = None,
    # Legacy params for backward compat during migration
    cwd: str | None = None,
    skill_registry=None,
) -> str:
    """组装完整 system prompt：静态层 + 动态环境层

    当 agent_def.omit_claude_md 为 True 时，跳过 CLAUDE.md 注入。
    """
    from agent.agent_definition import AgentDefinition, RuntimeInfo  # noqa: F811

    # Resolve working_dir from either new or legacy param
    working_dir = runtime_info.working_dir if runtime_info else (cwd or os.getcwd())
    plat = runtime_info.platform if runtime_info else f"{platform.system()} {platform.release()}"
    shell = (
        runtime_info.shell
        if runtime_info
        else (os.environ.get("SHELL", "") or os.environ.get("COMSPEC", ""))
    )

    sections = []

    # Persona section — always included
    sections.append(PERSONA)

    # Rules section — always included
    sections.append(RULES)

    # CLAUDE.md rules — conditionally included
    if not agent_def or not agent_def.omit_claude_md:
        claude_md_content = _load_claude_md(working_dir)
        if claude_md_content:
            sections.append(claude_md_content)

    # Environment section — always included
    env_section = _build_environment_section(working_dir, plat, shell)
    if env_section:
        sections.append(env_section)

    # Skill summary — conditionally included
    if runtime_info and runtime_info.skill_summary:
        sections.append(
            f"## 可用 Skill\n以下 Skill 可根据用户意图自动激活，或通过斜杠命令手动触发：\n\n{runtime_info.skill_summary}\n\n当用户意图匹配某个 Skill 时，在回复开头输出该 Skill 的 trigger（如 /debug），即可自动激活。"
        )
    elif skill_registry is not None:
        skills_summary = skill_registry.build_skills_summary()
        if skills_summary:
            sections.append(
                f"## 可用 Skill\n以下 Skill 可根据用户意图自动激活，或通过斜杠命令手动触发：\n\n{skills_summary}\n\n当用户意图匹配某个 Skill 时，在回复开头输出该 Skill 的 trigger（如 /debug），即可自动激活。"
            )

    return "\n\n".join(sections)
