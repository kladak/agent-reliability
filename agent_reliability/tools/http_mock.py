"""In-process mock HTTP tool with a request journal for graders."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agent_reliability.tools.base import BaseTool, ToolSpec


class HttpGetArgs(BaseModel):
    path: str = Field(..., description="API path, e.g. /inventory/a")


class MockHttpTool(BaseTool):
    """Serve fixture responses from an in-memory route map; record every call."""

    args_model = HttpGetArgs

    def __init__(self, routes: dict[str, Any], *, timeout_s: float = 2.0) -> None:
        self.routes = dict(routes)
        self.journal: list[dict[str, Any]] = []
        self.spec = ToolSpec(
            name="http_get",
            description="GET a mock HTTP API path and return JSON-like payload",
            is_write=False,
            timeout_s=timeout_s,
            max_retries=1,
            retry_on_error=True,
        )

    def execute(self, args: BaseModel, *, idempotency_key: str | None = None) -> Any:
        assert isinstance(args, HttpGetArgs)
        self.journal.append({"method": "GET", "path": args.path})
        if args.path not in self.routes:
            raise LookupError(f"404 not found: {args.path}")
        return {"path": args.path, "status": 200, "body": self.routes[args.path]}
