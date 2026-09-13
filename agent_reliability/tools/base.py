"""Base tool protocol and call results."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    ok: bool
    output: Any = None
    error: str | None = None
    failure_class: str | None = None
    duration_ms: float | None = None
    attempt: int = 1
    idempotency_key: str | None = None
    cached: bool = False


class ToolSpec(BaseModel):
    name: str
    description: str
    is_write: bool = False
    timeout_s: float = 5.0
    max_retries: int = 0
    # Retry only transient failures when True
    retry_on_error: bool = False


class BaseTool(ABC):
    """Schema-validated tool. Subclasses define args_model and execute()."""

    spec: ToolSpec
    args_model: type[BaseModel]

    @abstractmethod
    def execute(self, args: BaseModel, *, idempotency_key: str | None = None) -> Any:
        ...

    def validate_args(self, raw: dict[str, Any]) -> BaseModel:
        return self.args_model.model_validate(raw)
