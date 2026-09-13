"""Mock filesystem read/write tools (sandboxed under a root)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agent_reliability.tools.base import BaseTool, ToolSpec


class FsReadArgs(BaseModel):
    path: str = Field(..., description="Relative path under workspace root")


class FsWriteArgs(BaseModel):
    path: str = Field(..., description="Relative path under workspace root")
    content: str = Field(..., description="Full file contents to write")


def _resolve(root: Path, rel: str) -> Path:
    """Resolve rel under root; reject escapes via .. or absolute paths."""
    root_resolved = root.resolve()
    # Disallow absolute inputs — they must be relative to the workspace.
    rel_path = Path(rel)
    if rel_path.is_absolute():
        raise PermissionError(f"path escapes workspace root: {rel}")
    target = (root_resolved / rel_path).resolve()
    if not target.is_relative_to(root_resolved):
        raise PermissionError(f"path escapes workspace root: {rel}")
    return target


class FsReadTool(BaseTool):
    args_model = FsReadArgs

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.spec = ToolSpec(
            name="fs_read",
            description="Read a text file under the workspace root",
            is_write=False,
            timeout_s=2.0,
            max_retries=0,
        )

    def execute(self, args: BaseModel, *, idempotency_key: str | None = None) -> Any:
        assert isinstance(args, FsReadArgs)
        path = _resolve(self.root, args.path)
        if not path.exists():
            raise FileNotFoundError(f"missing file: {args.path}")
        return {"path": args.path, "content": path.read_text(encoding="utf-8")}


class FsWriteTool(BaseTool):
    args_model = FsWriteArgs

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.spec = ToolSpec(
            name="fs_write",
            description="Write a text file under the workspace root (idempotent by key)",
            is_write=True,
            timeout_s=2.0,
            max_retries=1,
            retry_on_error=True,
        )

    def execute(self, args: BaseModel, *, idempotency_key: str | None = None) -> Any:
        assert isinstance(args, FsWriteArgs)
        path = _resolve(self.root, args.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args.content, encoding="utf-8")
        return {
            "path": args.path,
            "bytes_written": len(args.content.encode("utf-8")),
            "idempotency_key": idempotency_key,
        }
