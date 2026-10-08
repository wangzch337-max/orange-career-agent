"""Closed D.6 contracts. Reported outcomes are never confirmed skill facts."""

from typing import Literal
from pydantic import Field
from career_reality.models import Strict, Text
from evidence_match.models import Relation


class Template(Strict):
    template_id: str = Field(pattern=r"^experiment_[a-z0-9_]+$")
    version: Literal[1]
    provenance: Literal["independently_authored_public_synthetic"]
    direction_id: str
    archetype_id: str
    role_id: str
    source_id: str
    source_version: Literal[1]
    source_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    work_field: Literal["responsibilities"]
    work_evidence_ids: tuple[str] = Field(min_length=1, max_length=1)
    work_authority: Literal["SOURCE_FACT"]
    eligible_relation_types: tuple[Literal["UNKNOWN", "RELATED_BUT_PARTIAL"], ...]
    unknown_scope: Text
    partial_scope: Text
    task: Text
    synthetic_material: Text
    estimated_minutes: int = Field(ge=30, le=90)
    allowed_assistance: Text
    expected_observations: tuple[Text, ...] = Field(min_length=1, max_length=5)
    reflection_questions: tuple[Text, ...] = Field(min_length=1, max_length=5)
    limitations: tuple[Text, ...] = Field(min_length=1, max_length=5)
    optional: Literal[True]
    can_stop: Literal[True]


class Inventory(Strict):
    schema_version: Literal["orange.evidence_validation.templates.v1"]
    templates: tuple[Template, ...] = Field(min_length=9, max_length=9)


class Target(Strict):
    relation_id: str
    relation_type: Relation
    work_signal_id: str
    work_evidence_ids: tuple[str, ...]
    label: Text
    unresolved_scope: Text
    reason: Literal["user_evidence_insufficient", "independence_unestablished"]


class Candidate(Strict):
    kind: Literal["recollection", "current_claim", "scope", "context"]
    text: Text
    authority: Literal["session_candidate"] = "session_candidate"


class Outcome(Strict):
    completion: Literal["not_reported", "reported_completed", "stopped"] = "not_reported"
    observations: tuple[Text, ...] = ()
    text_outputs: tuple[Text, ...] = ()
    reflections: tuple[Text, ...] = ()
    assistance_reports: tuple[Text, ...] = ()
    authority: Literal["unverified_session_report"] = "unverified_session_report"


class Binding(Strict):
    owner: str
    subject: str
    thread: str
    request_id: str
    generation: int
    parent_request_id: str
    parent_generation: int
    parent_binding_fingerprint: str
    parent_result_fingerprint: str
    parent_context_fingerprint: str
    profile_id: str
    profile_version: int
    profile_fingerprint: str
    role_id: str
    source_id: str
    source_version: int
    source_fingerprint: str
    relation_id: str
    relation_fingerprint: str
    work_evidence_ids: tuple[str, ...]
    template_id: str | None
    template_version: int | None
    template_fingerprint: str | None


class Token(Strict):
    owner: str
    subject: str
    thread: str
    request_id: str
    generation: int
    turn: int
    parent_fingerprint: str
