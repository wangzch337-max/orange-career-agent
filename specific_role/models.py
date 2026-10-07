"""Closed public-source contracts and ephemeral D.1–D.3 ownership receipts."""

from enum import Enum
from typing import Literal
from pydantic import Field, model_validator
from career_reality.models import Strict, Text, Items, Authority, Status, DirectionIdentity


class Dimension(str, Enum):
    OVERVIEW = "overview"
    PURPOSE = "purpose"
    WORK = "responsibilities"
    SITUATION = "work_situations"
    IO = "inputs_outputs"
    COLLABORATION = "collaborators"
    DECISIONS = "decision_scope"
    RHYTHM = "work_rhythm"
    TECHNICAL = "technical_involvement"
    CAPABILITIES = "capabilities_involved"
    VARIATION = "organizational_variation"
    UNKNOWN = "unknowns"


class Membership(Strict):
    direction_id: str
    archetype_id: str
    representative_role_id: str
    direction_archetype_evidence: Text
    archetype_role_evidence: Text


class SpecificRoleSource(Strict):
    source_id: str = Field(pattern=r"^specific_[a-z0-9_]{1,40}$")
    version: Literal[1]
    status: Literal["approved_public_demo"]
    source_type: Literal["public_synthetic_curated"]
    provenance: Literal["independently_authored_fictional_specific_role"]
    direction_identity: DirectionIdentity
    parent_direction_id: str
    parent_archetype_id: str
    parent_source_id: str
    parent_source_version: int = Field(ge=1)
    parent_source_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    representative_role_id: str = Field(pattern=r"^specific_role_[a-z0-9_]{1,40}$")
    display_name: Text
    scope: Text
    purpose: Text
    responsibilities: Items
    work_situations: Items
    inputs: Items
    outputs: Items
    collaborators: Items
    decision_scope: Items
    work_rhythm: Items
    technical_involvement: Items
    capabilities_involved: Items
    organizational_variation: Items
    unknowns: Items
    membership: Membership

    @model_validator(mode="after")
    def exact_membership(self):
        if (self.parent_direction_id, self.parent_archetype_id, self.representative_role_id) != (
                self.membership.direction_id, self.membership.archetype_id, self.membership.representative_role_id):
            raise ValueError("INVALID_SPECIFIC_ROLE_MEMBERSHIP")
        return self


class Inventory(Strict):
    schema_version: Literal["orange.specific_role.sources.v1"]
    records: tuple[SpecificRoleSource, ...] = Field(min_length=9, max_length=9)


class RoleBlock(Strict):
    field: str
    text: Text
    authority: Authority
    source_ref: str
    membership_refs: tuple[str, str]


class RoleReply(Strict):
    source_id: str
    source_version: int
    source_fingerprint: str
    archetype_id: str
    representative_role_id: str
    dimension: Dimension
    blocks: tuple[RoleBlock, ...] = Field(min_length=1, max_length=12)


class Binding(Strict):
    owner: str
    thread: str
    request_id: str
    discovery_request_id: str
    direction_id: str
    reality_request_id: str
    reality_generation: int
    reality_fingerprint: str
    landscape_request_id: str
    landscape_generation: int
    landscape_fingerprint: str
    archetype_id: str
    source_id: str
    source_version: int
    source_fingerprint: str
    representative_role_id: str


class FollowupToken(Strict):
    owner: str
    thread: str
    request_id: str
    generation: int
    context_fingerprint: str
