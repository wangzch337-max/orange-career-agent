"""Provider-facing Phase 5 Match & Insight contracts."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Dict, List, Literal, Optional, Set, Union

from pydantic import AfterValidator, Field, TypeAdapter, WithJsonSchema, create_model, model_validator
from pydantic_core import PydanticCustomError

from data.models import (
    ActionType,
    GoalType,
    MatchDimension,
    MatchRelationType,
    Severity,
)
from providers.errors import LLMStructuredOutputError
from providers.models import ProviderModel


class ProfileSignalCategory(str, Enum):
    SKILL = "skill"
    INTEREST = "interest"
    VALUE = "value"
    GOAL = "goal"
    CAREER_PREFERENCE = "career_preference"
    STRENGTH = "strength"
    DEVELOPMENT_AREA = "development_area"


class JobSignalCategory(str, Enum):
    ACTUAL_WORK = "actual_work"
    REQUIRED_CAPABILITY = "required_capability"
    PREFERRED_CAPABILITY = "preferred_capability"
    TECHNOLOGY = "technology"
    WORK_STYLE = "work_style"
    COLLABORATION_CONTEXT = "collaboration_context"
    GROWTH_EXPOSURE = "growth_exposure"
    POTENTIAL_FRICTION = "potential_friction"
    UNCERTAINTY = "uncertainty"


class MatchEvidenceRef(ProviderModel):
    evidence_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source_type: str = Field(min_length=1)


class ProfileSignalRef(ProviderModel):
    signal_id: str = Field(min_length=1)
    category: ProfileSignalCategory
    label: str = Field(min_length=1)
    description: str = ""
    evidence_ids: List[str] = Field(default_factory=list)
    confirmed_by_user: bool
    goal_type: Optional[GoalType] = None

    @model_validator(mode="after")
    def validate_goal_type_scope(self) -> "ProfileSignalRef":
        if self.category == ProfileSignalCategory.GOAL and self.goal_type is None:
            raise ValueError("goal profile signal 必须包含 goal_type")
        if self.category != ProfileSignalCategory.GOAL and self.goal_type is not None:
            raise ValueError("只有 goal profile signal 可以包含 goal_type")
        return self


class JobSignalRef(ProviderModel):
    signal_id: str = Field(min_length=1)
    category: JobSignalCategory
    label: str = Field(min_length=1)
    description: str = ""
    evidence_ids: List[str] = Field(default_factory=list)


class MatchContext(ProviderModel):
    profile_id: str = Field(min_length=1)
    profile_version: int = Field(ge=1)
    job_id: str = Field(min_length=1)
    intelligence_id: str = Field(min_length=1)
    role_title: str = Field(min_length=1)
    profile_signals: List[ProfileSignalRef] = Field(default_factory=list)
    profile_evidence: List[MatchEvidenceRef] = Field(default_factory=list)
    job_signals: List[JobSignalRef] = Field(default_factory=list)
    job_evidence: List[MatchEvidenceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_unique_ids(self) -> "MatchContext":
        for items, attribute, label in (
            (self.profile_signals, "signal_id", "profile signal"),
            (self.profile_evidence, "evidence_id", "profile evidence"),
            (self.job_signals, "signal_id", "job signal"),
            (self.job_evidence, "evidence_id", "job evidence"),
        ):
            values = [getattr(item, attribute) for item in items]
            if len(values) != len(set(values)):
                raise ValueError(f"MatchContext {label} IDs 必须唯一")
        return self


class MatchCandidateBase(ProviderModel):
    """Fields shared by the three provider-facing relation structures."""

    candidate_id: str = Field(min_length=1)
    dimension: MatchDimension
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    needs_user_review: bool = True

    @model_validator(mode="after")
    def ensure_unique_signal_ids(self) -> "MatchCandidateBase":
        for field_name in ("profile_signal_ids", "job_signal_ids"):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise PydanticCustomError(
                    "duplicate_identifier",
                    f"{field_name} cannot contain duplicate IDs",
                )
        return self


class BilateralMatchCandidate(MatchCandidateBase):
    """Relations whose provider structure requires both signal sides."""

    relation_type: Literal[
        MatchRelationType.STRONG_ALIGNMENT,
        MatchRelationType.PARTIAL_ALIGNMENT,
        MatchRelationType.CONFIRMED_GAP,
        MatchRelationType.EXPERIENCE_DEPTH_GAP,
        MatchRelationType.PREFERENCE_ALIGNMENT,
        MatchRelationType.POTENTIAL_FRICTION,
    ]
    profile_signal_ids: List[str] = Field(min_length=1)
    job_signal_ids: List[str] = Field(min_length=1)


class EvidenceMissingCandidate(MatchCandidateBase):
    """Missing-profile-evidence relation with a mandatory job side."""

    relation_type: Literal[MatchRelationType.EVIDENCE_MISSING]
    profile_signal_ids: List[str] = Field(default_factory=list)
    job_signal_ids: List[str] = Field(min_length=1)


class UnknownMatchCandidate(MatchCandidateBase):
    """Unknown relation allowing either signal side, but never neither."""

    relation_type: Literal[MatchRelationType.UNKNOWN]
    profile_signal_ids: List[str] = Field(default_factory=list)
    job_signal_ids: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_at_least_one_signal_side(self) -> "UnknownMatchCandidate":
        if not (self.profile_signal_ids or self.job_signal_ids):
            raise PydanticCustomError(
                "unknown_signal_reference_required",
                "unknown requires at least one signal side",
            )
        return self


MatchInsightCandidate = Annotated[
    Union[
        BilateralMatchCandidate,
        EvidenceMissingCandidate,
        UnknownMatchCandidate,
    ],
    Field(discriminator="relation_type"),
]
_MATCH_INSIGHT_CANDIDATE_ADAPTER = TypeAdapter(MatchInsightCandidate)


def validate_match_insight_candidate(payload: object) -> MatchInsightCandidate:
    """Validate one provider candidate through the relation discriminator."""

    return _MATCH_INSIGHT_CANDIDATE_ADAPTER.validate_python(payload)


class NormalizedMatchCandidate(ProviderModel):
    """Uniform copy-only representation consumed by deterministic assembly."""

    candidate_id: str = Field(min_length=1)
    dimension: MatchDimension
    relation_type: MatchRelationType
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    profile_signal_ids: List[str] = Field(default_factory=list)
    job_signal_ids: List[str] = Field(default_factory=list)
    needs_user_review: bool = True

    @classmethod
    def from_provider(
        cls,
        candidate: MatchInsightCandidate,
    ) -> "NormalizedMatchCandidate":
        return cls.model_validate(candidate.model_dump())


class MatchActionCandidate(ProviderModel):
    action_id: str = Field(min_length=1)
    action_type: ActionType
    description: str = Field(min_length=1)
    related_insight_ids: List[str] = Field(min_length=1)
    priority: Severity = Severity.MEDIUM
    expected_evidence: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    target_label: str = Field(min_length=1)

    @model_validator(mode="after")
    def ensure_unique_related_ids(self) -> "MatchActionCandidate":
        if len(self.related_insight_ids) != len(set(self.related_insight_ids)):
            raise ValueError("Action candidate related_insight_ids 不能重复")
        return self


class MatchInsightExtraction(ProviderModel):
    candidate_alignments: List[MatchInsightCandidate] = Field(default_factory=list)
    candidate_gaps: List[MatchInsightCandidate] = Field(default_factory=list)
    candidate_frictions: List[MatchInsightCandidate] = Field(default_factory=list)
    candidate_unknowns: List[MatchInsightCandidate] = Field(default_factory=list)
    candidate_actions: List[MatchActionCandidate] = Field(default_factory=list)

    def insights(self) -> List[MatchInsightCandidate]:
        return [
            *self.candidate_alignments,
            *self.candidate_gaps,
            *self.candidate_frictions,
            *self.candidate_unknowns,
        ]

    def normalized_insights(self) -> List[NormalizedMatchCandidate]:
        return [NormalizedMatchCandidate.from_provider(item) for item in self.insights()]

    @model_validator(mode="after")
    def ensure_unique_candidate_ids(self) -> "MatchInsightExtraction":
        insight_ids = [item.candidate_id for item in self.insights()]
        action_ids = [item.action_id for item in self.candidate_actions]
        if len(insight_ids) != len(set(insight_ids)):
            raise PydanticCustomError(
                "duplicate_candidate_id",
                "Match insight candidate IDs 必须唯一",
            )
        if len(action_ids) != len(set(action_ids)):
            raise PydanticCustomError(
                "duplicate_action_id",
                "Match action IDs 必须唯一",
            )
        return self

    def validate_context(self, context: MatchContext) -> "MatchInsightExtraction":
        profile_signal_ids = {item.signal_id for item in context.profile_signals}
        job_signal_ids = {item.signal_id for item in context.job_signals}
        allowed = (
            (
                "profile signal",
                "UNKNOWN_PROFILE_SIGNAL_ID",
                profile_signal_ids,
                lambda candidate: candidate.profile_signal_ids,
            ),
            (
                "job signal",
                "UNKNOWN_JOB_SIGNAL_ID",
                job_signal_ids,
                lambda candidate: candidate.job_signal_ids,
            ),
        )
        for candidate in self.insights():
            for label, error_code, valid_ids, getter in allowed:
                unknown = set(getter(candidate)) - valid_ids
                if unknown:
                    identifier = sorted(unknown)[0]
                    raise LLMStructuredOutputError(
                        f"Match output 引用了未知 {label} ID。",
                        error_code=error_code,
                        stage="MatchInsightExtraction.validate_context",
                        identifier=identifier,
                    )
        known_insight_ids: Set[str] = {item.candidate_id for item in self.insights()}
        unknown_action_links = {
            insight_id
            for action in self.candidate_actions
            for insight_id in action.related_insight_ids
            if insight_id not in known_insight_ids
        }
        if unknown_action_links:
            identifier = sorted(unknown_action_links)[0]
            raise LLMStructuredOutputError(
                "Action 引用了未知 insight ID。",
                error_code="ACTION_UNKNOWN_INSIGHT_ID",
                stage="MatchInsightExtraction.validate_context",
                identifier=identifier,
            )
        return self

    def relation_counts(self) -> Dict[str, int]:
        return {
            relation.value: sum(
                item.relation_type == relation for item in self.insights()
            )
            for relation in MatchRelationType
        }


def allowed_match_signal_ids(
    context: MatchContext,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return the authoritative, request-scoped profile and job ID universes."""

    profile_ids = tuple(item.signal_id for item in context.profile_signals)
    job_ids = tuple(item.signal_id for item in context.job_signals)
    if set(profile_ids) & set(job_ids):
        raise ValueError("MatchContext profile and job signal namespaces must be disjoint")
    return profile_ids, job_ids


