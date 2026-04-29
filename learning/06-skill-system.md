# 06 — Skill 机制：Prompt 驱动的行为编排

> **核心问题**：Tool 是原子操作（读文件、执行命令），但用户需要的是**行为编排**——"帮我审查这段代码"不是单个工具调用，而是一系列工具按特定流程组合使用。Skill 就是这层编排。

---

## 1. Skill ≠ Tool：本质区别

| 维度 | Tool | Skill |
|---|---|---|
| 粒度 | 原子操作（read_file, grep） | 行为编排（审查代码、调试排错） |
| 定义方式 | Python 函数 + @tool 装饰器 | Markdown 文件 + YAML frontmatter |
| LLM 感知 | LLM 看到工具定义，自主决定调用 | LLM 看到 prompt 指令，按指令行动 |
| 可组合性 | 不可组合，每次调用一个 | 组合多个 Tool，定义执行流程 |
| 用户触发 | Agent 自主调用 | 用户手动 `/skill-name` 激活 |

**关键洞察**：Skill 不给 Agent 新能力，而是告诉 Agent **如何使用已有能力**。

---

## 2. 设计决策：为什么选 Prompt-driven？

主流 Agent 框架有两种 Skill 范式：

### Prompt-driven（Claude Code、Semantic Kernel）
```
Skill = 一段 prompt 指令
激活 → 注入到 system_prompt → Agent 按指令行动
```
- 优点：零代码门槛，Markdown 即可定义；与 ReAct 循环天然兼容
- 缺点：Agent 可能不严格遵守指令

### Code-driven（OpenAI Agents、MetaGPT）
```
Skill = 一个 Python 类
激活 → 创建独立执行循环 → 有自己的 run() 方法
```
- 优点：行为可控，可包含自定义逻辑
- 缺点：代码门槛高，需要理解框架 API

**Bitz 选择 Prompt-driven**：教学项目，门槛最低，概念最清晰。

---

## 3. Skill 文件格式

```markdown
---
name: code-review
description: 审查代码质量，检查常见问题
trigger: /review
---

你是代码审查专家。请按以下步骤审查代码：

1. 使用 glob 找到目标文件
2. 使用 read_file 阅读代码
3. 使用 grep 搜索常见反模式
4. 输出审查报告

重点关注：安全漏洞、性能问题、代码风格
```

**三段式结构**：
1. **YAML frontmatter**（`---` 包裹）：元信息，机器解析
2. **空行分隔**：frontmatter 与 body 之间
3. **Markdown body**：行为指令，Agent 读取后执行

### Frontmatter 字段

| 字段 | 必填 | 说明 | 示例 |
|---|---|---|---|
| `name` | 是 | Skill 标识 | `code-review` |
| `description` | 是 | 一句话描述 | `审查代码质量` |
| `trigger` | 是 | 斜杠命令 | `/review` |

### 为什么用 Markdown 而不是 YAML/Python？

- **Markdown 写 prompt 最自然**：prompt 本身就是自然语言，Markdown 的标题、列表、代码块天然适合结构化指令
- **YAML 只适合结构化数据**：把长段 prompt 塞进 YAML 字符串需要大量转义，可读性差
- **Python 门槛太高**：教学项目不应该要求用户写代码来定义行为

---

## 4. Frontmatter 解析

```python
# agent/skills.py 核心解析逻辑

import re
import yaml

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

def _parse_skill_file(filepath: str, source: str) -> Skill | None:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    match = _FRONTMATTER_RE.match(content)
    if not match:
        return None  # 无 frontmatter，跳过

    meta = yaml.safe_load(match.group(1))  # 解析 YAML
    if not {"name", "description", "trigger"}.issubset(meta.keys()):
        return None  # 缺少必填字段，跳过

    prompt = content[match.end():].strip()  # frontmatter 之后的内容
    return Skill(name=meta["name"], description=meta["description"],
                 trigger=meta["trigger"], prompt=prompt, source=source)
```

**容错设计**：
- 无 frontmatter → 跳过（不是 Skill 文件）
- YAML 解析失败 → 跳过（不崩溃）
- 缺少必填字段 → 跳过（不崩溃）
- 非 `.md` 文件 → 忽略

**为什么用正则而不是第三方库？**

`python-frontmatter` 库可以解析，但引入额外依赖。正则 `^---\s*\n(.*?)\n---\s*\n` 足够处理标准格式，且 `yaml.safe_load()` 已经在依赖中。YAGNI——不为简单需求引入新依赖。

---

## 5. 动态 system_prompt 拼接

Skill 激活后，prompt 需要注入到 LLM 的 system 消息中。有三种策略：

### 策略 A：直接修改 system_prompt
```python
context.system_prompt += f"\n\n[Skill: {skill.name}]\n{skill.prompt}"
```
- 问题：永久修改，多次切换会累积

### 策略 B：作为 user 消息注入
```python
context.add_user(f"[Skill 指令] {skill.prompt}")
```
- 问题：语义不对（这是系统指令不是用户输入），且会被 `_trim()` 裁掉

### 策略 C：动态拼接（Bitz 的选择）
```python
def get_messages(self) -> list[dict]:
    msgs = [{"role": "system", "content": self.system_prompt}]
    msgs.extend(self.messages)

    # 动态拼接，不修改原始数据
    if self._active_skill:
        skill_section = f"\n\n[当前 Skill: {self._active_skill.name}]\n{self._active_skill.prompt}"
        msgs[0] = {**msgs[0], "content": msgs[0]["content"] + skill_section}

    return msgs
```

