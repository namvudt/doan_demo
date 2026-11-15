from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.evidence import (
    CheckedClaim,
    Clarification,
    Evidence,
    LocationHint,
    RecognitionResult,
    Region,
    RequestedSlot,
)
from core.schemas import SourceRecord


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionCreate(Contract):
    label: str = Field(default="Swagger test", min_length=1, max_length=80)


class SessionCreated(Contract):
    session_id: UUID
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime


class SessionView(Contract):
    session_id: UUID
    label: str
    expires_at: datetime


class AssetView(Contract):
    asset_id: UUID
    sha256: str
    size_bytes: int
    width: int
    height: int
    media_type: str = "image/png"
    created_at: datetime
    content_url: str


class RunCreate(Contract):
    location_hint: LocationHint | None = Field(
        default=None, description="Optional unverified location hint; not historical ground truth."
    )
    focus_box: tuple[float, float, float, float] | None = None
    asset_id: UUID
    question: str = Field(
        min_length=1,
        max_length=4000,
        examples=["Những chi tiết kiến trúc nào nhìn thấy rõ trong ảnh?"],
    )
    audience: Literal["tourist", "student"] = "tourist"
    profile: Literal["default"] = "default"
    parent_run_id: UUID | None = None

    @field_validator("question")
    @classmethod
    def meaningful_question(cls, value):
        if not value.strip():
            raise ValueError("Question must not be blank")
        return value.strip()

    @field_validator("focus_box")
    @classmethod
    def region_is_valid(cls, value):
        if value is not None:
            Region(box=value)
        return value


class ClarificationBody(Contract):
    selected_candidate: str | None = Field(default=None, min_length=1, max_length=200)
    clarification_id: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=1)
    answer: str = Field(default="", max_length=2000)
    asset_id: UUID | None = None
    focus_box: tuple[float, float, float, float] | None = None

    @field_validator("focus_box")
    @classmethod
    def region_is_valid(cls, value):
        if value is not None:
            Region(box=value)
        return value


class EvidenceView(Contract):
    recognition: RecognitionResult | None = None
    location_hint: LocationHint | None = None
    run_id: UUID
    result_schema_version: int
    answer_status: str | None
    requested_slots: list[RequestedSlot]
    evidence: list[Evidence]
    claims: list[CheckedClaim]
    candidates: list[dict]
    image_quality: dict
    regions: list[dict]
    tool_calls: list[dict]


class ClarificationView(Contract):
    run_id: UUID
    execution_status: str
    clarification: Clarification | None
    continuation_run_id: UUID | None


class RunView(Contract):
    run_id: UUID
    run_kind: Literal["full", "review", "clarification"] = "full"
    request_id: str | None = None
    trace_id: UUID | None = None
    asset_id: UUID
    parent_run_id: UUID | None
    question: str
    audience: str
    model_mode: Literal["live", "demo"]
    execution_status: Literal[
        "queued",
        "running",
        "cancel_requested",
        "succeeded",
        "failed",
        "cancelled",
        "awaiting_input",
    ]
    result_status: str | None
    bookmarked: bool
    event_count: int
    error_type: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    events_url: str
    result_url: str


class RunPage(Contract):
    items: list[RunView]
    total: int
    limit: int
    offset: int


class EventView(Contract):
    sequence: int
    event: str
    data: dict[str, Any]
    created_at: datetime


class EventPage(Contract):
    run_id: UUID
    items: list[EventView]
    next_after: int
    terminal: bool


class ResultView(Contract):
    recognition: RecognitionResult | None = None
    location_hint: LocationHint | None = None
    result_schema_version: int = 1
    answer_status: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    requested_slots: list[dict[str, Any]] = Field(default_factory=list)
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    image_quality: dict[str, Any] = Field(default_factory=dict)
    regions: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    clarification: dict[str, Any] | None = None
    run_id: UUID
    parent_run_id: UUID | None = None
    run_kind: Literal["full", "review", "clarification"] = "full"
    reused_nodes: list[str] = Field(default_factory=list)
    upstream_config_hash: str | None = None
    model_mode: Literal["live", "demo"]
    status: str
    question: str
    audience: str
    final_response: str | None
    sources: list[RetrievedSource]
    plan: dict[str, Any]
    review: dict[str, Any]
    errors: list[dict[str, Any]]
    duration: float
    usage: dict[str, Any]
    intermediate: dict[str, Any] | None = None


class FeedbackBody(Contract):
    rating: Literal["helpful", "needs_review", "unrated"] = "unrated"
    note: str = Field(default="", max_length=1500)


class BookmarkBody(Contract):
    saved: bool


class ErrorDetail(Contract):
    code: str
    message: str
    request_id: str
    details: dict[str, Any] | None = None


class PreflightBody(Contract):
    roles: list[
        Literal["coordinator", "visual", "knowledge", "generation", "aggregator", "judge"]
    ] = Field(
        default_factory=lambda: ["coordinator", "visual", "aggregator", "judge"],
        min_length=1,
        max_length=6,
    )
    force: bool = False


class RoleReadiness(Contract):
    role: str
    provider: str
    model: str
    ready: bool
    cached: bool
    checked_at: float | None = None
    error_type: str | None = None
    error_code: str | None = None
    error_category: str | None = None
    retryable: bool = False
    provider_status_code: int | None = None
    provider_reason: str | None = None


class PreflightView(Contract):
    ready: bool
    roles: list[RoleReadiness]
    scope: str
    generation_verified: bool = False


class ErrorResponse(Contract):
    error: ErrorDetail


class ProfileView(Contract):
    id: str
    workflow_version: str
    generation_enabled: bool


class CapabilitiesView(Contract):
    accuracy: dict[str, Any] = Field(default_factory=dict)
    api_version: str
    config_hash: str
    model_mode: Literal["live", "demo"]
    model_configured: bool
    missing_roles: list[str]
    max_upload_bytes: int
    max_image_pixels: int
    max_question_characters: int
    profiles: list[ProfileView]
    session_bootstrap_required: bool


class RetrievedSource(SourceRecord):
    number: int
    cited: bool


class SourcesView(Contract):
    run_id: UUID
    items: list[RetrievedSource]


class StepsView(Contract):
    run_id: UUID
    items: dict[str, dict[str, Any]]


class MetricsView(Contract):
    run_id: UUID
    model_mode: Literal["live", "demo"]
    duration: float | None
    usage: dict[str, Any]
    calls: list[dict[str, Any]]
    workflow_version: str
    config_hash: str


class SampleView(Contract):
    sample_id: str
    title: str


class SamplesView(Contract):
    items: list[SampleView]


class StageDefinition(Contract):
    id: str
    title: str
    description: str


class WorkflowView(Contract):
    version: str
    stages: list[StageDefinition]
    diagram: str
