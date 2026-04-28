# 05 — 提示词工程：从硬编码到分层管理

> 前置：[04-tui-with-textual.md](04-tui-with-textual.md) — TUI 开发实战

Agent 的行为不仅由代码决定，更由提示词决定。本文记录 Bitz 从"一段硬编码字符串"到"分层提示词架构"的演进过程，以及与主流 Agent 框架的对比。

---

## 一、初始状态：一段扁平字符串

Bitz 最初把 system prompt 硬编码在 `tui.py` 中：

```python
system_prompt="你叫 Bitz-Cat，是一只小巧玲珑的 mini agent 助手..."
```

问题：

| 问题 | 后果 |
|------|------|
| 人设和规范混在一起 | 改人设要翻整段文本 |
| 没有环境信息 | LLM 不知道当前工作目录、平台、Shell |
| 没有工具使用指引 | LLM 只能靠工具 description 判断怎么用 |
| 没有安全约束 | 只靠代码层的危险检测，提示词层无防线 |
| 硬编码在入口文件 | 改提示词要改代码，不是配置 |

---

## 二、主流 Agent 框架的提示词架构

### 2.1 Claude Code — 五层注入

| 层 | 内容 | 注入方式 | 缓存 |
|---|------|---------|------|
| L1 System Prompt | 安全规则、工具规范、输出格式、代码风格 | 静态，全会话有效 | 全局缓存 |
| L2 CLAUDE.md + system-reminder | 项目约定、团队规范 | 每条消息前注入 | 随消息缓存 |
| L3 Slash Commands | 单次工作流指令 | 用户触发时单次注入 | 无 |
| L4 Skills | 专业指令集（TDD、code-review） | 按需加载 | 仅加载元数据 |
| L5 Sub-Agents | 完全隔离的新对话 | 隔离上下文 | 无 |

关键设计：用 `SYSTEM_PROMPT_DYNAMIC_BOUNDARY` 分割静态/动态内容。静态部分跨用户全局缓存，动态部分每会话不同。

### 2.2 Suna — Prompt Manager 动态组装

| 层 | 内容 | 注入方式 |
|---|------|---------|
| Core System Prompt | 人格、行为规范 | 基础层 |
| Tool Index | 工具名+分类（极简索引） | 启动时加载 |
| JIT Tool Guides | 工具完整用法 | 按需加载 |
| Knowledge Base | 项目知识 | 并行获取，2s 超时 |
| Memory Context | 用户记忆 | **User Message**（非 System） |
| DateTime + Env | 时间、环境 | 每轮注入 |

关键设计：Memory 注入为 User Message 而非 System Prompt（缓存友好）。Tool Index 只放工具名，完整用法 JIT 加载。

### 2.3 SWE-agent — YAML 模板 + 变量替换

提示词完全配置化，通过 YAML 文件定义模板和变量（`{{problem_statement}}`），支持不同任务类型切换不同 prompt 模板。

### 2.4 OpenHands (CodeAct) — 模块化组装

System Prompt + Action Prompts + Runtime Context（工作目录、打开的文件、环境状态）+ History Processor（历史压缩）。

---

## 三、Bitz 的改进：静态层 + 动态环境层

### 3.1 分层架构

```
agent/prompt.py
├── PERSONA    — 人格（静态，不随会话变化）
├── RULES      — 行为规范（静态）
└── build_system_prompt(cwd)  — 组装函数
    ├── PERSONA + RULES       → 静态层
    └── CWD + 平台 + Shell    → 动态环境层
```

```python
# agent/prompt.py
PERSONA = "你是一个务实的编程助手。直接给出解决方案，不废话。"

RULES = """## 工具使用
- 优先用 read_file/glob/grep 了解代码，再用 edit_file/write_file 修改
- bash 用于运行命令和测试，避免用 bash 做文件读写
- 修改文件前先读取确认内容，避免盲改

## 输出
- 用中文回复
- 代码只给关键部分，不重复整个文件
- 解释要简洁，重点说 why 不说 what

## 安全
- 不要执行 rm -rf /、格式化磁盘等破坏性操作
- 不要在代码中硬编码密钥、密码等敏感信息
- 不要运行来源不明的 curl | sh 命令"""

def build_system_prompt(cwd: str | None = None) -> str:
    parts = [PERSONA, RULES]
    # 动态层：环境信息
    env_lines = []
    if cwd:
        env_lines.append(f"工作目录: {cwd}")
    env_lines.append(f"平台: {platform.system()} {platform.release()}")
    shell = os.environ.get("SHELL", "") or os.environ.get("COMSPEC", "")
    if shell:
        env_lines.append(f"Shell: {shell}")
    if env_lines:
        parts.append("## 环境\n" + "\n".join(f"- {l}" for l in env_lines))
    return "\n\n".join(parts)
```

