"""Failure taxonomy for agent runs (SPEC §6)."""

from enum import Enum


class FailureClass(str, Enum):
    TOOL_SCHEMA_ERROR = "tool_schema_error"
    TOOL_EXECUTION_ERROR = "tool_execution_error"
    TIMEOUT = "timeout"
    RETRY_EXHAUSTED = "retry_exhausted"
    INVALID_STRUCTURED_OUTPUT = "invalid_structured_output"
    TASK_ASSERTION_FAILED = "task_assertion_failed"
    POLICY_VIOLATION = "policy_violation"
    BUDGET_EXCEEDED = "budget_exceeded"
    STATE_CORRUPTION = "state_corruption"
    UNKNOWN = "unknown"
