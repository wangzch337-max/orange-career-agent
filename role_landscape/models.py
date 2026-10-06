"""Closed, source-owned role membership and ephemeral dialogue contracts."""

from enum import Enum
from typing import Literal
from pydantic import Field, model_validator
from career_reality.models import Strict, Text, Items, DirectionIdentity, Status, Authority


class Dimension(str, Enum):
    OVERVIEW = "overview"
    WORK = "representative_tasks"
    COLLABORATION = "collaboration"
    TECHNICAL = "technical_system_emphasis"
    COMPARISON = "comparison"
    OUTPUTS = "outputs"
    VARIATION = "variation_notes"
    UNKNOWN = "uncertainties"


class RoleArchetype(Strict):
    role_id: str = Field(pattern=r"^role_[a-z0-9_]{1,40}$")
    display_name: Text
    scope: Text
    primary_problem: Text
    work_emphasis: Text
    distinction: Text
    representative_tasks: Items
    collaboration: Items
    outputs: Items
    technical_system_emphasis: Text
    variation_notes: Items
    uncertainties: Items
    reference_aliases: tuple[Text, ...] = Field(min_length=0, max_length=4)


class Membership(Strict):
    role_id: str
    evidence: Text


class RoleLandscapeSource(Strict):
    source_id: str = Field(pattern=r"^landscape_[a-z0-9_]{1,40}$")
    version: int = Field(ge=1, le=100)
    status: Literal["approved_public_demo"]
    source_type: Literal["public_synthetic_curated"]
    provenance: Literal["independently_authored_fictional_role_landscape"]
    direction_identity: DirectionIdentity
    display_name: Text
    scope: Text
    roles: tuple[RoleArchetype, ...] = Field(min_length=2, max_length=5)
    memberships: tuple[Membership, ...] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def exact_membership(self):
        ids = [r.role_id for r in self.roles]
        links = [m.role_id for m in self.memberships]
        aliases = [v for r in self.roles for v in (r.display_name, *r.reference_aliases)]
        if len(set(ids)) != len(ids) or len(set(links)) != len(links) or set(ids) != set(links):
            raise ValueError("INVALID_ROLE_MEMBERSHIP")
        if len(set(aliases)) != len(aliases):
            raise ValueError("AMBIGUOUS_ROLE_REFERENCE")
        return self


class Inventory(Strict):
    schema_version: Literal["orange.role_landscape.sources.v1"]
    records: tuple[RoleLandscapeSource, ...] = Field(min_length=1, max_length=12)


class RoleBlock(Strict):
    role_id: str
    field: str
    text: Text
    authority: Authority
    source_ref: str
    membership_ref: str


class RoleReply(Strict):
    source_id: str
    source_version: int
    dimension: Dimension
    role_ids: tuple[str, ...] = Field(min_length=1, max_length=5)
    blocks: tuple[RoleBlock, ...] = Field(min_length=1, max_length=40)


class Binding(Strict):
    owner: str
    thread: str
    request_id: str
    direction_id: str
    parent_request_id: str
    parent_generation: int
    parent_fingerprint: str
    source_id: str
    source_version: int
    source_fingerprint: str
    displayed_role_ids: tuple[str, ...]


class FollowupToken(Strict):
    owner: str
    thread: str
    request_id: str
    generation: int
    context_fingerprint: str
