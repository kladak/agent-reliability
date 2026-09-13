"""Simple allowlist / path policy for negative safety tests."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PolicyDecision(BaseModel):
    allowed: bool
    reason: str = ""


class PolicyGate(BaseModel):
    """Block write tools targeting forbidden path prefixes."""

    blocked_write_prefixes: list[str] = Field(
        default_factory=lambda: ["secrets/", "../", "/etc/", "/sys/"]
    )
    # If True, any tool not in allowlist_tools is denied when allowlist is non-empty
    allowlist_tools: list[str] = Field(default_factory=list)

    def check(self, tool_name: str, args: dict) -> PolicyDecision:
        if self.allowlist_tools and tool_name not in self.allowlist_tools:
            return PolicyDecision(
                allowed=False,
                reason=f"tool not in allowlist: {tool_name}",
            )
        if tool_name in {"fs_write"}:
            path = str(args.get("path", ""))
            for prefix in self.blocked_write_prefixes:
                if path.startswith(prefix) or prefix in path:
                    return PolicyDecision(
                        allowed=False,
                        reason=f"blocked write path matching '{prefix}': {path}",
                    )
        return PolicyDecision(allowed=True)
