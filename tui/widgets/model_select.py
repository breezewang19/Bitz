from __future__ import annotations

from textual.screen import ModalScreen
from textual.widgets import OptionList, Button, Static
from textual.containers import Vertical, Horizontal
from textual.message import Message
from rich.text import Text


class ModelSelectScreen(ModalScreen):
    """模型选择列表弹窗。"""

    DEFAULT_CSS = """
    ModelSelectScreen {
        align: center middle;
    }

    ModelSelectScreen > Vertical {
        width: 40;
        height: auto;
        max-height: 20;
        background: $surface;
        border: solid $primary;
        padding: 1 2;
    }

    ModelSelectScreen .model-title {
        text-align: center;
        margin-bottom: 1;
    }

    ModelSelectScreen OptionList {
        height: auto;
        max-height: 10;
        margin-bottom: 1;
    }

    ModelSelectScreen Horizontal {
        height: auto;
        align: center middle;
    }

    ModelSelectScreen Button {
        margin: 0 1;
    }
    """

    class ModelAction(Message):
        def __init__(self, action: str, model_id: str | None) -> None:
            super().__init__()
            self.action = action
            self.model_id = model_id

    def __init__(self, model_store) -> None:
        super().__init__()
        self._model_store = model_store

    def compose(self):
        with Vertical():
            yield Static("模型管理", classes="model-title")
            models = self._model_store.list_all()
            current = self._model_store.get_current()
            current_id = current.id if current else None
            option_list = OptionList()
            for m in models:
                marker = " ←" if m.id == current_id else ""
                label = Text.assemble(
                    Text(f"{m.id}", style="bold cyan"),
                    Text(f" ({m.protocol}/{m.model})", style="dim"),
                    Text(marker, style="green"),
                )
                option_list.add_option(label)
            yield option_list
            with Horizontal():
                yield Button("切换", variant="primary", id="switch-btn")
                yield Button("添加", variant="success", id="add-btn")
                yield Button("删除", variant="error", id="delete-btn")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """双击选项直接切换。"""
        models = self._model_store.list_all()
        if event.option_index < len(models):
            self.dismiss(("switch", models[event.option_index].id))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        models = self._model_store.list_all()
        option_list = self.query_one(OptionList)
        selected = option_list.highlighted

        if event.button.id == "add-btn":
            self.dismiss(("add", None))
        elif event.button.id == "switch-btn":
            if selected is not None and selected < len(models):
                self.dismiss(("switch", models[selected].id))
        elif event.button.id == "delete-btn":
            if selected is not None and selected < len(models):
                self.dismiss(("delete", models[selected].id))

    def key_escape(self) -> None:
        self.dismiss(None)
