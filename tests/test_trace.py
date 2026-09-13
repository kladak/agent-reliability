from pathlib import Path

from agent_reliability.observe import EventType, TraceEvent, TraceSink, read_trace


def test_trace_sink_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    with TraceSink(path) as sink:
        sink.emit(
            TraceEvent(
                run_id="r1",
                event_type=EventType.RUN_START,
                metadata={"k": "v"},
            )
        )
        sink.emit(
            TraceEvent(
                run_id="r1",
                event_type=EventType.TOOL_CALL,
                tool_name="fs_read",
                args={"path": "a.txt"},
            )
        )

    events = read_trace(path)
    assert len(events) == 2
    assert events[0].event_type == EventType.RUN_START
    assert events[1].tool_name == "fs_read"
