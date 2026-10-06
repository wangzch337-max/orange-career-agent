"""Strict, public-source and session-only contracts; no personal authority."""

from enum import Enum
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1, max_length=600)]
Items = Annotated[tuple[Text, ...], Field(min_length=1, max_length=6)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Dimension(str, Enum):
    PURPOSE = "purpose"
    WORK = "typical_work"
    SITUATION = "representative_situations"
    COLLABORATION = "collaboration"
    IO = "inputs_outputs"
    STYLE = "work_style"
    CAPABILITIES = "capabilities_involved"
    VARIATIONS = "internal_variations"
    UNKNOWN = "uncertainties"


class Authority(str, Enum):
    SOURCE_FACT = "source_fact"
    OBSERVATION = "observation"
    EXPLANATION = "derived_explanation"
    EXAMPLE = "representative_example"
    UNKNOWN = "unknown"
    SUGGESTION = "suggestion"


class Status(str, Enum):
    IDLE = "IDLE"
    ACTIVE = "ACTIVE"
    UNSUPPORTED = "UNSUPPORTED"
    STALE = "STALE"
    INVALID = "INVALID"
    LIMIT_REACHED = "LIMIT_REACHED"


class DirectionIdentity(Strict):
    family: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=160)


class Situation(Strict):
    situation_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,40}$")
    situation: Text
    problem: Text
    why_it_matters: Text
    typical_tasks: Items
    inputs: Items
    outputs: Items
    collaborators: Items
    work_style: Items
    capabilities_involved: Items
    uncertainties: Items


class CareerRealitySource(Strict):
    source_id: str = Field(pattern=r"^reality_[a-z0-9_]{1,40}$")
    version: int = Field(ge=1, le=100)
    source_type: Literal["public_synthetic_demo"]
    provenance: Literal["independently_authored_fictional_work_material"]
    identities: tuple[DirectionIdentity, ...] = Field(min_length=1, max_length=8)
    display_name: Text
    purpose: Text
    situations: tuple[Situation, ...] = Field(min_length=1, max_length=3)
    internal_variations: Items
    uncertainties: Items

    @model_validator(mode="after")
    def unique_situations(self):
        ids = [s.situation_id for s in self.situations]
        if len(ids) != len(set(ids)):
            raise ValueError("DUPLICATE_SITUATION")
        return self


class SourceInventory(Strict):
    schema_version: Literal["orange.career_reality.sources.v1"]
    records: tuple[CareerRealitySource, ...] = Field(min_length=1, max_length=24)


class WorkBlock(Strict):
    source_ref: str
    authority: Authority
    text: Text


class WorkReply(Strict):
    source_id: str
    source_version: int
    dimension: Dimension
    situation_id: str
    blocks: tuple[WorkBlock, ...] = Field(min_length=1, max_length=18)


class Binding(Strict):
    owner: str
    thread: str
    request_id: str
    discovery_request_id: str
    direction_id: str
    direction_identity: DirectionIdentity
    profile_id: str
    profile_version: int
    profile_fingerprint: str
    source_id: str
    source_version: int
    source_fingerprint: str


class FollowupToken(Strict):
    owner: str
    thread: str
    request_id: str
    generation: int
    context_fingerprint: str
