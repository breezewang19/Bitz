# Agent 框架架构调研报告

**日期**：2026-04-23
**目标**：调研主流 Agent 框架的架构设计和技术特点

---

## 前言

本报告调研当前主流的 Agent 框架，涵盖从最小循环到完整 Agent 系统的各类方案。重点分析各框架的架构设计、核心组件和适用场景。

---

## 一、Agent 框架全景图

### 1.1 框架分类

根据定位和复杂度，当前 Agent 框架可分为四类：

| 类别 | 代表框架 | 特点 | 适用场景 |
|------|---------|------|----------|
| **最小循环** | felixwickholm/claude-agent-loop | ~150 行，专注核心循环 | 学习原理 |
| **开发组件库** | OpenHarness | 10 子系统，可插拔 | 开发者集成 |
| **完整 Agent 运行时** | OpenClaw | Gateway + Runtime + 适配器 | 直接使用 |
| **多 Agent 协作** | ChatDev, MetaGPT | 多个 Agent 分工 | 复杂任务 |

### 1.2 各框架一句话定位

| 框架 | 定位 | 一句话描述 |
|------|------|-----------|
| **OpenClaw** | AI Agent 操作系统 | 本地优先的多渠道 Agent 运行时 |
| **OpenHarness** | Agent 开发组件库 | 提供构建 Agent 的全套基础设施 |
| **SWE-agent** | 代码修复 Agent | 普林斯顿的 GitHub Issue 自动修复 |
| **OpenCode** | AI 编程代理 | 隐私优先的终端编程工具 |
| **ChatDev** | 虚拟软件公司 | 多 Agent 协作完成软件开发 |
| **Deer Flow** | 超级研究 Agent | 基于 LangStack 的深度研究框架 |
| **OpenManus** | 快速原型框架 | 简洁透明的多协议 Agent 框架 |
| **MetaGPT** | 多 Agent 协作 | 角色扮演的多 Agent 软件开发 |

---

## 二、OpenClaw — AI Agent 操作系统

### 2.1 核心定位

OpenClaw 是一个**无头智能体运行时（Headless Agent Runtime）**，本质是一个守护进程，通过即时通讯软件（Telegram、飞书、WhatsApp 等）作为交互界面。

定位是**"数字员工"**，而非聊天机器人——强调能干活（操控电脑、处理文件、发送邮件）。

### 2.2 架构设计：中心辐射式（Hub-and-Spoke）

```
                    ┌─────────────────────────────────┐
                    │         Gateway（网关层）          │
                    │  端口 18789，维护 WebSocket 连接   │
                    │  消息路由、会话隔离、访问控制       │
                    └─────────────┬───────────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
    ┌─────────▼─────────┐ ┌──────▼──────┐ ┌────────▼────────┐
    │   飞书适配器       │ │  Telegram   │ │   iMessage     │
    │   Webhook/Bot API │ │  Bot Token  │ │   适配器       │
    └───────────────────┘ └─────────────┘ └────────────────┘

              ┌───────────────────┼───────────────────┐
              │                   │                   │
    ┌─────────▼─────────────────▼───────────────────▼─────────┐
    │                   Agent Runtime（运行时层）               │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
    │  │ 记忆系统  │  │ 工具系统  │  │ Skill    │  │ 安全    │ │
    │  │ (JSONL+  │  │ Registry │  │ 管理器    │  │ 策略    │ │
    │  │  FTS5)   │  │          │  │          │  │         │ │
    │  └──────────┘  └──────────┘  └──────────┘  └─────────┘ │
    └─────────────────────────────────────────────────────┘
```

### 2.3 三层架构详解

#### Gateway 层（交通指挥中心）

- **端口**：默认 18789（本地回环）
- **职责**：
  - 连接管理：维护 WebSocket 长连接
  - 消息路由：判断消息发给哪个 Agent
  - 会话隔离：确保用户对话不串台
  - 访问控制：第一道防火墙
- **设计原则**：网关只负责传话，不碰 AI 逻辑

#### Agent Runtime 层（执行引擎）

四个关键步骤的循环：

```
1. 翻旧账 → 查询记忆库（JSONL 文件 + FTS5 向量检索）
2. 翻工具书 → 确认会话配备的 Skill 列表
3. 组装提示词 → 合并系统提示词、记忆片段、工具列表
4. 执行与回调 → 调用相应 Skill 并处理结果
```

**内置容灾**：API 挂掉时自动降级备用模型。

#### 通道适配器层（翻译官团队）

支持 10+ 种接入渠道：

| 渠道 | 认证方式 | 库/协议 |
|------|---------|---------|
| 飞书 | Webhook/Bot API | Feishu SDK |
| Telegram | Bot Token | Telegram Bot API |
| WhatsApp | Baileys | WebSocket |
| iMessage | macOS 原生 | Private API |
| Discord | Webhook | Discord API |

