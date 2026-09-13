"""Eval package. Import run_offline from agent_reliability.eval.runner."""

__all__ = ["run_offline"]


def __getattr__(name: str):
    if name == "run_offline":
        from agent_reliability.eval.runner import run_offline

        return run_offline
    raise AttributeError(name)
