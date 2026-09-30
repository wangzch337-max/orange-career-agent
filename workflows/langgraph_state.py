"""Explicit, checkpoint-safe contracts for the Phase 6 orchestration layer."""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator
from typing_extensions import TypedDict


class GraphWorkflowStatus(str, Enum):
    RUNNING = "running"
    WAITING_FOR_HUMAN = "waiting_for_human"
    COMPLETED = "completed"
    FAILED = "failed"


class ProfileReviewAction(str, Enum):
    CONFIRM = "confirm"
    REVISE = "revise"


class ProfileReviewDecision(BaseModel):
    """The only human command accepted by the profile-review interrupt."""

    model_config = ConfigDict(extra="forbid")

    action: ProfileReviewAction
    education_summary: Optional[str] = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_revision_payload(self) -> "ProfileReviewDecision":
        if self.action == ProfileReviewAction.REVISE and self.education_summary is None:
            raise ValueError("revise requires education_summary")
        if self.action == ProfileReviewAction.CONFIRM and self.education_summary is not None:
            raise ValueError("confirm does not accept profile changes")
        return self

    def revision_changes(self) -> Dict[str, object]:
        if self.action != ProfileReviewAction.REVISE:
            return {}
        return {"education_summary": self.education_summary}


class GraphErrorCategory(str, Enum):
    PROVIDER_FAILURE = "provider_failure"
    VALIDATION_FAILURE = "validation_failure"
    UNEXPECTED_FAILURE = "unexpected_failure"


class SafeGraphError(BaseModel):
    """Sanitized failure state with no provider payload or private evidence."""

    model_config = ConfigDict(extra="forbid")

    category: GraphErrorCategory
    node_name: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: bool = False


class OrangeGraphState(TypedDict):
    """Minimal JSON-compatible execution state persisted by LangGraph."""

    workflow_id: str
    subject_id: str
    workflow_status: str
    checkpoint_mode: str
    selected_job_ids: List[str]
    profile: Optional[Dict[str, JsonValue]]
    current_profile_ref: Optional[Dict[str, JsonValue]]
    profile_uncertainties: List[Dict[str, JsonValue]]
    clarification_questions: List[Dict[str, JsonValue]]
    self_discovery_metadata: Dict[str, JsonValue]
    job_records: List[Dict[str, JsonValue]]
    job_intelligence: List[Dict[str, JsonValue]]
    match_results: List[Dict[str, JsonValue]]
    report: Optional[Dict[str, JsonValue]]
    graph_events: List[Dict[str, JsonValue]]
    safe_error: Optional[Dict[str, JsonValue]]
    review_outcome: Optional[str]
    self_discovery_call_count: int


class UnknownWorkflowError(RuntimeError):
    """Raised when a resume request does not target a waiting checkpoint."""
