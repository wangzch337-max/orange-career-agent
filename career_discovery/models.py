"""Strict proposals and ephemeral, code-owned discovery contracts."""

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1, max_length=160)]
Ref = Annotated[str, Field(pattern=r"^src_[a-f0-9]{16}_[0-9]{3}$")]
Refs = Annotated[tuple[Ref, ...], Field(min_length=1, max_length=8)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Readiness(str, Enum):
    READY = "READY"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    NOT_REQUESTED = "NOT_REQUESTED"


class Status(str, Enum):
    IDLE = "IDLE"
    READY = "READY"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    NOT_REQUESTED = "NOT_REQUESTED"
    CREATED = "CREATED"
    SELECTED = "SELECTED"
    INVALID_CONTEXT = "INVALID_CONTEXT"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    INVALID_REFERENCE = "INVALID_REFERENCE"
    PROVIDER_FAILED = "PROVIDER_FAILED"
    STALE = "STALE"
    CONSENT_REQUIRED = "CONSENT_REQUIRED"


class DiscoveryError(ValueError):
    def __init__(self, code: Status):
        self.code = code
        super().__init__(code.value)


class GoalRelation(str, Enum):
    ALIGNED = "ALIGNED"
    PARTIALLY_ALIGNED = "PARTIALLY_ALIGNED"
    EXPLORATORY = "EXPLORATORY"
    TENSION = "TENSION"
    UNKNOWN = "UNKNOWN"


class Confidence(str, Enum):
    GROUNDED = "GROUNDED"
    TENTATIVE = "TENTATIVE"
    UNCERTAIN = "UNCERTAIN"


class CapabilityKind(str, Enum):
    # General, explicitly tentative interpretations, NOT profession -> direction rules.
    DOCUMENTATION = "structured_documentation"
    COMMUNICATION = "stakeholder_communication"
    ANALYSIS = "analytical_reasoning"
    COORDINATION = "process_coordination"
    DOMAIN = "domain_familiarity"
    LEARNING = "learning_foundation"
    CUSTOMER = "customer_understanding"
    QUALITY = "quality_attention"


class ConsiderationKind(str, Enum):
    DOMAIN_TRANSFER = "domain_transfer"
    EXPERIENCE_DEPTH = "experience_depth"
    QUALIFICATION = "qualification_barrier"
    INDUSTRY_CHANGE = "industry_change"
    RESPONSIBILITY = "responsibility_change"
    WORK_STYLE = "work_style"
    LOCATION = "location_constraint"
    INTENT = "intent_uncertainty"
    EVIDENCE = "additional_evidence_needed"


class Anchor(Strict):
    source_ref: Ref
    excerpt: str = Field(min_length=1, max_length=1200)


class CapabilityProposal(Strict):
    interpretation: CapabilityKind
    anchors: tuple[Anchor, ...] = Field(min_length=1, max_length=4)
    relevance_to_direction: Literal["potential_transfer", "domain_continuity"]
    uncertainty: Literal["requires_validation", "context_dependent"] = "requires_validation"


class ConsiderationProposal(Strict):
    kind: ConsiderationKind
    source_refs: Refs
    topic: Text
    state: Literal["unknown", "evidence_needed", "source_supported"] = "unknown"
    anchor: Anchor | None = None


class DirectionProposal(Strict):
    # No provider-owned direction/capability IDs, ranking, free factual narrative,
    # jobs, company, salary, invented evidence, scores or additional keys.
    title: Text
    direction_family: Text
    source_refs: Refs
    transferable_capabilities: tuple[CapabilityProposal, ...] = Field(default=(), max_length=5)
    transition_considerations: tuple[ConsiderationProposal, ...] = Field(default=(), max_length=5)
    uncertainties: tuple[Text, ...] = Field(default=(), max_length=3)
    evidence_gaps: tuple[Text, ...] = Field(default=(), max_length=3)
    goal_relation: GoalRelation = GoalRelation.EXPLORATORY
    confidence: Confidence = Confidence.TENTATIVE


class DiscoveryProposal(Strict):
    directions: tuple[DirectionProposal, ...] = Field(max_length=5)


class Source(Strict):
    ref: Ref
    origin: Literal["confirmed_profile", "confirmed_memory", "current_explicit", "recent_user_context"]
    category: str
    text: str = Field(min_length=1, max_length=1200, repr=False)
    origin_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    uncertainty: Literal["none", "unknown", "explicit_uncertainty"] = "none"
    goal_type: Literal["career_goal", "project_goal", "learning_goal"] | None = None


class Binding(Strict):
    owner_scope_id: str
    conversation_id: str
    subject_id: str
    request_id: str
    profile_id: str
    profile_version: int
    profile_fingerprint: str
    statement_fingerprint: str
    recent_fingerprint: str
    memory_fingerprints: tuple[tuple[str, str], ...] = ()


class ClarificationNeed(Strict):
    need_id: Literal["background", "exploration_scope"]
    question: Text
    reason: Literal["insufficient_relevant_background", "material_direction_uncertainty"]


class CareerDiscoveryContext(Strict):
    request_id: str
    sources: tuple[Source, ...] = Field(max_length=56)
    partial: bool = False

    def provider_payload(self):
        # Canonical IDs/evidence/provenance remain local; aliases preserve ownership.
        return {"sources": [{"ref": s.ref, "origin": s.origin, "category": s.category,
                             "text": s.text, "uncertainty": s.uncertainty, "goal_type": s.goal_type} for s in self.sources],
                "partial": self.partial, "current_intent_overrides_historical_intent": True}


class TransferableCapability(Strict):
    capability_id: str
    label: Text
    derived_from_refs: Refs
    relevance_to_direction: Literal["potential_transfer", "domain_continuity"]
    interpretation_status: Literal["derived_candidate"] = "derived_candidate"
    uncertainty: Literal["requires_validation", "context_dependent"]
    safe_explanation: str


class TransitionConsideration(Strict):
    kind: ConsiderationKind
    source_refs: Refs
    description: str
    state: Literal["unknown", "evidence_needed", "source_supported"]
    authority: Literal["derived_candidate"] = "derived_candidate"


class CareerDirectionCandidate(Strict):
    direction_id: str
    title: Text
    direction_family: Text
    summary: str
    why_explore: str
    supporting_profile_refs: tuple[str, ...]
    supporting_memory_refs: tuple[str, ...]
    current_signal_refs: tuple[Ref, ...]
    recent_context_refs: tuple[Ref, ...] = ()
    transferable_capabilities: tuple[TransferableCapability, ...]
    transition_considerations: tuple[TransitionConsideration, ...]
    uncertainties: tuple[str, ...]
    evidence_gaps: tuple[str, ...]
    goal_relation: GoalRelation
    confidence: Confidence
    status: Literal["candidate"] = "candidate"


class CareerDiscoveryResult(Strict):
    request_id: str
    readiness: Readiness
    clarification_need: ClarificationNeed | None = None
    directions: tuple[CareerDirectionCandidate, ...] = Field(default=(), max_length=5)
    partial: bool = False
    source_summary: tuple[tuple[str, int], ...] = ()
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: Status

    @model_validator(mode="after")
    def mutually_exclusive(self):
        if self.readiness != Readiness.READY and self.directions:
            raise ValueError("DIRECTIONS_NOT_READY")
        if (self.readiness == Readiness.NEEDS_CLARIFICATION) != (self.clarification_need is not None):
            raise ValueError("INVALID_CLARIFICATION_STATE")
        return self


class SelectionToken(Strict):
    owner_scope_id: str
    conversation_id: str
    request_id: str
    result_fingerprint: str
