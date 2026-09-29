"""Minimal confirmed-profile MatchContext construction tests."""

import pytest

from agents.match_context import MatchContextBuilder
from agents.match_insight_demo import build_offline_job_intelligence, load_public_profile
from data.models import EvidenceItem, EvidenceSourceType, UserProfile
from workflows.stages import ProfileNotConfirmedError


def test_context_builder_rejects_unconfirmed_profile() -> None:
    with pytest.raises(ProfileNotConfirmedError):
        MatchContextBuilder().build(
            UserProfile(profile_id="draft_profile"),
            build_offline_job_intelligence()[0],
        )


def test_context_builder_accepts_confirmed_profile() -> None:
    profile = load_public_profile()
    context = MatchContextBuilder().build(profile, build_offline_job_intelligence()[0])
    assert context.profile_id == profile.profile_id
    assert context.profile_signals
    assert context.job_signals


def test_context_exposes_only_evidence_referenced_by_comparison_signals() -> None:
    profile = load_public_profile()
    extra = EvidenceItem(
        id="irrelevant_private_history",
        source_type=EvidenceSourceType.CONVERSATION,
        source_name="Unused history",
        statement="This evidence is intentionally not linked to a profile signal.",
        confidence=1.0,
    )
    profile = profile.model_copy(update={"evidence": [*profile.evidence, extra]})
    context = MatchContextBuilder().build(profile, build_offline_job_intelligence()[0])
    assert "irrelevant_private_history" not in {
        item.evidence_id for item in context.profile_evidence
    }


def test_profile_and_job_signal_ids_are_stable_and_unique() -> None:
    profile = load_public_profile()
    intelligence = build_offline_job_intelligence()[0]
    builder = MatchContextBuilder()
    first = builder.build(profile, intelligence)
    second = builder.build(profile, intelligence)
    assert [item.signal_id for item in first.profile_signals] == [
        item.signal_id for item in second.profile_signals
    ]
    assert len({item.signal_id for item in first.job_signals}) == len(first.job_signals)
    assert all("[" not in item.signal_id for item in [*first.profile_signals, *first.job_signals])
