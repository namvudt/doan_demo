from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class RunView(Contract):
    run_id: UUID
    request_id: str | None = None
    trace_id: UUID | None = None
    asset_id: UUID
    parent_run_id: UUID | None
    question: str
    audience: str
    model_mode: Literal["live", "demo"]
    execution_status: Literal[
        "queued", "running", "cancel_requested", "succeeded", "failed", "cancelled"
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
    run_id: UUID
    model_mode: Literal["live", "demo"]
    status: str
    question: str
    audience: str
    final_response: str | None
    sources: list[RetrievedSource]
    plan: dict[str, Any]
    review: dict[str, Any]
    errors: list[dict[str, str]]
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


class ErrorResponse(Contract):
    error: ErrorDetail


class ProfileView(Contract):
    id: str
    workflow_version: str
    generation_enabled: bool


class CapabilitiesView(Contract):
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