def _scoped_signal_id_type(
    allowed_ids: tuple[str, ...],
    *,
    error_type: str,
    side: str,
):
    """Create a string annotation with matching runtime and JSON Schema limits."""

    allowed = frozenset(allowed_ids)

    def validate(value: str) -> str:
        if value not in allowed:
            raise PydanticCustomError(
                error_type,
                f"{side} signal ID is not allowed by this MatchContext",
            )
        return value

    return Annotated[
        str,
        AfterValidator(validate),
        WithJsonSchema({"type": "string", "enum": list(allowed_ids)}),
    ]


def build_match_insight_response_model(
    context: MatchContext,
) -> type[MatchInsightExtraction]:
    """Compose relation-aware candidates with request-scoped signal-ID enums."""

    profile_ids, job_ids = allowed_match_signal_ids(context)
    profile_signal_id = _scoped_signal_id_type(
        profile_ids,
        error_type="unknown_profile_signal_id",
        side="profile",
    )
    job_signal_id = _scoped_signal_id_type(
        job_ids,
        error_type="unknown_job_signal_id",
        side="job",
    )

    scoped_bilateral = create_model(
        "RequestScopedBilateralMatchCandidate",
        __base__=BilateralMatchCandidate,
        profile_signal_ids=(List[profile_signal_id], Field(min_length=1)),
        job_signal_ids=(List[job_signal_id], Field(min_length=1)),
    )
    scoped_evidence_missing = create_model(
        "RequestScopedEvidenceMissingCandidate",
        __base__=EvidenceMissingCandidate,
        profile_signal_ids=(List[profile_signal_id], Field(default_factory=list)),
        job_signal_ids=(List[job_signal_id], Field(min_length=1)),
    )
    scoped_unknown = create_model(
        "RequestScopedUnknownMatchCandidate",
        __base__=UnknownMatchCandidate,
        profile_signal_ids=(List[profile_signal_id], Field(default_factory=list)),
        job_signal_ids=(List[job_signal_id], Field(default_factory=list)),
    )
    scoped_candidate = Annotated[
        Union[
            scoped_bilateral,
            scoped_evidence_missing,
            scoped_unknown,
        ],
        Field(discriminator="relation_type"),
    ]
    return create_model(
        "RequestScopedMatchInsightExtraction",
        __base__=MatchInsightExtraction,
        candidate_alignments=(List[scoped_candidate], Field(default_factory=list)),
        candidate_gaps=(List[scoped_candidate], Field(default_factory=list)),
        candidate_frictions=(List[scoped_candidate], Field(default_factory=list)),
        candidate_unknowns=(List[scoped_candidate], Field(default_factory=list)),
    )
