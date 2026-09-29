"""Phase 5 taxonomy and strict relationship contract tests."""

import pytest
from pydantic import ValidationError

from agents.match_insight_models import (
    MatchInsightExtraction,
    validate_match_insight_candidate,
)
from data.models import (
    ActionItem,
    ActionType,
    ConfirmedGap,
    EvidenceGap,
    ExperienceDepthGap,
    MatchDimension,
    MatchEvidenceLink,
    MatchInsight,
    MatchRelationType,
    Severity,
)


def link(*, profile=True, job=True) -> MatchEvidenceLink:
    return MatchEvidenceLink(
        profile_signal_ids=["skill_001"] if profile else [],
        profile_evidence_ids=["profile_ev_001"] if profile else [],
        job_signal_ids=["job_req_001"] if job else [],
        job_evidence_ids=["job_ev_001"] if job else [],
    )


def insight(relation: MatchRelationType, evidence_link: MatchEvidenceLink) -> MatchInsight:
    return MatchInsight(
        insight_id="insight_001",
        dimension=MatchDimension.CAPABILITY_ALIGNMENT,
        relation_type=relation,
        title="Evidence relationship",
        description="Bounded description.",
        confidence=0.8,
        evidence_link=evidence_link,
    )


def test_match_dimension_taxonomy_and_chinese_labels() -> None:
    assert len(MatchDimension) == 6
    assert MatchDimension.CAPABILITY_ALIGNMENT.display_name_zh == "能力匹配"


def test_match_relation_taxonomy_and_chinese_labels() -> None:
    assert len(MatchRelationType) == 8
    assert MatchRelationType.EVIDENCE_MISSING.display_name_zh == "证据不足"


def test_match_evidence_link_rejects_duplicate_ids() -> None:
    with pytest.raises(ValidationError):
        MatchEvidenceLink(profile_signal_ids=["skill_001", "skill_001"])


def test_strong_alignment_requires_user_and_job_evidence() -> None:
    with pytest.raises(ValidationError):
        insight(MatchRelationType.STRONG_ALIGNMENT, link(profile=False))
    assert insight(MatchRelationType.STRONG_ALIGNMENT, link()).relation_type == MatchRelationType.STRONG_ALIGNMENT


def test_partial_alignment_requires_both_sides() -> None:
    with pytest.raises(ValidationError):
        insight(MatchRelationType.PARTIAL_ALIGNMENT, link(job=False))


def test_evidence_missing_requires_job_evidence_but_not_user_evidence() -> None:
    item = insight(MatchRelationType.EVIDENCE_MISSING, link(profile=False))
    assert item.evidence_link.profile_evidence_ids == []
    with pytest.raises(ValidationError):
        insight(MatchRelationType.EVIDENCE_MISSING, link(job=False))


def test_evidence_gap_is_not_confirmed_gap() -> None:
    evidence_gap = EvidenceGap.model_validate(
        insight(MatchRelationType.EVIDENCE_MISSING, link(profile=False)).model_dump()
    )
    assert evidence_gap.relation_type != MatchRelationType.CONFIRMED_GAP
    with pytest.raises(ValidationError):
        ConfirmedGap.model_validate(evidence_gap.model_dump())


def test_confirmed_and_depth_gap_models_are_distinct() -> None:
    confirmed = ConfirmedGap.model_validate(
        insight(MatchRelationType.CONFIRMED_GAP, link()).model_dump()
    )
    depth = ExperienceDepthGap.model_validate(
        insight(MatchRelationType.EXPERIENCE_DEPTH_GAP, link()).model_dump()
    )
    assert confirmed.relation_type != depth.relation_type


def test_unknown_requires_at_least_one_reference() -> None:
    with pytest.raises(ValidationError):
        insight(MatchRelationType.UNKNOWN, MatchEvidenceLink())
    assert insight(
        MatchRelationType.UNKNOWN,
        MatchEvidenceLink(job_signal_ids=["unknown_topic_001"]),
    )


def test_confidence_bounds_apply_to_match_candidates() -> None:
    with pytest.raises(ValidationError):
        validate_match_insight_candidate(
            {
                "candidate_id": "candidate_001",
                "dimension": MatchDimension.INTEREST_ALIGNMENT,
                "relation_type": MatchRelationType.UNKNOWN,
                "title": "Unknown",
                "description": "Unknown",
                "confidence": 1.01,
                "job_signal_ids": ["job_signal_001"],
            }
        )


def test_match_extraction_has_bounded_named_collections() -> None:
    extraction = MatchInsightExtraction()
    assert extraction.insights() == []
    assert set(type(extraction).model_fields) == {
        "candidate_alignments", "candidate_gaps", "candidate_frictions",
        "candidate_unknowns", "candidate_actions",
    }


def test_action_item_requires_related_issue_and_small_taxonomy() -> None:
    assert len(ActionType) == 6
    with pytest.raises(ValidationError):
        ActionItem(
            action_id="action_001",
            action_type=ActionType.VERIFY_EXISTING_CAPABILITY,
            description="Verify evidence.",
            rationale="Evidence is missing.",
            priority=Severity.MEDIUM,
            expected_evidence="A reviewable artifact.",
            target_label="SQL",
            related_insight_ids=[],
        )
