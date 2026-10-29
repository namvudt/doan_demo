"""Validated LLM boundaries and serializable workflow results."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StrictBool, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class FocusDirectives(Contract):
    visual_focus: str = ""
    knowledge_focus: str = ""
    generation_focus: str = ""


class ExecutionPlan(Contract):
    query_intent: str = ""
    identified_monument: str = ""
    task_categories: list[str] = Field(default_factory=list)
    selected_agents: list[Literal["visual_agent", "knowledge_agent", "tool_gen_agent"]]
    plan_reasoning: str = ""
    focus_directives: FocusDirectives = Field(default_factory=FocusDirectives)

    @model_validator(mode="after")
    def normalize_agents(self):
        self.selected_agents = list(dict.fromkeys(["visual_agent", *self.selected_agents]))
        return self


class SourceRecord(Contract):
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: HttpUrl
    type: Literal["wiki", "web", "maps"]
    snippet: str = ""
    retrieved_at: str | None = None
    revision_id: str | None = None


class Criterion(Contract):
    passed: StrictBool
    score: float = Field(strict=True, ge=0, le=10)
    critique: str


class Criteria(Contract):
    visual_fidelity: Criterion
    relevance: Criterion
    cultural_tone: Criterion


class JudgeOutput(Contract):
    criteria_evaluation: Criteria
    overall_status: Literal["APPROVED", "REFINED_BY_JUDGE", "INSUFFICIENT_EVIDENCE"]
    hallucination_detected: StrictBool
    hallucination_notes: str
    refinement_summary: str = ""
    final_response: str = Field(min_length=1)
    cited_source_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_approval(self):
        if self.overall_status == "APPROVED" and (
            self.hallucination_detected
            or not all(
                value.passed
                for value in (
                    self.criteria_evaluation.visual_fidelity,
                    self.criteria_evaluation.relevance,
                    self.criteria_evaluation.cultural_tone,
                )
            )
        ):
            raise ValueError("APPROVED contradicts assessment")
        return self


class RunResult(Contract):
    run_id: str
    fingerprint: str
    query: str
    audience: Literal["tourist", "student"]
    status: Literal["reviewed", "unverified", "insufficient_evidence", "out_of_scope", "failed"]
    final_response: str | None = None
    draft_response: str | None = None
    plan: dict[str, Any] = Field(default_factory=dict)
    expert_results: dict[str, Any] = Field(default_factory=dict)
    judge_report: dict[str, Any] = Field(default_factory=dict)
    errors: list[dict[str, str]] = Field(default_factory=list)
    node_metadata: dict[str, Any] = Field(default_factory=dict)
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    calls: list[dict[str, Any]] = Field(default_factory=list)
    duration: float


class RunEvent(Contract):
    kind: Literal["node", "completed"]
    node: str
    result: RunResult | None = None
