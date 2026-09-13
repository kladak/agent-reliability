"""Eval package. Import run_offline from agent_reliability.eval.runner."""

__all__ = ["run_offline", "compare_reports"]


def __getattr__(name: str):
    if name == "run_offline":
        from agent_reliability.eval.runner import run_offline

        return run_offline
    if name == "compare_reports":
        from agent_reliability.eval.compare import compare_reports

        return compare_reports
    raise AttributeError(name)
