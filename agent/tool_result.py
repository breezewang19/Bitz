from dataclasses import dataclass, field
from typing import Any

@dataclass
class ToolResult:
    success: bool
    data: str = ""
    error_message: str = ""
    confirm_required: bool = False
    confirm_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_api_content(self) -> str:
        if self.confirm_required:
            return f"[CONFIRM_REQUIRED] {self.confirm_message}"
        if self.success:
            return self.data
        return f"Error: {self.error_message}"

    def to_display(self) -> str:
        return self.to_api_content()

    @staticmethod
    def ok(data: str, **metadata) -> "ToolResult":
        return ToolResult(success=True, data=data, metadata=metadata)

    @staticmethod
    def error(error: str) -> "ToolResult":
        return ToolResult(success=False, error_message=error)

    @staticmethod
    def confirm(message: str) -> "ToolResult":
        return ToolResult(
            success=False,
            confirm_required=True,
            confirm_message=message,
        )
