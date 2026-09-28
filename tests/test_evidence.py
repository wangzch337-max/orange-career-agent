"""Evidence-first 与 provenance 关系测试。"""

import pytest
from pydantic import ValidationError

from data.models import (
    CandidateSkill,
    EvidenceItem,
    EvidenceSourceType,
    UserProfile,
)


def test_model_inference_is_distinct_from_explicit_fact() -> None:
    assert EvidenceSourceType.MODEL_INFERENCE != EvidenceSourceType.EXPLICIT_USER_INPUT


def test_profile_rejects_missing_evidence_relationship() -> None:
    skill = CandidateSkill(
        skill_id="skill_demo",
        label="Demo Skill",
        confidence=0.7,
        evidence_ids=["ev_missing"],
        source_type=EvidenceSourceType.COURSE,
    )
    with pytest.raises(ValidationError, match="不存在的 evidence IDs"):
        UserProfile(profile_id="profile_test", skills=[skill])


def test_profile_accepts_resolvable_evidence_relationship() -> None:
    evidence = EvidenceItem(
        id="ev_course_01",
        source_type=EvidenceSourceType.COURSE,
        source_name="Demo Course",
        statement="完成公开课程案例。",
        confidence=1.0,
    )
    skill = CandidateSkill(
        skill_id="skill_demo",
        label="Demo Skill",
        confidence=0.7,
        evidence_ids=[evidence.id],
        source_type=EvidenceSourceType.COURSE,
    )
    profile = UserProfile(profile_id="profile_test", skills=[skill], evidence=[evidence])
    assert profile.skills[0].evidence_ids == [evidence.id]


def test_evidence_metadata_must_be_json_serializable() -> None:
    with pytest.raises(ValidationError):
        EvidenceItem(
            id="ev_bad_metadata",
            source_type=EvidenceSourceType.SYSTEM_FIXTURE,
            source_name="test",
            statement="测试",
            confidence=1.0,
            metadata={"not_json": object()},
        )
