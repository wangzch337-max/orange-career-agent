"""Strict diagnostic envelope with no arbitrary content-bearing fields."""

from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from career_runtime.diagnostics import RuntimeDiagnostic

from data.models import EventType
from observability.redaction import safe_id, validate_metadata, validate_counts, UnsafeDiagnosticMetadata


class DiagnosticComponent(str, Enum):
    SYSTEM = "SYSTEM"
    WORKFLOW = "WORKFLOW"
    SELF_DISCOVERY = "SELF_DISCOVERY"
    JOB_INTELLIGENCE = "JOB_INTELLIGENCE"
    MATCH_INSIGHT = "MATCH_INSIGHT"
    REPORT = "REPORT"
    MEMORY = "MEMORY"
    MEMORY_RETRIEVAL = "MEMORY_RETRIEVAL"
    MEMORY_CONTEXT = "MEMORY_CONTEXT"
    EMBEDDING = "EMBEDDING"
    VECTOR_INDEX = "VECTOR_INDEX"
    CONVERSATION = "CONVERSATION"
    PROFILE_REFINEMENT = "PROFILE_REFINEMENT"
    ROLE_EXPLORATION = "ROLE_EXPLORATION"
    ACTION = "ACTION"
    EVALUATION = "EVALUATION"
    UI = "UI"
    PROVIDER = "PROVIDER"


class DiagnosticStatus(str, Enum):
    STARTED = "STARTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    WAITING = "WAITING"
    SKIPPED = "SKIPPED"
    INTERRUPTED = "INTERRUPTED"


OPERATIONS = {item.value for item in EventType} | {
    "workflow_start", "workflow_resume", "self_discovery_run", "job_intelligence_run", "match_run",
    "memory_retrieve", "memory_context_build", "memory_change_resolve", "memory_change_detect", "profile_refine",
    "profile_refine_confirm", "role_recall", "action_review", "action_status", "guided_answer", "provider_call",
    "embedding_batch", "evaluation_scenario_run", "evaluation_check", "diagnostic_rejected", "vector_rebuild",
    "memory_confirm", "memory_archive", "memory_supersede", "memory_purge", "memory_candidate",
    "vector_sync", "memory_retrieval_sources",
    "agent_turn", "agent_plan", "agent_tool", "agent_response",
}


def run_id():
    return f"diag_{uuid4().hex}"


class DiagnosticModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ObservabilityContext(DiagnosticModel):
    run_id: str = Field(pattern=r"^diag_[0-9a-f]{32}$")
    parent_event_id: str | None = Field(default=None, pattern=r"^evt_[0-9a-f]{32}$")
    workflow_id: str | None = None
    thread_id: str | None = None
    subject_id: str | None = None
    scenario_id: str | None = None

    @field_validator("workflow_id", "thread_id", "subject_id", "scenario_id")
    @classmethod
    def identifiers(cls, value):
        return safe_id(value) if value is not None else value


class DiagnosticEvent(ObservabilityContext):
    schema_version: Literal["orange.observability.v1"] = "orange.observability.v1"
    event_id: str = Field(default_factory=lambda: f"evt_{uuid4().hex}", pattern=r"^evt_[0-9a-f]{32}$")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sequence: int = Field(default=0, ge=0)
    component: DiagnosticComponent
    operation: str
    status: DiagnosticStatus
    started_at: datetime | None = None
    duration_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    correlation_ids: dict[str, str] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    safe_metadata: dict[str, str | int | float | bool | list[str] | None] = Field(default_factory=dict)
    error_category: Literal["validation_failure", "provider_failure", "unexpected_failure", "diagnostic_failure"] | None = None
    source_event_type: EventType | None = None
    agent_detail: RuntimeDiagnostic | None = None

    @model_validator(mode="after")
    def agent_detail_scope(self):
        if self.agent_detail is not None and self.operation not in {"agent_turn", "agent_plan", "agent_tool", "agent_response"}:
            raise ValueError("Agent detail is limited to runtime events.")
        return self

    @field_validator("timestamp", "started_at")
    @classmethod
    def aware_time(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Diagnostic time must be timezone-aware")
        return value

    @field_validator("operation")
    @classmethod
    def operation_allowlist(cls, value):
        if value not in OPERATIONS:
            raise ValueError("Unknown diagnostic operation")
        return value

    @field_validator("safe_metadata", mode="before")
    @classmethod
    def metadata_allowlist(cls, value):
        return validate_metadata(value)

    @field_validator("counts", mode="before")
    @classmethod
    def counts_allowlist(cls, value):
        return validate_counts(value)

    @field_validator("correlation_ids", mode="before")
    @classmethod
    def correlation_allowlist(cls, value):
        from observability.redaction import ID_KEYS
        if not isinstance(value, dict) or set(value) - ID_KEYS:
            raise UnsafeDiagnosticMetadata()
        return {key: safe_id(item) for key, item in value.items()}


class DiagnosticRunSummary(DiagnosticModel):
    run_id: str = Field(pattern=r"^diag_[0-9a-f]{32}$")
    status: DiagnosticStatus
    started_at: datetime | None
    duration_ms: float | None
    event_count: int
    component_counts: dict[DiagnosticComponent, int]
    failure_count: int
    warning_count: int
    workflow_status: Literal["running", "waiting_for_human", "completed", "failed"] | None
    provider_call_count: int
    memory_retrieval_count: int
    recording_failure_count: int


class DiagnosticTimelineEntry(DiagnosticModel):
    event_id: str
    component: DiagnosticComponent
    operation: str
    status: DiagnosticStatus
    duration_ms: float | None