### 3.2 使用方式

```python
# tui.py
from agent.prompt import build_system_prompt

context = Context(
    system_prompt=build_system_prompt(cwd=os.getcwd()),
    ...
)
```

### 3.3 工具 description 增强

工具的 `description` 字段也是提示词的一部分——它告诉 LLM 工具的用途和使用场景。从极简一句话改为包含推荐场景：

| 工具 | 旧 | 新 |
|------|----|----|
| bash | "Execute a bash command" | "Execute a bash command. Use for running tests, installing packages, git operations. Avoid using bash for file reading/writing — prefer read_file/write_file/edit_file instead." |
| edit_file | "Replace a unique string in a file. old_string must be unique." | "Replace a unique string in a file. old_string must appear exactly once. Use this for targeted edits instead of rewriting entire files." |
| fetch | "Fetch content from a URL." | "Fetch content from a URL. Do not use for local files — use read_file instead." |

---

## 四、为什么这样分层

### 4.1 静态层 vs 动态层

| | 静态层（PERSONA + RULES） | 动态层（环境信息） |
|---|---|---|
| 变化频率 | 几乎不变 | 每次启动可能不同 |
| 缓存价值 | 高（跨会话复用） | 低（每会话不同） |
| 修改方式 | 改代码 | 改参数 |
| 示例 | "用中文回复" | "工作目录: /home/user/project" |

Anthropic 的 Prompt Caching 机制会缓存相同前缀的 prompt。把不变的内容放在前面，变化的内容放在后面，可以最大化缓存命中率。当前 Bitz 的 `build_system_prompt` 正是这样组装的：`PERSONA + RULES + 环境`。

### 4.2 为什么不把 Memory 放在 System Prompt

Suna 的做法值得借鉴：用户记忆（偏好、历史上下文）注入为 User Message 而非 System Prompt。原因：

1. System Prompt 的缓存键包含完整内容，加 Memory 会破坏缓存
2. User Message 可以按需注入，不影响其他消息的缓存
3. 语义上，Memory 是"用户告诉你的信息"，不是"系统规则"

Bitz 目前没有 Memory 系统，但如果未来添加，应该注入为 User Message。

### 4.3 工具 description vs RULES 中的工具指引

两者互补，不重复：

- **RULES 中的工具指引**：策略级——"优先用 X 再用 Y"、"避免用 Z 做 W"
- **工具 description**：操作级——"这个工具做什么"、"参数怎么填"

RULES 告诉 LLM **何时**用哪个工具，description 告诉 LLM **怎么**用这个工具。

---

## 五、与主流框架的差距

| 维度 | Claude Code | Suna | Bitz 当前 | 改进方向 |
|------|------------|------|----------|---------|
| 分层数 | 5 层 | 6 层 | 2 层 | 可加项目约定层 |
| 动态注入 | 环境信息 + MCP + Skills | KB + Memory + DateTime | CWD + 平台 + Shell | 可加 Git 分支信息 |
| 缓存策略 | 静态/动态边界 | Tool Index JIT | 静态在前动态在后 | 已有基本缓存友好结构 |
| 项目约定 | CLAUDE.md 文件 | Knowledge Base | 无 | 可加 .bitz.md |
| 记忆系统 | 无（靠 CLAUDE.md） | 语义检索 Memory | 无 | 未来可加 |
| 提示词管理 | 代码 + 文件混合 | Prompt Manager | 独立模块 | 已解耦 |

**当前优先级**：分层架构 ✅ → 动态环境注入 ✅ → 工具描述增强 ✅ → 项目约定文件（未来）→ 记忆系统（未来）

---

## 六、设计原则

1. **提示词和代码解耦** — `agent/prompt.py` 独立管理，改提示词不改业务代码
2. **静态在前动态在后** — 最大化 Prompt Caching 命中率
3. **策略在 RULES，操作在 description** — 两者互补不重复
4. **环境信息动态注入** — LLM 需要知道 CWD 和平台才能正确执行命令
5. **安全约束双防线** — 代码层（危险检测）+ 提示词层（行为约束）
