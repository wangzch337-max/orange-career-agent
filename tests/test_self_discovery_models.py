"""Phase 3 semantic contract boundaries."""

import pytest
from pydantic import ValidationError

from agents.self_discovery_models import (
    CareerPreferenceSignal,
    DevelopmentAreaSignal,
    GoalExtractionSignal,
    InterestExtractionSignal,
    SelfDiscoveryExtraction,
    SelfDiscoverySourceEvidence,
    SkillSignal,
    StrengthSignal,
    ValueExtractionSignal,
)
from data.models import (
    ClarificationQuestion,
    EvidenceSourceType,
    InferenceType,
    ProfileUncertainty,
)
from providers.errors import LLMStructuredOutputError


def source(evidence_id: str = "project_001") -> SelfDiscoverySourceEvidence:
    return SelfDiscoverySourceEvidence(
        id=evidence_id,
        text="虚构公开项目证据",
        source_type=EvidenceSourceType.PROJECT,
        source_name="Synthetic Project",
    )


def skill(**updates) -> SkillSignal:
    values = {
        "label": "Python",
        "description": "公开模拟项目支持这一候选技能。",
        "confidence": 0.8,
        "evidence_ids": ["project_001"],
        "inference_type": InferenceType.EVIDENCE_SUPPORTED_INFERENCE,
    }
    values.update(updates)
    return SkillSignal(**values)


def test_self_discovery_extraction_covers_all_signal_collections() -> None:
    extraction = SelfDiscoveryExtraction(skills=[skill()])
    assert extraction.skills[0].level is None
    assert set(extraction.signal_counts()) == {
        "skills", "interests", "values", "goals", "strengths",
        "development_areas", "career_preferences", "uncertainties",
        "clarification_questions",
    }


@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_signal_confidence_boundaries(value: float) -> None:
    with pytest.raises(ValidationError):
        skill(confidence=value)


def test_strength_requires_positive_evidence_reference() -> None:
    with pytest.raises(ValidationError):
        StrengthSignal(
            label="Testing discipline",
            description="Synthetic",
            confidence=0.7,
            evidence_ids=[],
            inference_type=InferenceType.EVIDENCE_SUPPORTED_INFERENCE,
        )


@pytest.mark.parametrize(
    "signal_type",
    [InterestExtractionSignal, ValueExtractionSignal, GoalExtractionSignal, CareerPreferenceSignal],
)
def test_each_profile_signal_type_requires_grounding(signal_type) -> None:
    with pytest.raises(ValidationError):
        signal_type(
            label="Synthetic",
            description="Synthetic signal",
            confidence=0.7,
            evidence_ids=[],
            inference_type=InferenceType.EXPLICIT_FACT,
        )


def test_development_area_requires_an_allowed_basis() -> None:
    with pytest.raises(ValidationError):
        DevelopmentAreaSignal(
            label="SQL",
            description="Unsupported",
            confidence=0.5,
            evidence_ids=["project_001"],
            inference_type=InferenceType.EVIDENCE_SUPPORTED_INFERENCE,
            basis="absence_of_evidence",
        )


def test_duplicate_evidence_reference_is_rejected() -> None:
    with pytest.raises(ValidationError, match="重复"):
        skill(evidence_ids=["project_001", "project_001"])


def test_explicit_fact_and_inference_are_distinct() -> None:
    assert InferenceType.EXPLICIT_FACT != InferenceType.EVIDENCE_SUPPORTED_INFERENCE
    assert skill().inference_type == InferenceType.EVIDENCE_SUPPORTED_INFERENCE


def test_unknown_signal_evidence_is_rejected() -> None:
    extraction = SelfDiscoveryExtraction(skills=[skill(evidence_ids=["invented_999"])])
    with pytest.raises(LLMStructuredOutputError, match="未知 evidence IDs"):
        extraction.validate_evidence_ids([source()])


def test_unknown_uncertainty_and_question_evidence_is_rejected() -> None:
    extraction = SelfDiscoveryExtraction(
        profile_uncertainties=[ProfileUncertainty(topic="方向", reason="未知", evidence_ids=["missing"])],
        clarification_questions=[ClarificationQuestion(question_id="q1", question="你偏好什么？", topic="preference", reason="需要澄清", related_evidence_ids=["missing"])],
    )
    with pytest.raises(LLMStructuredOutputError):
        extraction.validate_evidence_ids([source()])


def test_clarification_questions_are_limited_to_five() -> None:
    questions = [
        ClarificationQuestion(question_id=f"q{i}", question="一个相关问题？", topic="topic", reason="reason")
        for i in range(6)
    ]
    with pytest.raises(ValidationError):
        SelfDiscoveryExtraction(clarification_questions=questions)


def test_uncertainty_and_question_require_meaningful_text() -> None:
    with pytest.raises(ValidationError):
        ProfileUncertainty(topic="", reason="unknown")
    with pytest.raises(ValidationError):
        ClarificationQuestion(question_id="q", question="", topic="topic", reason="reason")
