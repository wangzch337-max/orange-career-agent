"""Evidence and action-policy validation around LLM-proposed Match candidates."""

import pytest
from pydantic import ValidationError

from agents.match_context import MatchContextBuilder
from agents.match_insight import public_offline_match_extraction
from agents.match_insight_assembler import MatchInsightAssembler
from agents.match_insight_demo import build_offline_job_intelligence, load_public_profile
from agents.match_insight_models import MatchInsightExtraction
from data.models import ActionType, MatchRelationType, MatchResult
from providers.errors import LLMStructuredOutputError
from workflows.stages import ProfileNotConfirmedError


def case(title: str = "AI Product Intern"):
    profile = load_public_profile()
    intelligence = next(
        item for item in build_offline_job_intelligence() if item.role_title == title
    )
    context = MatchContextBuilder().build(profile, intelligence)
    extraction = public_offline_match_extraction(context)
    return profile, context, extraction


def assemble(title: str = "AI Product Intern"):
    profile, context, extraction = case(title)
    result = MatchInsightAssembler().assemble(
        profile=profile,
        context=context,
        extraction=extraction,
        analysis_metadata={"provider": "fake"},
    )
    return result, profile, context, extraction


def test_assembler_rejects_unconfirmed_profile() -> None:
    from data.models import UserProfile
    _, context, extraction = case()
    with pytest.raises(ProfileNotConfirmedError, match="已确认"):
        MatchInsightAssembler().assemble(
            profile=UserProfile(profile_id="draft"),
            context=context,
            extraction=extraction,
            analysis_metadata={},
        )


@pytest.mark.parametrize(
    ("signal_field", "bad_id"),
    [
        ("profile_signal_ids", "unknown_profile_signal"),
        ("job_signal_ids", "unknown_job_signal"),
    ],
)
def test_unknown_match_ids_are_rejected(signal_field, bad_id) -> None:
    profile, context, extraction = case()
    payload = extraction.model_dump()
    candidate = payload["candidate_alignments"][0]
    candidate[signal_field] = [bad_id]
    modified = MatchInsightExtraction.model_validate(payload)
    with pytest.raises(LLMStructuredOutputError):
        MatchInsightAssembler().assemble(
            profile=profile, context=context, extraction=modified, analysis_metadata={}
        )


def test_assembler_resolves_links_and_preserves_confidence_and_relation_type() -> None:
    result, _, context, extraction = assemble()
    source = extraction.candidate_alignments[0]
    assembled = next(item for item in result.insights() if item.insight_id == source.candidate_id)
    profile_by_id = {item.signal_id: item for item in context.profile_signals}
    job_by_id = {item.signal_id: item for item in context.job_signals}
    assert assembled.evidence_link.profile_signal_ids == source.profile_signal_ids
    assert assembled.evidence_link.job_signal_ids == source.job_signal_ids
    assert assembled.evidence_link.profile_evidence_ids == [
        evidence_id
        for signal_id in source.profile_signal_ids
        for evidence_id in profile_by_id[signal_id].evidence_ids
    ]
    assert assembled.evidence_link.job_evidence_ids == [
        evidence_id
        for signal_id in source.job_signal_ids
        for evidence_id in job_by_id[signal_id].evidence_ids
    ]
    assert assembled.confidence == source.confidence
    assert assembled.relation_type == source.relation_type


def test_assembler_never_creates_overall_score_or_ranking() -> None:
    forbidden = {"overall_score", "match_score", "fit_score", "ranking", "recommended_role"}
    assert forbidden.isdisjoint(MatchResult.model_fields)
    result, _, _, _ = assemble()
    assert forbidden.isdisjoint(result.model_dump())
    assert all("score" not in name and "fit" not in name for name in type(result.coverage_metrics).model_fields)


def test_confirmed_gap_requires_positive_development_area_evidence() -> None:
    profile, context, extraction = case("Data Analyst")
    payload = extraction.model_dump()
    gap = next(
        item for item in payload["candidate_gaps"]
        if item["relation_type"] == "confirmed_gap"
    )
    gap["profile_signal_ids"] = ["skill_python_001"]
    with pytest.raises(LLMStructuredOutputError, match="development-area"):
        MatchInsightAssembler().assemble(
            profile=profile,
            context=context,
            extraction=MatchInsightExtraction.model_validate(payload),
            analysis_metadata={},
        )


def test_experience_depth_gap_requires_existing_experience_signal() -> None:
    profile, context, extraction = case("AI Application Engineer")
    payload = extraction.model_dump()
    depth = next(
        item for item in payload["candidate_gaps"]
        if item["relation_type"] == "experience_depth_gap"
    )
    depth["profile_signal_ids"] = []
    with pytest.raises(ValidationError) as caught:
        MatchInsightExtraction.model_validate(payload)
    assert any(error["type"] == "too_short" for error in caught.value.errors())


