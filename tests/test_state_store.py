"""State store corruption taxonomy."""

from __future__ import annotations

import uuid
from pathlib import Path

from agent_reliability.runtime import InjectedCrash, MockAgentRuntime, StateStore
from agent_reliability.runtime.state_store import StateCorruptionError
from agent_reliability.tools import FsWriteTool, ToolRouter


def test_corrupt_checkpoint_raises_state_corruption_error(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state")
    run_id = "corrupt-me"
    path = store._path(run_id)
    path.write_text("{not valid checkpoint json", encoding="utf-8")

    try:
        store.load(run_id)
        assert False, "expected StateCorruptionError"
    except StateCorruptionError as exc:
        assert "corrupt checkpoint" in str(exc)


def test_resume_corrupt_checkpoint_maps_to_taxonomy(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = StateStore(workspace / "state")
    run_id = str(uuid.uuid4())
    store._path(run_id).write_text('{"run_id": "x"}', encoding="utf-8")  # missing fields

    router = ToolRouter([FsWriteTool(workspace)], run_id=run_id)
    agent = MockAgentRuntime(router, state_store=store)
    outcome = agent.run(
        [],
        run_id=run_id,
        resume=True,
    )
    assert not outcome.ok
    assert outcome.failure_class == "state_corruption"
    assert "corrupt checkpoint" in (outcome.error or "")
