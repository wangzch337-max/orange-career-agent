"""Strict contracts for structured profile persistence and curated memory."""

from __future__ import annotations

import math
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4

from pydantic import Field, JsonValue, field_validator, model_validator

from data.models import BaseEvent, DomainModel, EvidenceSourceType, UserProfile, utc_now


class MemoryType(str, Enum):
    PROFILE_SIGNAL = "profile_signal"
    CAREER_PREFERENCE = "career_preference"
    GOAL = "goal"
    PROJECT_EVIDENCE = "project_evidence"
    COURSE_EVIDENCE = "course_evidence"
    USER_FEEDBACK = "user_feedback"
    CAREER_INSIGHT = "career_insight"


class MemoryStatus(str, Enum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class MemoryUseCase(str, Enum):
    PROFILE_REFINEMENT = "profile_refinement"
    ROLE_EXPLORATION = "role_exploration"
    CAREER_DIRECTION_DISCOVERY = "career_direction_discovery"


class MemoryRetrievalMode(str, Enum):
    HYBRID = "hybrid"


class MemoryConsumer(str, Enum):
    PROFILE_REFINEMENT_SERVICE = "profile_refinement_service"
    ROLE_MEMORY_CONTEXT_SERVICE = "role_memory_context_service"
    CAREER_DIRECTION_DISCOVERY_SERVICE = "career_direction_discovery_service"


class DimensionCardinality(str, Enum):
    SINGLE_VALUE = "single_value"
    MULTI_VALUE = "multi_value"


class SessionSignalPersistence(str, Enum):
    SESSION_ONLY = "session_only"
    PENDING_CONFIRMATION = "pending_confirmation"


class MemoryChangeChoice(str, Enum):
    UPDATE_LONG_TERM = "update_long_term"
    KEEP_BOTH = "keep_both"
    DEFER = "defer"
    UNCERTAIN = "uncertain"


class MemoryChangeStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DEFERRED = "deferred"
    UNCERTAIN = "uncertain"


class MemoryStatementKind(str, Enum):
    MEMORY_RECALL = "memory_recall"
    RELATED_HISTORY = "related_history"
    POST_MATCH_CONTEXT = "post_match_context"


class MemoryAuthorityLabel(str, Enum):
    CONFIRMED_HISTORICAL_MEMORY = "confirmed_historical_memory"


def new_subject_id() -> str:
    return f"subject_{uuid4().hex}"


def new_memory_id() -> str:
    return f"memory_{uuid4().hex}"


def _require_aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


class MemoryRecord(DomainModel):
    """Curated durable record; status expresses authority independently of relevance."""

    memory_id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    memory_type: MemoryType
    status: MemoryStatus
    content: str = Field(min_length=1, max_length=2000)
    source_type: EvidenceSourceType
    evidence_refs: List[str] = Field(default_factory=list)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    supersedes_memory_id: Optional[str] = None
    metadata: Dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("evidence_refs")
    @classmethod
    def normalize_evidence_refs(cls, value: List[str]) -> List[str]:
        if any(not item.strip() for item in value):
            raise ValueError("evidence_refs cannot contain empty IDs")
        return list(dict.fromkeys(value))

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_aware_timestamp(cls, value: datetime, info) -> datetime:
        return _require_aware(value, info.field_name)

    @model_validator(mode="after")
    def validate_identity_relationship(self) -> "MemoryRecord":
        if self.supersedes_memory_id == self.memory_id:
            raise ValueError("A memory cannot supersede itself")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        return self


class ProfileReference(DomainModel):
    subject_id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    version: int = Field(ge=1)


class ProfileSaveResult(DomainModel):
    profile: UserProfile
    reference: ProfileReference
    created: bool
    current: bool


class PurgeResult(DomainModel):
    subject_id: str = Field(min_length=1)
    profile_versions_deleted: int = Field(ge=0)
    current_pointer_deleted: int = Field(ge=0)
    memory_records_deleted: int = Field(ge=0)
    vector_records_deleted: int = Field(default=0, ge=0)
    vector_cleanup_required: bool = False


class MemoryRelevance(DomainModel):
    score: int = Field(ge=0)
    exact_phrase_match: bool = False
    matched_tokens: List[str] = Field(default_factory=list)


class MemoryRetrievalResult(DomainModel):
    memory: MemoryRecord
    relevance: MemoryRelevance


class EmbeddingVector(DomainModel):
    """Internal local vector plus immutable provider identity."""

    values: List[float]
    provider_name: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    dimension: int = Field(gt=0)
    normalization_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dimension(self) -> "EmbeddingVector":
        if len(self.values) != self.dimension:
            raise ValueError("Embedding vector length does not match its dimension.")
        if any(not math.isfinite(float(value)) for value in self.values):
            raise ValueError("Embedding vector values must be finite.")
        return self


class VectorIndexEntry(DomainModel):
    memory_id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    memory_type: MemoryType
    embedding_provider: str = Field(min_length=1)
    embedding_model_id: str = Field(min_length=1)
    embedding_dimension: int = Field(gt=0)
    content_hash: str = Field(min_length=64, max_length=64)
    indexed_at: datetime
    index_schema_version: int = Field(ge=1)
    embedding_normalization_version: str = Field(min_length=1)

    @field_validator("indexed_at")
    @classmethod
    def validate_indexed_at(cls, value: datetime) -> datetime:
        return _require_aware(value, "indexed_at")


class VectorSearchHit(DomainModel):
    entry: VectorIndexEntry
    distance: float = Field(ge=0.0)


class VectorIndexRebuildResult(DomainModel):
    subject_id: str = Field(min_length=1)
    cleared_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    indexed_count: int = Field(ge=0)


class SemanticMemoryRetrievalResult(DomainModel):
    memory: MemoryRecord
    semantic_rank: int = Field(ge=1)
    semantic_distance: float = Field(ge=0.0)
    embedding_provider: str = Field(min_length=1)
    embedding_model_id: str = Field(min_length=1)


class HybridMemoryRetrievalResult(DomainModel):
    memory: MemoryRecord
    lexical_rank: Optional[int] = Field(default=None, ge=1)
    semantic_rank: Optional[int] = Field(default=None, ge=1)
    fusion_rank: int = Field(ge=1)
    rrf_score: float = Field(gt=0.0)

    @model_validator(mode="after")
    def validate_retrieval_source(self) -> "HybridMemoryRetrievalResult":
        if self.lexical_rank is None and self.semantic_rank is None:
            raise ValueError("Hybrid result requires lexical or semantic provenance.")
        return self


class MemoryContextItem(DomainModel):
    memory_id: str = Field(min_length=1)
    memory_type: MemoryType
    status: MemoryStatus
    content: str = Field(min_length=1, max_length=2000)
    source_type: EvidenceSourceType
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    authority: str = Field(pattern="^active_confirmed$")
    lexical_rank: Optional[int] = Field(default=None, ge=1)
    semantic_rank: Optional[int] = Field(default=None, ge=1)
    fusion_rank: int = Field(ge=1)


class MemoryContext(DomainModel):
    subject_id: str = Field(min_length=1)
    items: List[MemoryContextItem]
    max_records: int = Field(ge=1)
    character_count: int = Field(ge=0)
    truncated: bool = False


class MemoryContextPolicy(DomainModel):
    """Deterministic allowlist and budget for one explicit consumer."""

    use_case: MemoryUseCase
    allowed_memory_types: List[MemoryType] = Field(min_length=1)
    retrieval_mode: MemoryRetrievalMode = MemoryRetrievalMode.HYBRID
    top_k: int = Field(ge=1, le=8)
    max_records: int = Field(ge=1, le=8)
    max_characters: int = Field(ge=1, le=6000)
    session_input_contributes: bool
    consumer: MemoryConsumer
    allow_memory_derived_statements: bool = True

    @model_validator(mode="after")
    def validate_budget(self) -> "MemoryContextPolicy":
        if self.max_records > self.top_k:
            raise ValueError("Memory context max_records cannot exceed top_k.")
        if len(self.allowed_memory_types) != len(set(self.allowed_memory_types)):
            raise ValueError("Memory policy types must be unique.")
        return self


class StructuredSessionSignal(DomainModel):
    signal_id: str = Field(min_length=1)
    dimension: str = Field(min_length=1)
    value: str = Field(min_length=1)
    display_label: str = Field(min_length=1)
    source: str = Field(pattern="^explicit_user_input$")
    session_order: int = Field(ge=1)
    observed_at: datetime = Field(default_factory=utc_now)
    persistence_state: SessionSignalPersistence = SessionSignalPersistence.SESSION_ONLY

    @field_validator("observed_at")
    @classmethod
    def validate_signal_time(cls, value: datetime) -> datetime:
        return _require_aware(value, "observed_at")


class MemoryChangeCandidate(DomainModel):
    """Session-only proposal; never an authoritative MemoryRecord."""

    candidate_id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    dimension: str = Field(min_length=1)
    previous_memory_refs: List[str] = Field(min_length=1)
    previous_values: List[str] = Field(min_length=1)
    current_session_value: str = Field(min_length=1)
    current_display_text: str = Field(min_length=1)
    change_kind: str = Field(pattern="^structured_same_dimension_change$")
    allowed_user_choices: List[MemoryChangeChoice] = Field(min_length=1)
    status: MemoryChangeStatus = MemoryChangeStatus.PENDING


class MemoryAwareStatement(DomainModel):
    statement_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    memory_refs: List[str] = Field(min_length=1)
    use_case: MemoryUseCase
    statement_kind: MemoryStatementKind
    authority_label: MemoryAuthorityLabel
    related_session_signal_id: Optional[str] = None

    @field_validator("memory_refs")
    @classmethod
    def normalize_memory_refs(cls, value: List[str]) -> List[str]:
        if any(not item.strip() for item in value):
            raise ValueError("memory_refs cannot contain empty IDs")
        return list(dict.fromkeys(value))


class ProfileRefinementContext(DomainModel):
    subject_id: str = Field(min_length=1)
    current_profile: UserProfile
    current_session_signal: StructuredSessionSignal
    memory_context: MemoryContext

    @model_validator(mode="after")
    def validate_subject(self) -> "ProfileRefinementContext":
        if self.memory_context.subject_id != self.subject_id:
            raise ValueError("Profile refinement context subject mismatch.")
        if not self.current_profile.confirmed:
            raise ValueError("Profile refinement requires a confirmed current profile.")
        return self


class ProfileRefinementResult(DomainModel):
    draft_profile: UserProfile
    memory_aware_statements: List[MemoryAwareStatement] = Field(default_factory=list)
    memory_refs: List[str] = Field(default_factory=list)
    current_input_is_newest: bool = True
    requires_profile_review: bool = True

    @model_validator(mode="after")
    def validate_draft(self) -> "ProfileRefinementResult":
        if self.draft_profile.confirmed:
            raise ValueError("Profile refinement may only produce a draft.")
        statement_refs = {
            ref for statement in self.memory_aware_statements for ref in statement.memory_refs
        }
        if statement_refs != set(self.memory_refs):
            raise ValueError("Profile refinement memory_refs must preserve statement provenance.")
        return self


class VectorSyncDiagnostic(DomainModel):
    operation: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    memory_id: Optional[str] = None
    cleanup_required: bool = False


class MemoryEvent(BaseEvent):
    """Ephemeral safe event; content and full profile payloads are never included."""

    subject_id: str = Field(min_length=1)
    memory_id: Optional[str] = None
    profile_version: Optional[int] = Field(default=None, ge=1)