### 2.4 配置体系

OpenClaw 用纯文本文件分离不同类型的内容：

| 文件 | 内容 | 变化频率 |
|------|------|---------|
| `SOUL.md` | 核心人格、决策逻辑 | 几乎不变 |
| `openclaw.json` | 工具/Skill 配置 | Skill 增删时 |
| `HEARTBEAT.md` | 周期性主动行为规则 | 时间驱动 |
| `MEMORY.md` | 持续进化的经验记录 | 每次任务后 |

### 2.5 Skill 系统

**架构**：每个 Skill 是一个文件夹，包含 `SKILL.md` 和可选的脚本。

```
skill-name/
├── SKILL.md          # 核心指令（给 LLM 看）
├── scripts/          # 可选脚本
│   └── do_something.py
└── config.yaml       # 可选配置（API key 等）
```

**安装方式**：`openclaw skill install tavily-search`

**关键设计**：Skill 是纯文本接口，利用 LLM 的上下文学习能力，不需要 OpenAPI 规范。

### 2.6 安全机制

- **配对机制（Pairing）**：设备绑定认证
- **指令分类**：不同渠道的指令分级
- **权限沙箱**：高危操作需要额外确认
- **审计追溯**：所有操作记录在案

---

## 三、OpenHarness — Agent 开发组件库

### 3.1 核心定位

**Harness 概念**：包裹在 LLM 之外、为模型赋予完整执行能力的全套基础设施。

> 模型负责智能与推理，Harness 提供**双手、眼睛、记忆和安全边界**。

定位是**"构建 Agent 的核心组件"**，面向需要集成 Agent 能力的开发者。

### 3.2 十大子系统架构

```
OpenHarness
├── engine/           # Agent Loop（查询→流→工具调用→循环）
├── tools/           # 43+ 工具（文件 I/O、Shell、搜索、Web、MCP）
├── skills/          # 按需加载的技能系统（.md 格式）
├── plugins/         # 扩展（命令、钩子、代理、MCP 服务器）
├── permissions/     # 多级安全权限模式
├── hooks/          # PreToolUse/PostToolUse 生命周期钩子
├── commands/       # 54 条命令
├── mcp/            # Model Context Protocol 客户端
├── memory/         # 跨会话持久化记忆
└── coordinator/     # 多 Agent 协调（子 Agent 派生、团队管理）
```

### 3.3 支持的 Agent 类型

| 类型 | 说明 |
|------|------|
| CLI 代理集成 | OpenClaw、nanobot、Cursor |
| `ohmo` 个人代理 | 支持 飞书/Slack/Telegram/Discord |
| 子 Agent 派生 | 团队协作 |
| 模型桥接 | Claude/Codex 订阅、GitHub Copilot OAuth |
| 自定义 API | OpenAI、DeepSeek、Ollama 等 |

### 3.4 关键特性

- **工具调用循环**：标准的 ReAct 模式
- **API 指数退避重试**：网络抖动时自动重试
- **并行工具执行**：多工具可同时调用
- **上下文压缩**：长对话自动摘要
- **权限检查**：PreToolUse/PostToolUse 钩子
- **React TUI 界面**：终端可视化

---

## 四、SWE-agent — 代码修复 Agent

### 4.1 核心定位

普林斯顿大学 NLP 团队开发的 **GitHub Issue 自动修复 Agent**。

在 SWE-bench 基准测试中达到开源最优，能修复真实 GitHub 仓库的问题。

### 4.2 ACI 设计理念

**ACI（Agent-Computer Interface）**：让大模型更方便地与代码库交互的接口设计。

核心理念：
- **简洁可 hack**：单 YAML 配置文件
- **给模型最大自主权**：Free-flowing & generalizable
- **研究导向**：代码清晰，适合学术研究

### 4.3 核心架构

```
SWE-agent
├── sweagent/        # 核心 Agent Loop
├── tools/          # 工具集（文件编辑、搜索、命令执行）
├── config/         # YAML 配置
├── docker/         # 沙箱执行环境
└── trajectories/   # 执行轨迹记录
```

**Loop 流程**：
```
用户输入 GitHub Issue
    ↓
构建环境（Docker 沙箱）
    ↓
Agent Loop（最多 N 步）
    ├── 感知：读取文件、搜索代码
    ├── 规划：决定下一步操作
    ├── 行动：Edit / Bash / Grep
    └── 观察：检查结果
    ↓
输出修复或失败原因
```

### 4.4 内置工具

