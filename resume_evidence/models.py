"""Strict reported claims; source visibility is not independently confirmed truth."""

import json
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from resume_evidence.policy import (
    MAX_EVIDENCE_ITEMS, MAX_SOURCE_REFS, MAX_WORK_DETAILS, MAX_UNCERTAINTIES,
    MAX_CLAIM_CHARS, MAX_QUOTE_CHARS, CATEGORIES,
)

Text = Annotated[str, Field(strict=True, min_length=1, max_length=MAX_CLAIM_CHARS)]
SourceID = Annotated[str, Field(strict=True, min_length=1, max_length=120)]
Refs = Annotated[tuple[SourceID, ...], Field(min_length=1, max_length=MAX_SOURCE_REFS)]
Details = Annotated[tuple[Text, ...], Field(max_length=MAX_WORK_DETAILS)]


class EvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True,
                              revalidate_instances="always")


class SourceQuote(EvidenceModel):
    block_id: SourceID
    excerpt: str = Field(strict=True, min_length=1, max_length=MAX_QUOTE_CHARS, repr=False)


class ResumeEvidence(EvidenceModel):
    evidence_id: str = Field(strict=True, pattern=r"^resume_evidence_[0-9]{3}$")
    normalized_claim: Text = Field(repr=False, description=(
        "NON_AUTHORITATIVE_PROVIDER_OUTPUT; replaced before canonical admission. "
        "Use an extractive phrase or "
        "finite grammatical normalization of whole supported fact phrases; no new "
        "ownership, proficiency, metrics, causal relationship or career preference. "
        "Referenced source_quotes remain extractive; all typed fields are checked independently."
    ))
    source_block_ids: Refs
    source_quotes: tuple[SourceQuote, ...] = Field(min_length=1, max_length=MAX_SOURCE_REFS, repr=False)
    confidence: Literal["explicit", "supported", "uncertain"]
    uncertainty: Literal["none", "unclear_dates", "unclear_organization", "unclear_proficiency",
                         "unclear_ownership", "overlapping_roles", "ambiguous_project_work_boundary", "other"]
    evidence_origin: Literal["resume_provided"]
    claim_type: Literal["reported_fact", "explicit_career_statement"]

    @model_validator(mode="after")
    def conservative_uncertainty(self):
        if self.uncertainty != "none" and self.confidence != "uncertain":
            raise ValueError("RESUME_UNCERTAINTY_REQUIRES_UNCERTAIN_CONFIDENCE")
        return self

    @property
    def canonical_facts(self) -> tuple[str, ...]:
        """Validated material fields, or the admitted extractive generic fact.

        Only validate_extraction admits provider output. Properties do not prove
        grounding and must not be used to bypass that boundary.
        """
        return (self.normalized_claim,)

    @property
    def canonical_label(self) -> str:
        return self.canonical_facts[0]

    @property
    def canonical_text(self) -> str:
        """Juxtaposition only: no generated adjectives, inference or new relation."""
        return " · ".join(dict.fromkeys(self.canonical_facts))

    def canonical_projection(self, limit: int) -> tuple[str, bool]:
        """Bounded whole facts, never a sliced quantity/negation/ownership value."""
        included = []
        for fact in dict.fromkeys(self.canonical_facts):
            if len(" · ".join((*included, fact))) <= limit:
                included.append(fact)
        text = " · ".join(included)
        return text, text != self.canonical_text


class WorkExperienceEvidence(ResumeEvidence):
    category: Literal["work_experience"]
    role_title: Text | None = Field(repr=False)
    organization: Text | None = Field(repr=False)
    time_range: Text | None = Field(repr=False)
    responsibilities: Details = Field(repr=False)
    achievements: Details = Field(repr=False)
    domain_signals: Details = Field(repr=False)
    tools: Details = Field(repr=False)
    business_metrics: Details = Field(repr=False)

    @property
    def material_fields(self) -> tuple[str, ...]:
        return tuple(value for value in (self.role_title, self.organization, self.time_range) if value is not None) + (
            *self.responsibilities, *self.achievements, *self.domain_signals, *self.tools, *self.business_metrics)

    @property
    def canonical_facts(self) -> tuple[str, ...]:
        return self.material_fields or super().canonical_facts


class ProjectEvidence(ResumeEvidence):
    category: Literal["projects"]
    project_name: Text | None = Field(repr=False)
    responsibilities: Details = Field(repr=False)
    achievements: Details = Field(repr=False)

    @property
    def material_fields(self) -> tuple[str, ...]:
        return ((self.project_name,) if self.project_name else ()) + self.responsibilities + self.achievements

    @property
    def canonical_facts(self) -> tuple[str, ...]:
        return self.material_fields or super().canonical_facts


class GeneralResumeEvidence(ResumeEvidence):
    category: Literal["education", "responsibilities", "achievements", "skills", "tools",
                      "domain_knowledge", "certifications", "professional_qualifications", "research",
                      "leadership", "collaboration", "languages", "portfolio", "business_metrics",
                      "awards", "publications", "other_evidence", "uncertainty"]


EvidenceItem = Union[WorkExperienceEvidence, ProjectEvidence, GeneralResumeEvidence]


class ResumeUncertainty(EvidenceModel):
    """A bounded uncertainty, not free-text diagnosis or an authoritative claim."""
    topic: Literal["dates", "organization", "proficiency", "ownership", "career_goal",
                   "role_overlap", "project_work_boundary", "other"]
    status: Literal["unclear", "not_stated"]
    source_block_ids: tuple[SourceID, ...] = Field(max_length=MAX_SOURCE_REFS)

    @model_validator(mode="after")
    def source_for_ambiguity(self):
        if self.status == "unclear" and not self.source_block_ids:
            raise ValueError("RESUME_AMBIGUITY_REQUIRES_SOURCE")
        return self


class ResumeEvidenceExtraction(EvidenceModel):
    items: tuple[EvidenceItem, ...] = Field(max_length=MAX_EVIDENCE_ITEMS, repr=False)
    uncertainties: tuple[ResumeUncertainty, ...] = Field(max_length=MAX_UNCERTAINTIES)

    def canonical_payload(self) -> dict:
        """Stable fact/source identity; provider display wording is not identity."""
        payload = self.model_dump(mode="json")
        for item, data in zip(self.items, payload["items"]):
            data["normalized_claim"] = item.canonical_label
        return payload

    def canonical_json(self) -> str:
        return json.dumps(self.canonical_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ResumeEvidenceBundle(ResumeEvidenceExtraction):
    """Local candidate authority only; no Profile/Memory fields or write commands."""
    source_id: SourceID
    content_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    owner_scope_id: SourceID = Field(repr=False)
    thread_id: SourceID = Field(repr=False)
    context_partial: bool = Field(strict=True)
    authority: Literal["candidate"] = "candidate"

    def category_counts(self) -> dict[str, int]:
        return {category: sum(item.category == category for item in self.items) for category in CATEGORIES}
