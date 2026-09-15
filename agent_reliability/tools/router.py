"""Tool router: allowlist, schema validation, timeouts, retries, idempotency."""

from __future__ import annotations

import hashlib
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any

from pydantic import ValidationError

from agent_reliability.observe.taxonomy import FailureClass
from agent_reliability.observe.trace import EventType, TraceEvent, TraceSink
from agent_reliability.tools.base import BaseTool, ToolResult


class ToolRouter:
    def __init__(
        self,
        tools: list[BaseTool],
        *,
        trace: TraceSink | None = None,
        run_id: str = "unknown",
        jitter_s: float = 0.05,
    ) -> None:
        self._tools: dict[str, BaseTool] = {t.spec.name: t for t in tools}
        self.trace = trace
        self.run_id = run_id
        self.jitter_s = jitter_s
        # idempotency_key -> ToolResult for write tools
        self._idempotency_cache: dict[str, ToolResult] = {}

    def list_tools(self) -> list[str]:
        return sorted(self._tools)

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def call(
        self,
        name: str,
        args: dict[str, Any],
        *,
        step: int | None = None,
        idempotency_key: str | None = None,
    ) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            result = ToolResult(
                ok=False,
                error=f"tool not allowlisted: {name}",
                failure_class=FailureClass.TOOL_SCHEMA_ERROR.value,
            )
            self._emit_call(name, args, result, step=step)
            return result

        try:
            validated = tool.validate_args(args)
        except ValidationError as exc:
            result = ToolResult(
                ok=False,
                error=str(exc),
                failure_class=FailureClass.TOOL_SCHEMA_ERROR.value,
            )
            self._emit_call(name, args, result, step=step)
            return result

        key = idempotency_key
        if tool.spec.is_write and key is None:
            key = self._derive_idempotency_key(name, validated.model_dump())

        if tool.spec.is_write and key and key in self._idempotency_cache:
            cached = self._idempotency_cache[key].model_copy(update={"cached": True})
            self._emit_call(name, args, cached, step=step, idempotency_key=key)
            return cached

        max_attempts = 1 + (tool.spec.max_retries if tool.spec.retry_on_error else 0)
        last: ToolResult | None = None

        for attempt in range(1, max_attempts + 1):
            last = self._invoke_once(tool, validated, attempt=attempt, idempotency_key=key)
            self._emit_call(name, args, last, step=step, idempotency_key=key)
            if last.ok:
                if tool.spec.is_write and key:
                    self._idempotency_cache[key] = last
                return last
            if last.failure_class == FailureClass.TIMEOUT.value:
                # timeouts still count toward retries if configured
                pass
            if attempt < max_attempts and tool.spec.retry_on_error:
                time.sleep(self.jitter_s * (1 + random.random()))
                continue
            break

        assert last is not None
        if not last.ok and last.failure_class != FailureClass.TIMEOUT.value and attempt >= max_attempts and tool.spec.max_retries > 0:
            last = last.model_copy(
                update={"failure_class": FailureClass.RETRY_EXHAUSTED.value}
            )
        return last

    def _invoke_once(
        self,
        tool: BaseTool,
        validated: Any,
        *,
        attempt: int,
        idempotency_key: str | None,
    ) -> ToolResult:
        started = time.perf_counter()
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(
                    tool.execute, validated, idempotency_key=idempotency_key
                )
                output = fut.result(timeout=tool.spec.timeout_s)
            duration_ms = (time.perf_counter() - started) * 1000
            return ToolResult(
                ok=True,
                output=output,
                duration_ms=duration_ms,
                attempt=attempt,
                idempotency_key=idempotency_key,
            )
        except FuturesTimeout:
            duration_ms = (time.perf_counter() - started) * 1000
            return ToolResult(
                ok=False,
                error=f"timeout after {tool.spec.timeout_s}s",
                failure_class=FailureClass.TIMEOUT.value,
                duration_ms=duration_ms,
                attempt=attempt,
                idempotency_key=idempotency_key,
            )
        except Exception as exc:  # noqa: BLE001 (surfaced as tool_execution_error)
            duration_ms = (time.perf_counter() - started) * 1000
            return ToolResult(
                ok=False,
                error=str(exc),
                failure_class=FailureClass.TOOL_EXECUTION_ERROR.value,
                duration_ms=duration_ms,
                attempt=attempt,
                idempotency_key=idempotency_key,
            )

    def _derive_idempotency_key(self, name: str, args: dict[str, Any]) -> str:
        payload = json.dumps({"tool": name, "args": args}, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:24]

    def _emit_call(
        self,
        name: str,
        args: dict[str, Any],
        result: ToolResult,
        *,
        step: int | None,
        idempotency_key: str | None = None,
    ) -> None:
        if self.trace is None:
            return
        self.trace.emit(
            TraceEvent(
                run_id=self.run_id,
                event_type=EventType.TOOL_CALL,
                step=step,
                tool_name=name,
                args=args,
                attempt=result.attempt,
                idempotency_key=idempotency_key or result.idempotency_key,
            )
        )
        self.trace.emit(
            TraceEvent(
                run_id=self.run_id,
                event_type=EventType.TOOL_RESULT,
                step=step,
                tool_name=name,
                result=result.output if result.ok else None,
                error=result.error,
                failure_class=result.failure_class,
                duration_ms=result.duration_ms,
                attempt=result.attempt,
                idempotency_key=idempotency_key or result.idempotency_key,
                metadata={"cached": result.cached, "ok": result.ok},
            )
        )