**策略 C 的优势**：
| 特性 | 效果 |
|---|---|
| 不修改原始 messages | `ctx.messages` 不受影响，干净 |
| 切换时替换 | `set_active_skill()` 直接赋值，不累积 |
| 不受 `_trim()` 影响 | Skill 不在 messages 列表中，不会被裁掉 |
| 清除即消失 | `clear_active_skill()` 后，下次 `get_messages()` 不再拼接 |

**`{**msgs[0], "content": ...}` 是什么？**

这是 Python 字典解包语法，等价于"复制 msgs[0] 但替换 content 字段"。创建新字典，不修改原字典。

---

## 6. SkillRegistry 加载与优先级

```python
class SkillRegistry:
    def __init__(self):
        self.skills: dict[str, Skill] = {}

    def load_builtin(self, path: str):
        self._load_from_dir(path, source="builtin")

    def load_user(self, path: str):
        self._load_from_dir(path, source="user")  # 同名覆盖 builtin
```

**加载顺序**：
1. 先加载内置 Skill（`Bitz/skills/`）→ `source="builtin"`
2. 再加载用户 Skill（`.bitz/skills/`）→ `source="user"`

因为 `self.skills[skill.name] = skill` 是字典赋值，后加载的同名 Skill 会覆盖先加载的。这就是**用户 Skill 优先级高于内置 Skill** 的实现原理。

**为什么用 `dict[name, Skill]` 而不是 `list[Skill]`？**

- 按 name 查找是 O(1) vs O(n)
- 天然去重（同名覆盖）
- `list_all()` 返回 `list(self.skills.values())` 即可

---

## 7. TUI 集成：命令补全

Skill trigger 需要出现在 `/` 命令补全列表中：

```python
# command_popup.py

BASE_COMMANDS = [
    ("/help", "显示帮助信息"),
    ("/clear", "清屏"),
    ("/compact", "压缩上下文"),
    ("/theme [name]", "切换主题"),
    ("/models", "模型管理弹窗"),
]

def build_commands(skill_registry=None) -> list[tuple[str, str]]:
    commands = list(BASE_COMMANDS)
    if skill_registry is not None:
        for skill in skill_registry.list_all():
            commands.append((skill.trigger, skill.description))
    return commands
```

**设计要点**：
- `BASE_COMMANDS` 是硬编码的，不会变
- `build_commands()` 动态追加 Skill trigger，每次创建 `CommandPopup` 时调用
- `InputBar` 持有 `skill_registry` 引用，创建 `CommandPopup` 时传入

---

## 8. 完整数据流

```
用户输入 /review
  → InputBar 检测 / 前缀 → CommandSubmitted(command="review")
  → BitzApp.on_input_bar_command_submitted()
    → skill_registry.get_by_trigger("/review") → Skill(name="code-review", ...)
    → _activate_skill(skill)
      → context.set_active_skill(skill)
      → chat.add_message("assistant", "已激活 Skill: code-review")

用户输入 "帮我看看 main.py"
  → InputBar → MessageSubmitted
  → BitzApp._run_agent()
    → agent.run("帮我看看 main.py")
      → context.get_messages()
        → 动态拼接: system_prompt + "\n\n[当前 Skill: code-review]\n你是代码审查专家..."
      → LLM 收到带 Skill 指令的 system prompt
      → LLM 按 Skill 指令行动（先 glob，再 read_file，再 grep...）

用户输入 /skill off
  → BitzApp → context.clear_active_skill()
  → 下次 get_messages() 不再拼接 Skill prompt
```

---

## 9. 扩展思考

### Skill vs Plugin

| 维度 | Skill | Plugin |
|---|---|---|
| 定义 | 行为指令（prompt） | 功能扩展（代码） |
| 修改 | 编辑 Markdown | 编写 Python |
| 风险 | 低（只是 prompt） | 高（执行任意代码） |
| 适合 | 流程编排、角色设定 | 新增工具、API 集成 |

Bitz 的 Skill 是纯 prompt，不执行代码，所以安全。如果未来需要 Plugin，需要沙箱机制。

### 自动激活（未实现）

当前 Skill 只能手动 `/skill-name` 触发。自动激活需要：
1. 将所有 Skill 的 description 嵌入到 system_prompt
2. LLM 判断用户意图是否匹配某个 Skill
3. 返回特殊标记触发 Skill

这增加了 system_prompt 长度和复杂度，教学项目暂不需要。

### 参数替换（未实现）

Claude Code 的 Skill 支持 `$ARGUMENTS` 占位符：
```markdown
请审查 $ARGUMENTS 中的代码
```

用户输入 `/review src/main.py` 时，`src/main.py` 替换 `$ARGUMENTS`。实现简单（字符串替换），但当前 Skill prompt 用自然语言描述目标即可，Agent 会从对话上下文理解。

---

## 10. 关键代码索引

| 文件 | 职责 |
|---|---|
| `agent/skills.py` | Skill 数据类、SkillRegistry、frontmatter 解析 |
| `agent/context.py` | `set_active_skill()`、`clear_active_skill()`、`get_messages()` 动态拼接 |
| `tui/app.py` | `_activate_skill()`、`/skill` 命令、Skill 命令路由 |
| `tui/widgets/command_popup.py` | `build_commands()` 动态构建补全列表 |
| `skills/*.md` | 内置 Skill 定义文件 |

---

## 练习

1. **创建自定义 Skill**：在 `.bitz/skills/` 下创建 `refactor.md`，定义一个重构建议 Skill
2. **覆盖内置 Skill**：创建与内置同名的 Skill 文件，验证用户版本覆盖内置版本
3. **观察动态拼接**：在 `_activate_skill()` 后打印 `context.get_messages()[0]["content"]`，观察 Skill prompt 如何拼接到 system 消息末尾
4. **思考**：如果 Skill prompt 很长（>2000 tokens），会对 Agent 行为产生什么影响？应该如何处理？
