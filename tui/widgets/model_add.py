from __future__ import annotations

from textual.screen import ModalScreen
from textual.widgets import Input, Button, Static, Select
from textual.containers import Vertical, Horizontal


# Provider 预设: (protocol, base_url)
PROVIDER_PRESETS = {
    "openai": ("openai", "https://api.openai.com/v1"),
    "anthropic": ("anthropic", "https://api.anthropic.com"),
    "custom_openai": ("openai", ""),
    "custom_anthropic": ("anthropic", ""),
}


class ModelAddScreen(ModalScreen):
    """添加模型表单弹窗。"""

    DEFAULT_CSS = """
    ModelAddScreen {
        align: center middle;
    }

    ModelAddScreen > Vertical {
        width: 50;
        height: auto;
        background: $surface;
        border: solid $primary;
        padding: 1 2;
    }

    ModelAddScreen .form-title {
        text-align: center;
        margin-bottom: 1;
    }

    ModelAddScreen .form-label {
        color: $text-muted;
        margin-bottom: 0;
    }

    ModelAddScreen Input {
        margin-bottom: 1;
    }

    ModelAddScreen Select {
        margin-bottom: 1;
    }

    ModelAddScreen .error-text {
        color: $error;
        margin-bottom: 1;
    }

    ModelAddScreen Horizontal {
        height: auto;
        align: center middle;
    }

    ModelAddScreen Button {
        margin: 0 1;
    }
    """

    def __init__(self, error: str = "") -> None:
        super().__init__()
        self._error = error

    def compose(self):
        with Vertical():
            yield Static("添加模型", classes="form-title")
            if self._error:
                yield Static(self._error, classes="error-text")
            yield Static("ID", classes="form-label")
            yield Input(placeholder="模型标识，如 gpt-4o", id="id-input")
            yield Static("Provider", classes="form-label")
            yield Select(
                [("OpenAI", "openai"), ("Anthropic", "anthropic"),
                 ("自定义 (OpenAI 协议)", "custom_openai"), ("自定义 (Anthropic 协议)", "custom_anthropic")],
                value="openai",
                id="provider-select",
            )
            yield Static("Base URL", classes="form-label")
            yield Input(value="https://api.openai.com/v1", placeholder="API 地址", id="base-url-input")
            yield Static("API Key", classes="form-label")
            yield Input(placeholder="sk-...", password=True, id="api-key-input")
            yield Static("模型名", classes="form-label")
            yield Input(placeholder="如 gpt-4o, claude-3-5-sonnet-20241022", id="model-input")
            with Horizontal():
                yield Button("确认添加", variant="primary", id="confirm-btn")
                yield Button("取消", variant="default", id="cancel-btn")

    def on_select_changed(self, event: Select.Changed) -> None:
        """Provider 选择变化时自动填充 base_url。"""
        if event.select.id == "provider-select":
            provider = event.value
            base_url_input = self.query_one("#base-url-input", Input)
            if provider in PROVIDER_PRESETS:
                base_url_input.value = PROVIDER_PRESETS[provider][1]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
            return

        if event.button.id == "confirm-btn":
            id_val = self.query_one("#id-input", Input).value.strip()
            provider = self.query_one("#provider-select", Select).value
            base_url = self.query_one("#base-url-input", Input).value.strip()
            api_key = self.query_one("#api-key-input", Input).value.strip()
            model = self.query_one("#model-input", Input).value.strip()

            # 验证必填字段
            errors = []
            if not id_val:
                errors.append("ID 不能为空")
            if not base_url:
                errors.append("Base URL 不能为空")
            if not api_key:
                errors.append("API Key 不能为空")
            if not model:
                errors.append("模型名 不能为空")
            if provider == Select.BLANK:
                errors.append("请选择 Provider")

            if errors:
                # 返回错误信息，让回调处理重新显示表单
                self.dismiss(("error", "；".join(errors)))
                return

            # 从预设中获取 protocol
            protocol = PROVIDER_PRESETS.get(provider, (provider, ""))[0]

            # 返回表单数据，让回调处理创建 ModelConfig
            self.dismiss(("data", {
                "id": id_val,
                "protocol": protocol,
                "base_url": base_url,
                "api_key": api_key,
                "model": model,
            }))

    def key_escape(self) -> None:
        self.dismiss(None)
