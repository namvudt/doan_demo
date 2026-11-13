"""Compatibility imports for the validated review agents."""

from agents.review import (
    AGGREGATOR_SYSTEM_PROMPT,
    JUDGE_SYSTEM_PROMPT,
    AggregatorAgent,
    JudgeAgent,
)

__all__ = ["AggregatorAgent", "JudgeAgent", "AGGREGATOR_SYSTEM_PROMPT", "JUDGE_SYSTEM_PROMPT"]
