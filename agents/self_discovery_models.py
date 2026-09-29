"""Phase 3 semantic extraction and result contracts."""

from __future__ import annotations

import re
from typing import Dict, List, Literal, Optional, Sequence, Set

from pydantic import Field, JsonValue, field_validator, model_validator

from data.models import (
    ClarificationQuestion,
    DomainModel,
    EvidenceItem,
    EvidenceSourceType,
    GoalType,
    InferenceType,
    ProfileUncertainty,
    Severity,
    UserProfile,
)
from providers.errors import LLMStructuredOutputError
from providers.models import LLMUsage, ProviderModel


class SelfDiscoverySourceEvidence(ProviderModel):
    """Evidence supplied by deterministic Python; the LLM may only reference it."""

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source_type: EvidenceSourceType
    source_name: str = Field(min_length=1)
    supports_development_area: bool = False


class SelfDiscoverySignal(ProviderModel):
    label: str = Field(min_length=1)
    description: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: List[str] = Field(min_length=1)
    inference_type: InferenceType
    needs_confirmation: bool = True

    @field_validator("evidence_ids")
    @classmethod
    def reject_duplicate_evidence_ids(cls, value: List[str]) -> List[str]:
        if len(value) != len(set(value)):
            raise ValueError("同一信号不能重复引用 evidence ID。")
        return value


class SkillSignal(SelfDiscoverySignal):
    level: Optional[str] = None


class InterestExtractionSignal(SelfDiscoverySignal):
    pass


class ValueExtractionSignal(SelfDiscoverySignal):
    pass


class GoalExtractionSignal(SelfDiscoverySignal):
    goal_type: GoalType


class StrengthSignal(SelfDiscoverySignal):
    pass


class DevelopmentAreaSignal(SelfDiscoverySignal):
    basis: Literal["explicit_limited_experience", "direct_capability_gap"]


class CareerPreferenceSignal(SelfDiscoverySignal):
    pass


class SelfDiscoveryExtraction(ProviderModel):
    """Candidate semantic signals only; this is never the authoritative profile."""

    skills: List[SkillSignal] = Field(default_factory=list)
    interests: List[InterestExtractionSignal] = Field(default_factory=list)
    values: List[ValueExtractionSignal] = Field(default_factory=list)
    goals: List[GoalExtractionSignal] = Field(default_factory=list)
    strengths: List[StrengthSignal] = Field(default_factory=list)
    development_areas: List[DevelopmentAreaSignal] = Field(default_factory=list)
    career_preferences: List[CareerPreferenceSignal] = Field(default_factory=list)
    profile_uncertainties: List[ProfileUncertainty] = Field(default_factory=list)
    clarification_questions: List[ClarificationQuestion] = Field(
        default_factory=list,
        max_length=5,
    )

    def all_signals(self) -> List[SelfDiscoverySignal]:
        return [
            *self.skills,
            *self.interests,
            *self.values,
            *self.goals,
            *self.strengths,
            *self.development_areas,
            *self.career_preferences,
        ]

    def validate_evidence_ids(
        self,
        source_evidence: Sequence[SelfDiscoverySourceEvidence],
    ) -> "SelfDiscoveryExtraction":
        allowed_ids: Set[str] = {item.id for item in source_evidence}
        if len(allowed_ids) != len(source_evidence):
            raise LLMStructuredOutputError("输入 SourceEvidence ID 必须唯一。")
        referenced_ids = {
            evidence_id
            for signal in self.all_signals()
            for evidence_id in signal.evidence_ids
        }
        referenced_ids.update(
            evidence_id
            for uncertainty in self.profile_uncertainties
            for evidence_id in uncertainty.evidence_ids
        )
        referenced_ids.update(
            evidence_id
            for question in self.clarification_questions
            for evidence_id in question.related_evidence_ids
        )
        unknown = referenced_ids - allowed_ids
        if unknown:
            raise LLMStructuredOutputError(
                f"Self-Discovery 输出引用了未知 evidence IDs: {sorted(unknown)}"
            )
        self._validate_professional_label_grounding(source_evidence)
        return self

    def _validate_professional_label_grounding(
        self,
        source_evidence: Sequence[SelfDiscoverySourceEvidence],
    ) -> None:
        """Reject broad capability labels whose linked evidence supports only a subset."""

        evidence_by_id = {item.id: item.text for item in source_evidence}
        rules = (
            (
                re.compile(r"\bdevops\b", re.IGNORECASE),
                re.compile(
                    r"\bdevops\b|ci\s*/?\s*cd|continuous (?:integration|delivery|deployment)|"
                    r"deployment pipeline|infrastructure|container(?:ization| orchestration)?|"
                    r"docker|kubernetes|cloud operations|部署流水线|基础设施|容器编排|云运维",
                    re.IGNORECASE,
                ),
                "DevOps",
            ),
            (
                re.compile(r"\bfull[ -]?stack\b|全栈", re.IGNORECASE),
                re.compile(
                    r"\bfull[ -]?stack\b|全栈|(?:frontend|前端).*(?:backend|后端)|"
                    r"(?:backend|后端).*(?:frontend|前端)",
                    re.IGNORECASE,
                ),
                "full-stack",
            ),
            (
                re.compile(r"\bbackend\s+(?:capabilit|ownership)|后端(?:能力|所有权)", re.IGNORECASE),
                re.compile(
                    r"backend (?:service|development|system|ownership)|server-side|"
                    r"后端(?:服务|开发|系统)|服务端(?:开发|系统)",
                    re.IGNORECASE,
                ),
                "backend ownership",
            ),
        )
        for signal in [*self.skills, *self.strengths]:
            claim = f"{signal.label} {signal.description}"
            evidence_text = " ".join(
                evidence_by_id[evidence_id]
                for evidence_id in signal.evidence_ids
                if evidence_id in evidence_by_id
            )
            for claim_pattern, support_pattern, category in rules:
                if claim_pattern.search(claim) and not support_pattern.search(evidence_text):
                    raise LLMStructuredOutputError(
                        f"专业能力标签超出证据范围：{category} 缺少直接支持。"
                    )

    def signal_counts(self) -> Dict[str, int]:
        return {
            "skills": len(self.skills),
            "interests": len(self.interests),
            "values": len(self.values),
            "goals": len(self.goals),
            "strengths": len(self.strengths),
            "development_areas": len(self.development_areas),
            "career_preferences": len(self.career_preferences),
            "uncertainties": len(self.profile_uncertainties),
            "clarification_questions": len(self.clarification_questions),
        }


class EvidenceBundle(DomainModel):
    source_evidence: List[SelfDiscoverySourceEvidence] = Field(min_length=1)
    domain_evidence: List[EvidenceItem] = Field(min_length=1)
    education_summary: Optional[str] = None

    @model_validator(mode="after")
    def validate_alignment(self) -> "EvidenceBundle":
        source_ids = [item.id for item in self.source_evidence]
        domain_ids = [item.id for item in self.domain_evidence]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("SourceEvidence ID 必须唯一。")
        if source_ids != domain_ids:
            raise ValueError("Provider evidence 与 domain evidence 必须顺序一致。")
        return self


class SelfDiscoveryResult(DomainModel):
    user_profile: UserProfile
    uncertainties: List[ProfileUncertainty] = Field(default_factory=list)
    clarification_questions: List[ClarificationQuestion] = Field(default_factory=list)
    extraction_metadata: Dict[str, JsonValue] = Field(default_factory=dict)
    usage: LLMUsage = Field(default_factory=LLMUsage)
