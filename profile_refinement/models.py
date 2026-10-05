"""Bounded ephemeral proposal/review contracts, separate from durable authority."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_CHANGES = 20
MAX_SOURCES = 60
MAX_CONTEXT_CHARS = 24_000
Category = Literal[
    "skills", "interests", "values", "goals", "strengths", "development_areas", "career_preferences",
    "education", "work_experience", "projects", "tools", "domain_knowledge", "achievements",
    "certifications", "professional_qualifications", "research", "leadership", "collaboration",
    "languages", "role_interests", "industry_interests", "location_preferences",
    "work_style_preferences", "constraints", "transition_intent", "uncertainties", "other_evidence",
]
Origin = Literal["explicit_user_input", "explicit_user_edit", "clarification_answer", "resume_evidence",
                 "confirmed_profile", "confirmed_memory", "model_inference"]
Ref = Annotated[str, Field(strict=True, pattern=r"^(?:pf|rs|an|cu|mm)_[0-9]{3}$")]
Refs = Annotated[tuple[Ref, ...], Field(min_length=1, max_length=8)]
Text = Annotated[str, Field(strict=True, min_length=1, max_length=240)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True,
                              revalidate_instances="always")


class Value(Contract):
    label: str = Field(strict=True, min_length=1, max_length=160)
    details: tuple[Text, ...] = Field(default=(), max_length=4)
    level: str | None = Field(default=None, strict=True, max_length=60)
    goal_type: Literal["career_goal", "project_goal", "learning_goal"] | None = None
    organization: str | None = Field(default=None, strict=True, max_length=160)
    time_range: str | None = Field(default=None, strict=True, max_length=80)


class ChangeType(str, Enum):
    UNCHANGED = "UNCHANGED"
    ADD = "ADD"
    UPDATE = "UPDATE"
    KEEP_OLD = "KEEP_OLD"
    REMOVE = "REMOVE"
    UNCERTAIN = "UNCERTAIN"
    CONFLICT = "CONFLICT_REQUIRES_REVIEW"


class Resolution(str, Enum):
    PENDING = "PENDING"
    CONFIRM = "CONFIRM"
    EDIT = "EDIT"
    KEEP_OLD = "KEEP_OLD"
    REJECT = "REJECT"
    UNCERTAIN = "UNCERTAIN"


class Status(str, Enum):
    IDLE = "IDLE"
    DRAFT = "DRAFT"
    REVIEWING = "REVIEWING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    NO_MATERIAL_CHANGE = "NO_MATERIAL_CHANGE"
    INVALID_DRAFT = "INVALID_DRAFT"
    STALE_DRAFT = "STALE_DRAFT"
    INVALID_REFERENCE = "INVALID_REFERENCE"
    PROFILE_VERSION_CONFLICT = "PROFILE_VERSION_CONFLICT"
    PROFILE_CONFIRMATION_FAILED = "PROFILE_CONFIRMATION_FAILED"
    MEMORY_SIDE_EFFECT_FAILED = "MEMORY_SIDE_EFFECT_FAILED"
    OWNER_SCOPE_MISMATCH = "OWNER_SCOPE_MISMATCH"
    CONVERSATION_NOT_FOUND = "CONVERSATION_NOT_FOUND"
    PROVIDER_FAILED = "PROVIDER_FAILED"


class Proposal(Contract):
    category: Category
    target_id: str | None = Field(strict=True, max_length=120)
    change_type: ChangeType
    proposed_value: Value | None = Field(repr=False)
    source_refs: Refs
    reason_summary: Literal["new_supported_evidence", "current_user_update", "clarification_update",
                            "source_conflict", "uncertainty_preserved", "same_understanding"]
    uncertainty: Literal["none", "unknown", "explicit_uncertainty"]


class RefinementOutput(Contract):
    outcome: Literal["CHANGES", "NO_MATERIAL_CHANGE"]
    changes: tuple[Proposal, ...] = Field(max_length=MAX_CHANGES, repr=False)

    @model_validator(mode="after")
    def coherent_outcome(self):
        if (self.outcome == "NO_MATERIAL_CHANGE") != (not self.changes):
            raise ValueError("INVALID_DRAFT")
        return self


class Source(Contract):
    ref: Ref
    origin: Origin
    category: str = Field(max_length=60)
    text: str = Field(max_length=800, repr=False)
    value: Value | None = Field(default=None, repr=False)
    target_id: str | None = Field(default=None, max_length=120)
    uncertainty: bool = Field(default=False, strict=True)
    uncertainty_status: Literal["none", "unknown", "explicit_uncertainty"] = "none"
    explicit_goal: bool = Field(default=False, strict=True)
    origin_refs: tuple[str, ...] = Field(default=(), exclude=True, repr=False, max_length=8)


class Binding(Contract):
    owner_scope_id: str = Field(repr=False)
    conversation_id: str = Field(repr=False)
    subject_id: str = Field(repr=False)
    base_profile_id: str | None = Field(repr=False)
    base_profile_version: int | None = Field(ge=1)
    base_profile_fingerprint: str
    resume_source_id: str
    resume_evidence_fingerprint: str
    clarification_state_version: int = Field(ge=0)
    clarification_fingerprint: str
    current_statement_fingerprint: str


class ProfileRefinementContext(Contract):
    sources: tuple[Source, ...] = Field(max_length=MAX_SOURCES, repr=False)
    partial: bool = Field(strict=True)


class ProfileFieldChange(Contract):
    change_id: str
    category: Category
    target_id: str
    change_type: ChangeType
    old_value: Value | None = Field(repr=False)
    proposed_value: Value | None = Field(repr=False)
    source_refs: Refs
    reason_summary: str
    uncertainty: Literal["none", "unknown", "explicit_uncertainty"]
    conflict_state: Literal["none", "requires_review"]
    user_resolution: Resolution = Resolution.PENDING
    edited_value: Value | None = Field(default=None, repr=False)


class ProfileRefinementDraft(Contract):
    draft_id: str
    binding: Binding = Field(repr=False)
    profile_id: str = Field(repr=False)
    proposed_profile_version: int = Field(ge=1)
    changes: tuple[ProfileFieldChange, ...] = Field(max_length=MAX_CHANGES, repr=False)
    created_at: datetime
    status: Status
    draft_fingerprint: str


class ReviewToken(Contract):
    draft_id: str
    draft_fingerprint: str
    owner_scope_id: str = Field(repr=False)
    conversation_id: str = Field(repr=False)


class RefinementError(ValueError):
    def __init__(self, code: Status | str):
        self.code = Status(code)
        super().__init__(self.code.value)
