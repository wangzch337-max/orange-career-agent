"""Independent D.5 contracts: no job qualifications, scores, actions or storage."""

from enum import Enum
from typing import Literal
from pydantic import Field, model_validator
from career_reality.models import Strict, Text, Authority


class Relation(str, Enum):
    DIRECT = "DIRECTLY_SUPPORTED"
    PARTIAL = "RELATED_BUT_PARTIAL"
    UNKNOWN = "UNKNOWN"
    TENSION = "TENSION"
    NA = "NOT_APPLICABLE"


class UserEvidence(Strict):
    evidence_id: str
    text: Text = Field(repr=False)
    source_type: str
    source_name: str


class UserSignal(Strict):
    signal_id: str
    category: str
    label: Text = Field(repr=False)
    scope: tuple[str, ...] = Field(repr=False)
    source_type: str
    inference_type: str
    origins: tuple[str, ...]
    uncertainty: str
    eligible: bool
    evidence_ids: tuple[str, ...]


class UserProjection(Strict):
    profile_id: str
    profile_version: int
    profile_fingerprint: str
    partial: bool
    signals: tuple[UserSignal, ...] = Field(repr=False)
    evidence: tuple[UserEvidence, ...] = Field(repr=False)


class WorkSignal(Strict):
    signal_id: str
    field: str
    label: Text = Field(repr=False)
    authority: Authority
    evidence_ids: tuple[str, ...]


class WorkEvidence(Strict):
    evidence_id: str
    text: Text = Field(repr=False)
    source_type: Literal["public_synthetic_curated"]
    membership_refs: tuple[str, str]


class WorkProjection(Strict):
    projection_version: Literal["d5.work@v1"] = "d5.work@v1"
    role_id: str
    role_label: Text
    source_id: str
    source_version: int
    source_fingerprint: str
    scope: Text
    variation: tuple[str, ...]
    unknowns: tuple[str, ...]
    signals: tuple[WorkSignal, ...] = Field(repr=False)
    evidence: tuple[WorkEvidence, ...] = Field(repr=False)


class Context(Strict):
    user: UserProjection = Field(repr=False)
    work: WorkProjection = Field(repr=False)

    # Read-only structural view for the existing ownership resolver. This is
    # NOT a JobRecord/JobIntelligenceRecord conversion or legacy workflow input.
    @property
    def profile_signals(self): return self.user.signals
    @property
    def profile_evidence(self): return self.user.evidence
    @property
    def job_signals(self): return self.work.signals
    @property
    def job_evidence(self): return self.work.evidence


class Candidate(Strict):
    relation_type: Relation
    user_signal_ids: tuple[str, ...] = Field(max_length=1)
    work_signal_ids: tuple[str, ...] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def sides(self):
        if self.relation_type != Relation.UNKNOWN and not self.user_signal_ids:
            raise ValueError("D5_BILATERAL_REFERENCE_REQUIRED")
        if len(set(self.user_signal_ids)) != len(self.user_signal_ids):
            raise ValueError("D5_DUPLICATE_REFERENCE")
        return self


class Extraction(Strict):
    relations: tuple[Candidate, ...] = Field(min_length=1, max_length=40)


class Relationship(Strict):
    relationship_id: str
    relation_type: Relation
    user_signal_ids: tuple[str, ...]
    user_evidence_ids: tuple[str, ...]
    work_signal_ids: tuple[str, ...]
    work_evidence_ids: tuple[str, ...]
    reason: Text
    limitations: tuple[str, ...]
    uncertainty: Literal["none", "limited_scope", "insufficient_evidence"]
    user_sources: tuple[str, ...]
    profile_version: int
    role_id: str
    source_id: str
    source_version: int
    source_fingerprint: str


class Result(Strict):
    profile_id: str
    profile_version: int
    profile_fingerprint: str
    role_id: str
    projection_version: str
    relationships: tuple[Relationship, ...] = Field(repr=False)


class Binding(Strict):
    owner: str
    subject: str
    thread: str
    request_id: str
    generation: int
    profile_id: str
    profile_version: int
    profile_fingerprint: str
    role_id: str
    source_id: str
    source_version: int
    source_fingerprint: str
    projection_version: str
    parent_generation: int
    parent_fingerprint: str


class Token(Strict):
    owner: str
    subject: str
    thread: str
    request_id: str
    generation: int
    turn: int


class Event(Strict):
    request_id: str | None
    profile_version: int
    role_id: str | None
    projection_version: str
    relation_counts: dict[Relation, int]
    status: Literal["active", "stale", "unavailable", "invalid", "limited"]
    duration_ms: int
