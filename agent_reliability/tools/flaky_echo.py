"""Intentional flaky tool for retry/timeout demos."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, Field

from agent_reliability.tools.base import BaseTool, ToolSpec


class FlakyEchoArgs(BaseModel):
    message: str = Field(..., min_length=1)
    fail_times: int = Field(
        2,
        ge=0,
        description="How many times to fail before succeeding (per process)",
    )


class FlakyEchoTool(BaseTool):
    """Fails the first N calls with the same message, then succeeds.

    Call counts are keyed by message so plans are deterministic in tests.
    """

    args_model = FlakyEchoArgs
    _fail_counts: ClassVar[dict[str, int]] = {}

    def __init__(self, *, timeout_s: float = 2.0, max_retries: int = 5) -> None:
        self.spec = ToolSpec(
            name="flaky_echo",
            description="Echo a message after injected transient failures",
            is_write=False,
            timeout_s=timeout_s,
            max_retries=max_retries,
            retry_on_error=True,
        )

    @classmethod
    def reset(cls) -> None:
        cls._fail_counts.clear()

    def execute(self, args: BaseModel, *, idempotency_key: str | None = None) -> Any:
        assert isinstance(args, FlakyEchoArgs)
        key = args.message
        seen = self._fail_counts.get(key, 0)
        if seen < args.fail_times:
            self._fail_counts[key] = seen + 1
            raise RuntimeError(f"injected flaky failure ({seen + 1}/{args.fail_times})")
        return {"echo": args.message, "attempts_before_success": seen}