| 工具 | 功能 |
|------|------|
| `Edit` | 修改文件 |
| `Grep` | 搜索代码 |
| `Bash` | 执行命令 |
| `WebSearch` | 搜索文档/问题 |
| `Read` | 读取文件内容 |

### 4.5 特点

- **SWE-bench 最优**：开源项目最高12.29% 解决率
- **可配置**：单 YAML 文件控制行为
- **沙箱隔离**：Docker 环境保证安全
- **轨迹记录**：方便调试和复现

---

## 五、OpenCode — AI 编程代理

### 5.1 核心定位

开源的**终端/IDE 编程助手**，强调隐私优先（不存储代码或上下文）。

### 5.2 核心特性

| 特性 | 说明 |
|------|------|
| **隐私优先** | 不存储代码或上下文，用户完全控制分享 |
| **75+ 模型支持** | 涵盖本地模型和付费订阅 |
| **LSP 集成** | 覆盖 Rust、Swift、TypeScript、PyRight 等 |
| **多会话** | 同一项目并行启动多个代理 |
| **桌面应用** | 原生桌面 Beta 版 |
| **IDE 扩展** | VS Code、Zed、Neovim、Emacs |

### 5.3 架构设计

**LSP 集成**是核心亮点：

```
OpenCode ←→ LSP Server ←→ 代码库
    ↓
通过 LSP 获取：
- 语法错误
- 类型检查
- 代码补全
- 跳转定义
```

这让 LLM 能通过 LSP 服务器的反馈更有效地与代码库交互。

**MCP 支持**：同时支持远程和本地 MCP 服务器。

---

## 六、ChatDev — 虚拟软件公司

### 6.1 核心定位

多 Agent 协作的**虚拟软件公司**，通过不同角色的 Agent 分工完成软件开发。

### 6.2 Agent 角色

| 角色 | 职责 |
|------|------|
| CEO | 决策、任务分配 |
| CTO | 技术方案 |
| Programmer | 写代码 |
| Reviewer | 代码审查 |
| Tester | 测试 |
| Art Designer | UI/UX |

### 6.3 协作流程

```
用户需求（如：做一个博客系统）
    ↓
CEO Agent 分解任务
    ↓
┌─────────┐  ┌─────────┐  ┌─────────┐
│ Programmer │  │ Reviewer │  │ Tester  │
│   写代码   │→ │  审查    │→ │  测试   │
└─────────┘  └─────────┘  └─────────┘
    ↓
CTO Agent 汇总
    ↓
交付
```

### 6.4 版本演进

| 版本 | 定位 | 说明 |
|------|------|------|
| ChatDev 1.0 | 虚拟软件公司 | 多 Agent 角色扮演 |
| ChatDev 2.0 | 通用多 Agent 协作 | 可定制工作流、插件扩展 |

---

## 七、Deer Flow — 超级研究 Agent

### 7.1 核心定位

字节跳动开源的**深度研究框架**，基于 LangChain + LangGraph。

GitHub Stars 44K+，2026 年初排名 Trending 第一。

### 7.2 架构设计

```
Deer Flow
├── backend/        # LangGraph Agent Graph
├── frontend/       # Web 界面
├── skills/        # 研究技能
├── agent/         # Agent 定义
└── docker/        # 沙箱环境
```

**Multi-Agent 架构**：
- 主 Agent 负责任务规划
- 子 Agent 负责执行（搜索、编程、写作）
- 共享状态通过 LangGraph 的 StateGraph

### 7.3 核心能力

| 能力 | 说明 |
|------|------|
| **深度研究** | Web 搜索 + 摘要 + 报告生成 |
| **MCP 集成** | 支持 Model Context Protocol |
| **报告生成** | AI 增强编辑 |
| **播客生成** | 多模态输出 |
| **沙箱执行** | 安全执行代码 |

---

## 八、其他框架

### 8.1 OpenManus

**定位**：快速原型框架，强调"简洁透明"。

| 组件 | 说明 |
|------|------|
| 工具系统 | PythonExecute、GoogleSearch、BrowserUseTool、FileSaver |
| 记忆管理 | 短期/长期记忆，多轮交互 |
| 启动模式 | main.py（交互）、run_flow.py（流程编排） |

**与 OpenClaw 对比**：OpenManus 偏重研究实验，OpenClaw 偏重直接使用。

### 8.2 MetaGPT

**定位**：角色扮演的多 Agent 软件开发。

**特点**：
- Agent 有自己的"角色设定"
- 通过"研讨会"形式协作
- 支持强化学习算法（GRPO）

### 8.3 Mini-SWE-agent

**定位**：SWE-agent 的极简实现，100 行代码。

**特点**：
- 只用 Python 标准库 + 少量依赖
- 支持 litellm（多模型后端）
- 适合学习原理

