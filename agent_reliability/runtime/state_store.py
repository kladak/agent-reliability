"""File-backed checkpoint store for resume-after-crash demos."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError


class StateCorruptionError(Exception):
    """Checkpoint exists but cannot be parsed into a valid Checkpoint."""


class Checkpoint(BaseModel):
    run_id: str
    next_step: int  # 1-based index of the next plan step to execute
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class StateStore:
    """Persist one checkpoint JSON per run_id under a directory."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        safe = run_id.replace("/", "_")
        return self.root / f"{safe}.checkpoint.json"

    def save(self, checkpoint: Checkpoint) -> Path:
        path = self._path(checkpoint.run_id)
        path.write_text(checkpoint.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return path

    def load(self, run_id: str) -> Checkpoint | None:
        path = self._path(run_id)
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8")
        try:
            return Checkpoint.model_validate_json(raw)
        except (ValidationError, json.JSONDecodeError, ValueError) as exc:
            raise StateCorruptionError(
                f"corrupt checkpoint for run_id={run_id}: {exc}"
            ) from exc

    def clear(self, run_id: str) -> None:
        path = self._path(run_id)
        if path.exists():
            path.unlink()