def test_preference_alignment_requires_confirmed_preference() -> None:
    profile, context, extraction = case()
    payload = extraction.model_dump()
    preference = next(
        item for item in payload["candidate_alignments"]
        if item["relation_type"] == "preference_alignment"
    )
    preference["profile_signal_ids"] = ["skill_python_001"]
    with pytest.raises(LLMStructuredOutputError, match="career preference"):
        MatchInsightAssembler().assemble(
            profile=profile,
            context=context,
            extraction=MatchInsightExtraction.model_validate(payload),
            analysis_metadata={},
        )


def test_potential_friction_requires_preference_or_value() -> None:
    profile, context, extraction = case("AI Solutions Consultant")
    payload = extraction.model_dump()
    friction = payload["candidate_frictions"][0]
    friction["profile_signal_ids"] = ["skill_python_001"]
    with pytest.raises(LLMStructuredOutputError, match="preference"):
        MatchInsightAssembler().assemble(
            profile=profile,
            context=context,
            extraction=MatchInsightExtraction.model_validate(payload),
            analysis_metadata={},
        )


def test_evidence_missing_verify_and_build_actions_are_accepted() -> None:
    result, profile, context, extraction = assemble()
    assert any(item.action_type == ActionType.VERIFY_EXISTING_CAPABILITY for item in result.action_items)
    payload = extraction.model_dump()
    verify = next(item for item in payload["candidate_actions"] if item["action_type"] == "verify_existing_capability")
    verify["action_type"] = "build_portfolio_evidence"
    accepted = MatchInsightAssembler().assemble(
        profile=profile,
        context=context,
        extraction=MatchInsightExtraction.model_validate(payload),
        analysis_metadata={},
    )
    assert any(item.action_type == ActionType.BUILD_PORTFOLIO_EVIDENCE for item in accepted.action_items)


def test_evidence_missing_cannot_become_deepen_capability_action() -> None:
    _, profile, context, extraction = assemble()
    payload = extraction.model_dump()
    verify = next(item for item in payload["candidate_actions"] if item["action_type"] == "verify_existing_capability")
    verify["action_type"] = "deepen_capability"
    with pytest.raises(LLMStructuredOutputError):
        MatchInsightAssembler().assemble(
            profile=profile,
            context=context,
            extraction=MatchInsightExtraction.model_validate(payload),
            analysis_metadata={},
        )


def test_confirmed_gap_deepen_and_depth_gap_practical_experience_are_accepted() -> None:
    data_result, _, _, _ = assemble("Data Analyst")
    engineering_result, _, _, _ = assemble("AI Application Engineer")
    assert any(item.action_type == ActionType.DEEPEN_CAPABILITY for item in data_result.action_items)
    assert any(item.action_type == ActionType.GAIN_PRACTICAL_EXPERIENCE for item in engineering_result.action_items)


def test_unsupported_trendy_skill_action_is_rejected() -> None:
    _, profile, context, extraction = assemble()
    payload = extraction.model_dump()
    payload["candidate_actions"][0]["target_label"] = "Kubernetes"
    with pytest.raises(LLMStructuredOutputError, match="target"):
        MatchInsightAssembler().assemble(
            profile=profile,
            context=context,
            extraction=MatchInsightExtraction.model_validate(payload),
            analysis_metadata={},
        )


def test_unknown_action_must_reference_a_known_issue() -> None:
    _, profile, context, extraction = assemble()
    payload = extraction.model_dump()
    payload["candidate_actions"][-1]["related_insight_ids"] = ["invented_issue"]
    modified = MatchInsightExtraction.model_validate(payload)
    with pytest.raises(LLMStructuredOutputError, match="未知 insight"):
        MatchInsightAssembler().assemble(
            profile=profile, context=context, extraction=modified, analysis_metadata={}
        )


def test_unknown_can_clarify_preference_when_dimension_is_appropriate() -> None:
    _, profile, context, extraction = assemble()
    payload = extraction.model_dump()
    unknown = payload["candidate_unknowns"][0]
    unknown["dimension"] = "career_preference_alignment"
    unknown["profile_signal_ids"] = ["preference_hands_on_001"]
    action = payload["candidate_actions"][-1]
    action["action_type"] = "clarify_preference"
    action["target_label"] = "Hands-on implementation"
    result = MatchInsightAssembler().assemble(
        profile=profile,
        context=context,
        extraction=MatchInsightExtraction.model_validate(payload),
        analysis_metadata={},
    )
    assert result.action_items[-1].action_type == ActionType.CLARIFY_PREFERENCE