---

## 九、框架对比总结

### 9.1 架构模式对比

| 框架 | 架构模式 | 复杂度 | 适用场景 |
|------|---------|--------|---------|
| **OpenClaw** | Hub-and-Spoke | 高 | 本地数字员工 |
| **OpenHarness** | 模块化组件 | 中高 | 开发者集成 |
| **SWE-agent** | 单 Agent Loop | 低 | 代码修复 |
| **OpenCode** | 代理 + LSP | 中 | 隐私编程 |
| **ChatDev** | 多 Agent 协作 | 中 | 软件开发 |
| **Deer Flow** | LangGraph | 中高 | 深度研究 |

### 9.2 核心组件对比

| 组件 | OpenClaw | OpenHarness | SWE-agent | OpenCode |
|------|----------|--------------|-----------|----------|
| **Agent Loop** | ✅ | ✅ | ✅ | ✅ |
| **Tool Registry** | ✅ | ✅ (43+) | ✅ | ✅ (LSP) |
| **Memory** | ✅ (JSONL) | ✅ | ❌ | ❌ |
| **Skill System** | ✅ | ✅ | ❌ | ❌ |
| **Multi-Agent** | ❌ | ✅ | ❌ | ❌ |
| **安全沙箱** | ✅ | ✅ | ✅ (Docker) | ✅ |
| **Web UI** | ❌ | ✅ (TUI) | ✅ | ✅ |

### 9.3 选型建议

| 需求 | 推荐框架 |
|------|---------|
| 学习 Agent 原理 | Mini-SWE-agent / claude-agent-loop |
| 直接当数字员工用 | OpenClaw |
| 开发 Agent 产品 | OpenHarness |
| 自动修复 GitHub Issue | SWE-agent |
| 隐私编程 | OpenCode |
| 多 Agent 协作开发 | ChatDev |
| 深度研究 | Deer Flow |

---

## 十、关键技术点总结

### 10.1 Agent 框架的核心组件

无论哪个框架，都包含以下核心组件：

```
┌─────────────────────────────────────────┐
│              Agent Framework             │
├─────────────────────────────────────────┤
│  1. Agent Loop（循环控制器）             │
│     - ReAct 模式                         │
│     - max_steps 保护                    │
│     - stop_reason 处理                   │
├─────────────────────────────────────────┤
│  2. Tool System（工具系统）               │
│     - 注册表（Registry）                 │
│     - 执行器（Executor）                 │
│     - Schema 验证                       │
├─────────────────────────────────────────┤
│  3. Memory System（记忆系统）            │
│     - 短期（对话历史）                   │
│     - 长期（文件/向量存储）               │
│     - 压缩/摘要                         │
├─────────────────────────────────────────┤
│  4. Skill System（技能系统）            │
│     - 渐进式披露                         │
│     - 按需加载                           │
├─────────────────────────────────────────┤
│  5. Security（安全）                      │
│     - 沙箱隔离                           │
│     - 权限控制                           │
│     - 审计日志                           │
└─────────────────────────────────────────┘
```

### 10.2 框架演进趋势

1. **Harness 理念**：框架越来越强调"为 LLM 提供基础设施"，而非重新造轮子
2. **隐私优先**：本地执行、数据自主成为重要考量
3. **多 Agent 协作**：从单 Agent 到多 Agent 分工
4. **安全沙箱**：生产级应用必须考虑隔离和权限
5. **Skill 即插即用**：Skill 系统标准化（MCP、SKILL.md）

---

## 参考资料

### 官方项目

- [OpenClaw](https://github.com/openclaw/openclaw)
- [OpenHarness (HKUDS)](https://github.com/HKUDS/OpenHarness)
- [SWE-agent (Princeton)](https://github.com/princeton-nlp/SWE-agent)
- [OpenCode](https://opencode.ai/)
- [ChatDev](https://github.com/OpenBMB/ChatDev)
- [Deer Flow (ByteDance)](https://github.com/bytedance/deer-flow)
- [OpenManus](https://github.com/openmanus/OpenManus)

### 技术文章

- [OpenClaw 架构深度剖析](https://blog.csdn.net/HHX_01/article/details/158658334)
- [OpenClaw 插件系统架构解析](https://www.cnblogs.com/AmazonwebService/p/19793082)
- [OpenHarness 代码解读](https://blog.csdn.net/qq_52053775/article/details/159950018)
- [SWE-agent 论文 (NeurIPS 2024)](https://arxiv.org/abs/2407.21787)
- [Agent 框架调研 19 类对比](https://blog.csdn.net/2401_85390073/article/details/143659429)
- [Deer Flow 2.0 深度解析](https://www.sohu.com/a/1011986255_121356541)
