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


def test_http_mock_journal(tmp_path: Path) -> None:
    from agent_reliability.tools import MockHttpTool

    http = MockHttpTool({"/x": [1, 2]})
    router = ToolRouter([http])
    result = router.call("http_get", {"path": "/x"})
    assert result.ok
    assert http.journal == [{"method": "GET", "path": "/x"}]


def test_fs_resolve_rejects_parent_escape(tmp_path: Path) -> None:
    """Sibling-prefix escape (../ws-evil) must raise without relying on PolicyGate."""
    import pytest

    workspace = tmp_path / "ws"
    workspace.mkdir()
    evil = tmp_path / "ws-evil"
    evil.mkdir()

    tool = FsWriteTool(workspace)
    with pytest.raises(PermissionError, match="escapes workspace root"):
        # Call execute directly, bypassing PolicyGate and the router.
        from agent_reliability.tools.filesystem import FsWriteArgs

        tool.execute(FsWriteArgs(path="../ws-evil/pwned.txt", content="pwned"))

    assert not (evil / "pwned.txt").exists()


def test_fs_resolve_rejects_absolute_path(tmp_path: Path) -> None:
    import pytest
    from agent_reliability.tools.filesystem import FsReadArgs

    tool = FsReadTool(tmp_path / "ws")
    (tmp_path / "ws").mkdir()
    with pytest.raises(PermissionError, match="escapes workspace root"):
        tool.execute(FsReadArgs(path="/etc/passwd"))
