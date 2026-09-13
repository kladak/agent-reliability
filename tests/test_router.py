from pathlib import Path

from agent_reliability.tools import FlakyEchoTool, FsReadTool, FsWriteTool, ToolRouter


def test_schema_rejection(tmp_path: Path) -> None:
    router = ToolRouter([FsReadTool(tmp_path)])
    result = router.call("fs_read", {})  # missing path
    assert not result.ok
    assert result.failure_class == "tool_schema_error"


def test_unknown_tool(tmp_path: Path) -> None:
    router = ToolRouter([FsReadTool(tmp_path)])
    result = router.call("not_a_tool", {})
    assert not result.ok
    assert result.failure_class == "tool_schema_error"


def test_write_idempotency(tmp_path: Path) -> None:
    router = ToolRouter([FsWriteTool(tmp_path)])
    r1 = router.call(
        "fs_write",
        {"path": "x.txt", "content": "hello"},
        idempotency_key="k1",
    )
    r2 = router.call(
        "fs_write",
        {"path": "x.txt", "content": "hello"},
        idempotency_key="k1",
    )
    assert r1.ok and r2.ok
    assert r2.cached is True
    assert (tmp_path / "x.txt").read_text() == "hello"


def test_flaky_echo_retries(tmp_path: Path) -> None:
    FlakyEchoTool.reset()
    tool = FlakyEchoTool(max_retries=5)
    router = ToolRouter([tool])
    result = router.call("flaky_echo", {"message": "hi", "fail_times": 2})
    assert result.ok
    assert result.attempt == 3  # 2 failures + 1 success
