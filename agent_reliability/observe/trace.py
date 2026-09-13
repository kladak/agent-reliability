"""Trace event schema and JSONL sink."""

from __future__ import annotations

import json
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    RUN_START = "run_start"
    RUN_END = "run_end"
    STEP_START = "step_start"
    STEP_END = "step_end"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    AGENT_MESSAGE = "agent_message"
    ERROR = "error"
    METRIC = "metric"


class TraceEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ts: float = Field(default_factory=time.time)
    run_id: str
    event_type: EventType
    step: int | None = None
    tool_name: str | None = None
    args: dict[str, Any] | None = None
    result: Any | None = None
    error: str | None = None
    failure_class: str | None = None
    duration_ms: float | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    idempotency_key: str | None = None
    attempt: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TraceSink:
    """Append-only JSONL sink for run traces."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", encoding="utf-8")

    def emit(self, event: TraceEvent) -> None:
        self._fh.write(event.model_dump_json() + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()

    def __enter__(self) -> TraceSink:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def read_trace(path: Path | str) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    p = Path(path)
    if not p.exists():
        return events
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                events.append(TraceEvent.model_validate_json(line))
    return events
