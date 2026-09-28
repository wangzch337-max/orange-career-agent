"""Deterministic assembly from validated semantic signals to UserProfile."""

from __future__ import annotations

from typing import Dict, Sequence

from agents.self_discovery_models import (
    EvidenceBundle,
    SelfDiscoveryExtraction,
    SelfDiscoveryResult,
    SelfDiscoverySignal,
)
from data.models import (
    CandidateSkill,
    CareerPreference,
    EvidenceBackedStatement,
    EvidenceItem,
    EvidenceSourceType,
    Goal,
    InterestSignal,
    SignalStrength,
    UserProfile,
    ValueSignal,
)
from providers.errors import LLMStructuredOutputError
from providers.models import LLMUsage


class ProfileAssembler:
    """Apply deterministic mapping only; never infer or call an LLM."""

    def assemble(
        self,
        *,
        profile_id: str,
        extraction: SelfDiscoveryExtraction,
        evidence: EvidenceBundle,
        extraction_metadata: Dict[str, object],
        usage: LLMUsage,
    ) -> SelfDiscoveryResult:
        extraction.validate_evidence_ids(evidence.source_evidence)
        self._validate_development_areas(extraction, evidence.domain_evidence)

        profile = UserProfile(
            profile_id=profile_id,
            version=1,
            education_summary=evidence.education_summary,
            skills=[
                CandidateSkill(
                    skill_id=f"skill_{index:03d}",
                    label=signal.label,
                    description=signal.description,
                    level=signal.level,
                    **self._linked_fields(signal, evidence.domain_evidence),
                )
                for index, signal in enumerate(extraction.skills, start=1)
            ],
            interests=[
                InterestSignal(
                    interest_id=f"interest_{index:03d}",
                    label=signal.label,
                    description=signal.description,
                    strength=SignalStrength.MEDIUM,
                    **self._linked_fields(signal, evidence.domain_evidence),
                )
                for index, signal in enumerate(extraction.interests, start=1)
            ],
            values=[
                ValueSignal(
                    value_id=f"value_{index:03d}",
                    label=signal.label,
                    description=signal.description,
                    **self._linked_fields(signal, evidence.domain_evidence),
                )
                for index, signal in enumerate(extraction.values, start=1)
            ],
            goals=[
                Goal(
                    goal_id=f"goal_{index:03d}",
                    label=signal.label,
                    description=signal.description,
                    **self._linked_fields(signal, evidence.domain_evidence),
                )
                for index, signal in enumerate(extraction.goals, start=1)
            ],
            strengths=[
                EvidenceBackedStatement(
                    text=signal.label,
                    **self._linked_fields(signal, evidence.domain_evidence),
                )
                for signal in extraction.strengths
            ],
            development_areas=[
                EvidenceBackedStatement(
                    text=signal.label,
                    **self._linked_fields(signal, evidence.domain_evidence),
                )
                for signal in extraction.development_areas
            ],
            career_preferences=[
                CareerPreference(
                    preference_id=f"preference_{index:03d}",
                    label=signal.label,
                    description=signal.description,
                    **self._linked_fields(signal, evidence.domain_evidence),
                )
                for index, signal in enumerate(extraction.career_preferences, start=1)
            ],
            evidence=evidence.domain_evidence,
            confirmed=False,
        )
        return SelfDiscoveryResult(
            user_profile=profile,
            uncertainties=extraction.profile_uncertainties,
            clarification_questions=extraction.clarification_questions,
            extraction_metadata=extraction_metadata,
            usage=usage,
        )

    @staticmethod
    def _linked_fields(
        signal: SelfDiscoverySignal,
        evidence: Sequence[EvidenceItem],
    ) -> Dict[str, object]:
        evidence_by_id = {item.id: item for item in evidence}
        first_source = evidence_by_id[signal.evidence_ids[0]].source_type
        source_type = (
            first_source
            if signal.inference_type.value == "explicit_fact"
            else EvidenceSourceType.MODEL_INFERENCE
        )
        return {
            "confidence": signal.confidence,
            "evidence_ids": signal.evidence_ids,
            "source_type": source_type,
            "inference_type": signal.inference_type,
            "needs_confirmation": signal.needs_confirmation,
            "confirmed_by_user": False,
        }

    @staticmethod
    def _validate_development_areas(
        extraction: SelfDiscoveryExtraction,
        evidence: Sequence[EvidenceItem],
    ) -> None:
        evidence_by_id = {item.id: item for item in evidence}
        for area in extraction.development_areas:
            if not any(
                bool(evidence_by_id[evidence_id].metadata.get("supports_development_area"))
                for evidence_id in area.evidence_ids
            ):
                raise LLMStructuredOutputError(
                    "发展领域必须由用户明确的有限经验或直接能力缺口证据支持。"
                )
