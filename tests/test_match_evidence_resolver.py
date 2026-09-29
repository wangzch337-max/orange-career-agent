"""Deterministic evidence ownership tests for Phase 5 Match."""

import pytest
from pydantic import ValidationError

from agents.match_context import MatchContextBuilder
from agents.match_evidence_resolver import MatchEvidenceResolver
from agents.match_insight_demo import (
    build_offline_job_intelligence,
    load_public_profile,
    run_offline_demo,
)
from agents.match_insight_models import (
    BilateralMatchCandidate,
    EvidenceMissingCandidate,
    UnknownMatchCandidate,
    validate_match_insight_candidate,
)
from data.models import MatchDimension, MatchRelationType
from providers.errors import LLMStructuredOutputError


def context_for(title: str = "Data Analyst"):
    profile = load_public_profile()
    intelligence = next(
        item
        for item in build_offline_job_intelligence()
        if item.role_title == title
    )
    return MatchContextBuilder().build(profile, intelligence)


def test_resolver_derives_profile_evidence_from_profile_signal() -> None:
    context = context_for()
    signal = next(item for item in context.profile_signals if item.evidence_ids)
    link = MatchEvidenceResolver().resolve(
        context,
        profile_signal_ids=[signal.signal_id],
        job_signal_ids=[],
    )
    assert link.profile_evidence_ids == signal.evidence_ids
    assert link.job_evidence_ids == []


def test_resolver_derives_job_evidence_from_job_signal() -> None:
    context = context_for()
    signal = next(item for item in context.job_signals if item.evidence_ids)
    link = MatchEvidenceResolver().resolve(
        context,
        profile_signal_ids=[],
        job_signal_ids=[signal.signal_id],
    )
    assert link.job_evidence_ids == signal.evidence_ids
    assert link.profile_evidence_ids == []


def test_multiple_signals_have_stable_deduplicated_evidence_union() -> None:
    context = context_for()
    evidence_ids = [item.evidence_id for item in context.profile_evidence[:3]]
    assert len(evidence_ids) == 3
    first, second = context.profile_signals[:2]
    first = first.model_copy(update={"evidence_ids": evidence_ids[:2]})
    second = second.model_copy(update={"evidence_ids": evidence_ids[1:]})
    context = context.model_copy(update={"profile_signals": [first, second]})
    resolver = MatchEvidenceResolver()
    link = resolver.resolve(
        context,
        profile_signal_ids=[first.signal_id, second.signal_id, first.signal_id],
        job_signal_ids=[],
    )
    assert link.profile_signal_ids == [first.signal_id, second.signal_id]
    assert link.profile_evidence_ids == evidence_ids
    assert resolver.resolve(
        context,
        profile_signal_ids=[first.signal_id, second.signal_id],
        job_signal_ids=[],
    ) == link


def test_unrelated_context_evidence_is_excluded() -> None:
    context = context_for()
    signal = next(item for item in context.profile_signals if item.evidence_ids)
    unrelated = {
        item.evidence_id for item in context.profile_evidence
    } - set(signal.evidence_ids)
    assert unrelated
    link = MatchEvidenceResolver().resolve(
        context,
        profile_signal_ids=[signal.signal_id],
        job_signal_ids=[],
    )
    assert unrelated.isdisjoint(link.profile_evidence_ids)


@pytest.mark.parametrize(
    ("side", "error_code"),
    [
        ("profile", "UNKNOWN_PROFILE_SIGNAL_ID"),
        ("job", "UNKNOWN_JOB_SIGNAL_ID"),
    ],
)
def test_unknown_signal_ids_are_rejected(side: str, error_code: str) -> None:
    kwargs = {
        "profile_signal_ids": ["unknown_profile_signal"] if side == "profile" else [],
        "job_signal_ids": ["unknown_job_signal"] if side == "job" else [],
    }
    with pytest.raises(LLMStructuredOutputError) as caught:
        MatchEvidenceResolver().resolve(context_for(), **kwargs)
    assert caught.value.error_code == error_code


@pytest.mark.parametrize("provider_field", ["evidence_link", "profile_evidence_ids", "job_evidence_ids"])
def test_provider_evidence_fields_are_not_part_of_v3_candidate_schema(
    provider_field: str,
) -> None:
    payload = {
        "candidate_id": "candidate_001",
        "dimension": "capability_alignment",
        "relation_type": "evidence_missing",
        "title": "Missing evidence",
        "description": "Evidence is not currently established.",
        "confidence": 0.8,
        "profile_signal_ids": [],
        "job_signal_ids": ["job_signal_001"],
        "needs_user_review": True,
        provider_field: {} if provider_field == "evidence_link" else ["wrong_evidence"],
    }
    with pytest.raises(ValidationError) as caught:
        validate_match_insight_candidate(payload)
    assert any(error["type"] == "extra_forbidden" for error in caught.value.errors())


def test_previous_wrong_job_evidence_cannot_enter_via_non_owner_signal() -> None:
    context = context_for("Data Analyst")
    evidence_id = "job_013_summary_001"
    assert evidence_id in {item.evidence_id for item in context.job_evidence}
    non_owner = next(
        signal for signal in context.job_signals if evidence_id not in signal.evidence_ids
    )
    link = MatchEvidenceResolver().resolve(
        context,
        profile_signal_ids=[],
        job_signal_ids=[non_owner.signal_id],
    )
    assert evidence_id not in link.job_evidence_ids


def test_all_public_match_evidence_is_exactly_owned_by_referenced_signals() -> None:
    profile = load_public_profile()
    contexts = {
        item.job_id: MatchContextBuilder().build(profile, item)
        for item in build_offline_job_intelligence()
    }
    results = run_offline_demo()
    assert len(results) == 20
    for intelligence, result, _ in results:
        context = contexts[intelligence.job_id]
        for insight in result.insights():
            expected = MatchEvidenceResolver().resolve(
                context,
                profile_signal_ids=insight.evidence_link.profile_signal_ids,
                job_signal_ids=insight.evidence_link.job_signal_ids,
            )
            assert insight.evidence_link == expected


def test_candidate_retains_semantics_but_not_evidence_ownership() -> None:
    common_fields = {
        "candidate_id",
        "dimension",
        "relation_type",
        "title",
        "description",
        "confidence",
        "profile_signal_ids",
        "job_signal_ids",
        "needs_user_review",
    }
    for family in (
        BilateralMatchCandidate,
        EvidenceMissingCandidate,
        UnknownMatchCandidate,
    ):
        assert set(family.model_fields) == common_fields
    candidate = validate_match_insight_candidate(
        {
            "candidate_id": "candidate_001",
            "dimension": MatchDimension.EXPERIENCE_EVIDENCE,
            "relation_type": MatchRelationType.UNKNOWN,
            "title": "Unknown",
            "description": "Information remains unknown.",
            "confidence": 1.0,
            "job_signal_ids": ["job_signal_001"],
        }
    )
    assert candidate.job_signal_ids == ["job_signal_001"]
