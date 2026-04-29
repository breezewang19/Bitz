# agent/prompt.py
"""提示词管理 — 静态层 + 动态环境层"""
import os
import platform

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


def build_system_prompt(cwd: str | None = None, skill_registry=None) -> str:
    """组装完整 system prompt：静态层 + 动态环境层"""
    parts = [PERSONA, RULES]

    # ── 动态层：环境信息（每会话可能不同） ──
    env_lines = []
    if cwd:
        env_lines.append(f"工作目录: {cwd}")
    env_lines.append(f"平台: {platform.system()} {platform.release()}")
    shell = os.environ.get("SHELL", "") or os.environ.get("COMSPEC", "")
    if shell:
        env_lines.append(f"Shell: {shell}")

    if env_lines:
        parts.append("## 环境\n" + "\n".join(f"- {l}" for l in env_lines))

    # 注入 auto_trigger=True 的 skill 摘要区
    if skill_registry is not None:
        skills_summary = skill_registry.build_skills_summary()
        if skills_summary:
            parts.append(
                f"## 可用 Skill\n以下 Skill 可根据用户意图自动激活，或通过斜杠命令手动触发：\n\n{skills_summary}\n\n当用户意图匹配某个 Skill 时，在回复开头输出该 Skill 的 trigger（如 /debug），即可自动激活。"
            )

    return "\n\n".join(parts)
