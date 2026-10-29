"""Opt-in single-provider smoke test, excluded from pytest collection."""

import os

from core.gateway import LLMManager


def main():
    if os.getenv("RUN_LIVE_SMOKE") != "1":
        print("Set RUN_LIVE_SMOKE=1 explicitly to perform a billable model call.")
        return 2
    manager = LLMManager()
    try:
        answer, meta = manager.call_llm("Reply with OK.", agent_role="visual")
        print({"answer": answer, "provider": meta["actual_provider"], "model": meta["model_used"]})
        return 0
    finally:
        manager.close()


if __name__ == "__main__":
    raise SystemExit(main())
