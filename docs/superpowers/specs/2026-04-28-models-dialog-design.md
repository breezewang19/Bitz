# 模型管理弹窗交互设计

## Context

当前 `/models` 命令使用单行参数输入（如 `/models add gpt-4o openai https://api.openai.com/v1 sk-key gpt-4o`），5 个参数一行输入，容易打错、参数顺序难记、API key 明文暴露。切换模型需记住 ID，没有选择界面。用户希望更友好的交互方式。

## 设计目标

将 `/models` 命令从"单行参数命令"改为"弹窗交互"，使用 Textual ModalScreen 模式：
- 切换模型 → 选择列表弹窗（上下键选择，回车切换）
- 添加模型 → 表单弹窗（逐项填写，下拉选择协议/provider，API key 遮蔽）
- 删除模型 → 确认弹窗

## 架构

使用 Textual `ModalScreen` + `push_screen/dismiss` 模式。每个弹窗是独立的 Screen 类，封装交互逻辑，通过 `dismiss(result)` 返回结果给 `BitzApp` 回调处理。

### 1. `/models` → ModelSelectScreen

输入 `/models` 时弹出模型选择列表弹窗。

**内容：**
- `OptionList` 显示所有已配置模型，每个选项格式：`{id} ({protocol}/{model})`
- 当前模型标 `←`
- 底部三个按钮：`切换`、`添加`、`删除`
- ESC 关闭弹窗

**交互流程：**
- 选中一个模型 → 点击 `切换` → dismiss 返回 `("switch", model_id)` → BitzApp 调用 `_switch_model`
- 点击 `添加` → dismiss 返回 `("add", None)` → BitzApp 弹出 ModelAddScreen
- 选中一个模型 → 点击 `删除` → dismiss 返回 `("delete", model_id)` → BitzApp 弹出确认后删除

**CSS：**
- 模态背景半透明（`$background 60%`）
- 弹窗居中，宽度 40，高度 auto
- 选项高亮使用 `$primary-background`

### 2. ModelAddScreen — 表单弹窗

**字段：**
- **ID**：`Input`（placeholder: "模型标识，如 gpt-4o"），必填
- **协议/Provider**：`Select` 下拉，选项：
  - `OpenAI` → base_url 预填 `https://api.openai.com/v1`
  - `Anthropic` → base_url 预填 `https://api.anthropic.com`
  - `自定义` → base_url 空白，手动填写
- **Base URL**：`Input`（根据 provider 选择自动填充，选择"自定义"时需手动输入）
- **API Key**：`Input(password=True)`（显示 ***，placeholder: "sk-..."）
- **模型名**：`Input`（placeholder: "如 gpt-4o, claude-3-5-sonnet-20241022"），必填

**底部按钮：** `确认添加`、`取消`

**交互流程：**
- 选择 Provider → 自动填充 base_url + 更新 placeholder
- 点击 `确认添加` → 验证所有必填字段 → 创建 `ModelConfig` → `ModelStore.add()` → dismiss 返回 `ModelConfig`
- 验证失败 → 在字段旁显示红色错误提示
- 点击 `取消` → dismiss 返回 `None`
- ESC → 同取消

**CSS：**
- 模态背景半透明
- 弹窗居中，宽度 50
- 表单字段间距 1 行
- 错误提示红色文字

### 3. 删除确认弹窗

在 ModelSelectScreen 中选中模型后点击 `删除`，弹出简单确认弹窗：

**内容：**
- 文字：`确定删除模型 '{id}'？`
- 两个按钮：`确认删除`、`取消`

**交互：**
- 确认 → `ModelStore.remove(id)` → dismiss 返回 `("deleted", id)`
- 取消 → dismiss 返回 `None`

### 4. ModelStore 新增 `remove()` 方法

```python
def remove(self, id: str) -> None:
    data = self._load()
    if not any(m["id"] == id for m in data["models"]):
        raise ValueError(f"模型 '{id}' 不存在")
    data["models"] = [m for m in data["models"] if m["id"] != id]
    if data["current"] == id:
        data["current"] = data["models"][0]["id"] if data["models"] else None
    self._save(data)
```

### 5. 命令变更

**主命令 `/models`：**
- 弹出 ModelSelectScreen（不再需要子命令）
- 保留快捷子命令向后兼容：
  - `/models list` → 仍输出 Markdown 表格到聊天（不弹窗）
  - `/models add <args>` → 仍支持单行添加（不弹窗）
  - `/models <id>` → 仍支持快捷切换（不弹窗）
- `/models` 无参数时 → 弹窗

**CommandPopup：**
- `/models` 描述改为 "模型管理弹窗"

### 6. BitzApp 回调处理

```python
def on_mount(self):
    # ... existing code ...
    # 注册模型弹窗回调
    # (不需要额外注册，push_screen 的 callback 参数处理)

def _handle_models_command(self, args, chat):
    if not args:
        # 弹窗模式
        self.app.push_screen(ModelSelectScreen(self._model_store), self._on_models_result)
        return
    # 原有子命令逻辑不变...

def _on_models_result(self, result):
    if result is None:
        return
    action, data = result
    if action == "switch":
        config = self._model_store.get(data)
        if config:
            self._switch_model(config)
    elif action == "add":
        self.app.push_screen(ModelAddScreen(), self._on_model_added)
    elif action == "delete":
        self.app.push_screen(ModelConfirmScreen(data), self._on_model_deleted)

def _on_model_added(self, result):
    if result is None:
        return
    config = result  # ModelConfig
    self._model_store.add(config)
    chat = self.query_one(ChatLog)
    chat.add_message("assistant", f"模型 '{config.id}' 已添加")

def _on_model_deleted(self, result):
    if result is None:
        return
    action, model_id = result
    self._model_store.remove(model_id)
    chat = self.query_one(ChatLog)
    chat.add_message("assistant", f"模型 '{model_id}' 已删除")
```

## 文件变更

| 文件 | 操作 | 职责 |
|------|------|------|
| `tui/widgets/model_select.py` | 新建 | ModelSelectScreen — 模型选择列表弹窗 |
| `tui/widgets/model_add.py` | 新建 | ModelAddScreen — 添加模型表单弹窗 |
| `tui/widgets/model_confirm.py` | 新建 | ModelConfirmScreen — 删除确认弹窗 |
| `agent/models.py` | 修改 | 新增 `remove()` 方法 |
| `tui/app.py` | 修改 | `/models` 无参数时弹窗，新增回调方法 |
| `tui/widgets/command_popup.py` | 修改 | 更新 `/models` 描述 |
| `tui/widgets/__init__.py` | 修改 | 导出新 widget |
| `tests/test_models.py` | 修改 | 新增 `remove()` 测试 |
| `tests/test_tui_app.py` | 修改 | 新增弹窗交互测试 |

## 验证

1. 输入 `/models` → 弹出选择列表，显示所有已配置模型
2. 选中模型 → 点击切换 → StatusBar 更新，聊天显示确认消息
3. 点击添加 → 弹出表单 → 选择 Provider → base_url 自动填充 → 输入 API key（显示 ***） → 确认添加 → 模型出现在列表中
4. 选中模型 → 点击删除 → 确认弹窗 → 确认 → 模型从列表消失
5. `/models list`、`/models add <args>`、`/models <id>` 仍正常工作（向后兼容）
6. ESC 随时关闭弹窗
7. `pytest tests/ -v` 全部通过