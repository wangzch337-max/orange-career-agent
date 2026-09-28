"""Deterministic ProfileAssembler safety and provenance tests."""

import pytest

from agents.profile_assembler import ProfileAssembler
from agents.self_discovery import public_offline_extraction
from agents.self_discovery_evidence import SourceEvidenceBuilder
from agents.self_discovery_models import DevelopmentAreaSignal, SelfDiscoveryExtraction
from data.models import CourseRecord, EvidenceSourceType, InferenceType, ProfileStatus
from providers.errors import LLMStructuredOutputError
from providers.models import LLMUsage
from workflows.demo import load_user_input


def bundle():
    courses = [
        CourseRecord(course_id="a", title="A", summary="Synthetic A"),
        CourseRecord(course_id="b", title="B", summary="Synthetic B"),
        CourseRecord(course_id="c", title="C", summary="Synthetic C"),
    ]
    return SourceEvidenceBuilder().build(load_user_input(), courses)


def assemble(extraction=None):
    return ProfileAssembler().assemble(
        profile_id="profile_test",
        extraction=extraction or public_offline_extraction(),
        evidence=bundle(),
        extraction_metadata={"provider": "fake"},
        usage=LLMUsage(),
    )


def test_assembler_produces_unconfirmed_user_profile_v1() -> None:
    profile = assemble().user_profile
    assert profile.version == 1
    assert profile.status == ProfileStatus.DRAFT
    assert profile.confirmed is False


def test_assembler_preserves_evidence_confidence_and_inference() -> None:
    skill = assemble().user_profile.skills[0]
    assert skill.evidence_ids == ["course_001"]
    assert skill.confidence == 0.82
    assert skill.inference_type == InferenceType.EVIDENCE_SUPPORTED_INFERENCE
    assert skill.source_type == EvidenceSourceType.MODEL_INFERENCE


def test_assembler_maps_explicit_fact_without_turning_it_into_inference() -> None:
    interest = assemble().user_profile.interests[0]
    assert interest.inference_type == InferenceType.EXPLICIT_FACT
    assert interest.source_type == EvidenceSourceType.EXPLICIT_USER_INPUT


def test_assembler_preserves_career_preferences() -> None:
    profile = assemble().user_profile
    assert len(profile.career_preferences) == 1
    assert profile.career_preferences[0].evidence_ids == ["career_001", "career_002"]


def test_assembler_does_not_invent_extra_signals() -> None:
    result = assemble(SelfDiscoveryExtraction())
    assert result.user_profile.skills == []
    assert result.user_profile.development_areas == []


def test_unsupported_development_area_is_rejected() -> None:
    extraction = SelfDiscoveryExtraction(
        development_areas=[
            DevelopmentAreaSignal(
                label="SQL",
                description="No direct gap evidence",
                confidence=0.4,
                evidence_ids=["course_001"],
                inference_type=InferenceType.EVIDENCE_SUPPORTED_INFERENCE,
                basis="direct_capability_gap",
            )
        ]
    )
    with pytest.raises(LLMStructuredOutputError, match="发展领域"):
        assemble(extraction)


def test_explicit_development_area_can_be_assembled() -> None:
    payload = load_user_input()
    payload["explicit_development_areas"] = ["明确说明有限的演讲经验。"]
    evidence = SourceEvidenceBuilder().build(payload, [])
    extraction = SelfDiscoveryExtraction(
        development_areas=[DevelopmentAreaSignal(label="公开演讲经验", description="用户明确说明经验有限。", confidence=1.0, evidence_ids=["development_001"], inference_type=InferenceType.EXPLICIT_FACT, basis="explicit_limited_experience")]
    )
    result = ProfileAssembler().assemble(profile_id="p", extraction=extraction, evidence=evidence, extraction_metadata={}, usage=LLMUsage())
    assert len(result.user_profile.development_areas) == 1
