"""Public synthetic profile safety and relation coverage."""

import re

from agents.match_insight_demo import load_public_profile, run_offline_demo
from data.models import MatchRelationType, ProfileStatus


def test_public_synthetic_profile_is_confirmed_and_sanitized() -> None:
    profile = load_public_profile()
    assert profile.confirmed is True
    assert profile.status == ProfileStatus.CONFIRMED
    text = profile.model_dump_json()
    assert not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    assert not re.search(r"\b(?:student[_ -]?id|phone|address)\b", text, re.I)
    assert not re.search(r"\b[569]\d{7}\b", text)


def test_public_profile_exercises_every_relation_category_across_twenty_roles() -> None:
    relations = {
        insight.relation_type
        for _, result, _ in run_offline_demo()
        for insight in result.insights()
    }
    assert relations == set(MatchRelationType)


def test_every_public_action_traces_to_a_validated_issue() -> None:
    issue_types = {
        MatchRelationType.EVIDENCE_MISSING,
        MatchRelationType.CONFIRMED_GAP,
        MatchRelationType.EXPERIENCE_DEPTH_GAP,
        MatchRelationType.POTENTIAL_FRICTION,
        MatchRelationType.UNKNOWN,
    }
    for _, result, _ in run_offline_demo():
        insight_by_id = {item.insight_id: item for item in result.insights()}
        for action in result.action_items:
            assert action.related_insight_ids
            assert all(
                insight_by_id[insight_id].relation_type in issue_types
                for insight_id in action.related_insight_ids
            )
