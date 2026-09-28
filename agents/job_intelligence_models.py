"""Strict provider-facing contracts for Phase 4 job interpretation."""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Sequence, Set

from pydantic import Field, model_validator

from data.models import (
    EvidenceSourceType,
    JobSignalInferenceType,
    JobUncertainty,
)
from providers.errors import LLMStructuredOutputError
from providers.models import ProviderModel


class JobEvidenceCategory(str, Enum):
    TITLE = "title"
    SUMMARY = "summary"
    RESPONSIBILITY = "responsibility"
    REQUIREMENT = "requirement"
    PREFERRED_QUALIFICATION = "preferred_qualification"
    TECHNOLOGY = "technology"
    LOCATION = "location"
    EMPLOYMENT_TYPE = "employment_type"


class JobSourceEvidence(ProviderModel):
    id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    category: JobEvidenceCategory
    text: str = Field(min_length=1)
    source_type: EvidenceSourceType


class JobEvidenceBundle(ProviderModel):
    source_evidence: List[JobSourceEvidence] = Field(min_length=1)

    @model_validator(mode="after")
    def ensure_unique_ids(self) -> "JobEvidenceBundle":
        ids = [item.id for item in self.source_evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("JobSourceEvidence IDs 必须唯一。")
        return self


class JobExtractionSignal(ProviderModel):
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: List[str] = Field(min_length=1)
    inference_type: JobSignalInferenceType

    @model_validator(mode="after")
    def ensure_unique_evidence_ids(self) -> "JobExtractionSignal":
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("岗位信号 evidence_ids 不能重复。")
        return self


class JobIntelligenceExtraction(ProviderModel):
    """Semantic candidates only; not yet an authoritative domain record."""

    actual_work: List[JobExtractionSignal] = Field(default_factory=list)
    required_capabilities: List[JobExtractionSignal] = Field(default_factory=list)
    preferred_capabilities: List[JobExtractionSignal] = Field(default_factory=list)
    technology_signals: List[JobExtractionSignal] = Field(default_factory=list)
    work_style_signals: List[JobExtractionSignal] = Field(default_factory=list)
    collaboration_context: List[JobExtractionSignal] = Field(default_factory=list)
    growth_exposure: List[JobExtractionSignal] = Field(default_factory=list)
    potential_friction: List[JobExtractionSignal] = Field(default_factory=list)
    job_uncertainties: List[JobUncertainty] = Field(default_factory=list)

    def signals(self) -> List[JobExtractionSignal]:
        return [
            *self.actual_work,
            *self.required_capabilities,
            *self.preferred_capabilities,
            *self.technology_signals,
            *self.work_style_signals,
            *self.collaboration_context,
            *self.growth_exposure,
            *self.potential_friction,
        ]

    def validate_evidence_ids(
        self,
        source_evidence: Sequence[JobSourceEvidence],
    ) -> "JobIntelligenceExtraction":
        allowed_ids: Set[str] = {item.id for item in source_evidence}
        referenced = {
            evidence_id
            for item in [*self.signals(), *self.job_uncertainties]
            for evidence_id in item.evidence_ids
        }
        unknown = referenced - allowed_ids
        if unknown:
            raise LLMStructuredOutputError(
                f"岗位结构化输出引用了未知 evidence IDs: {sorted(unknown)}"
            )
        return self

    def signal_counts(self) -> Dict[str, int]:
        return {
            "actual_work": len(self.actual_work),
            "required_capabilities": len(self.required_capabilities),
            "preferred_capabilities": len(self.preferred_capabilities),
            "technology_signals": len(self.technology_signals),
            "work_style_signals": len(self.work_style_signals),
            "collaboration_context": len(self.collaboration_context),
            "growth_exposure": len(self.growth_exposure),
            "potential_friction": len(self.potential_friction),
            "job_uncertainties": len(self.job_uncertainties),
        }
