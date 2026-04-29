from __future__ import annotations

from textual.screen import ModalScreen
from textual.widgets import Button, Static
from textual.containers import Vertical, Horizontal


class ModelConfirmScreen(ModalScreen):
    """删除模型确认弹窗。"""

    DEFAULT_CSS = """
    ModelConfirmScreen {
        align: center middle;
    }

    ModelConfirmScreen > Vertical {
        width: 36;
        height: auto;
        background: $surface;
        border: solid $error;
        padding: 1 2;
    }

    ModelConfirmScreen .confirm-text {
        text-align: center;
        margin-bottom: 1;
    }

    ModelConfirmScreen Horizontal {
        height: auto;
        align: center middle;
    }

    ModelConfirmScreen Button {
        margin: 0 1;
    }
    """

    def __init__(self, model_id: str) -> None:
        super().__init__()
        self._model_id = model_id

    def compose(self):
        with Vertical():
            yield Static(f"确定删除模型 '{self._model_id}'？", classes="confirm-text")
            with Horizontal():
                yield Button("确认删除", variant="error", id="confirm-btn")
                yield Button("取消", variant="default", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-btn":
            self.dismiss(("delete", self._model_id))
        else:
            self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)
