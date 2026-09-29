"""Safe diagnostics and prompt/schema consistency for Phase 5 Match."""

import pytest
from pydantic import ValidationError

from agents.match_context import MatchContextBuilder
from agents.match_evidence_resolver import MatchEvidenceResolver
from agents.match_insight import public_offline_match_extraction
from agents.match_insight_assembler import MatchInsightAssembler
from agents.match_insight_demo import build_offline_job_intelligence, load_public_profile
from agents.match_insight_models import (
    BilateralMatchCandidate,
    EvidenceMissingCandidate,
    JobSignalCategory,
    MatchInsightCandidate,
    MatchInsightExtraction,
    NormalizedMatchCandidate,
    ProfileSignalCategory,
    UnknownMatchCandidate,
    validate_match_insight_candidate,
)
from data.models import (
    ActionType,
    MatchDimension,
    MatchRelationType,
)
from providers.errors import LLMStructuredOutputError
from providers.fake import FakeLLMProvider
from providers.models import GenerationOptions, LLMMessage, MessageRole
from providers.prompts import load_match_insight_prompt


def match_case(title: str = "Data Analyst"):
    profile = load_public_profile()
    intelligence = next(
        item for item in build_offline_job_intelligence()
        if item.role_title == title
    )
    context = MatchContextBuilder().build(profile, intelligence)
    return profile, intelligence, context


def ref(context, category, *, profile: bool):
    items = context.profile_signals if profile else context.job_signals
    return next(item for item in items if item.category == category)


def signal_ids(profile_ref=None, job_ref=None) -> dict[str, list[str]]:
    return {
        "profile_signal_ids": [profile_ref.signal_id] if profile_ref else [],
        "job_signal_ids": [job_ref.signal_id] if job_ref else [],
    }


def candidate(
    relation: MatchRelationType,
    dimension: MatchDimension,
    signals: dict[str, list[str]],
) -> MatchInsightCandidate:
    return validate_match_insight_candidate(
        {
            "candidate_id": f"candidate_{relation.value}",
            "dimension": dimension,
            "relation_type": relation,
            "title": "Synthetic evidence relation",
            "description": "A public synthetic relation for deterministic validation.",
            "confidence": 0.8,
            **signals,
        }
    )


def extraction_for(item: MatchInsightCandidate) -> MatchInsightExtraction:
    if item.relation_type in {
        MatchRelationType.STRONG_ALIGNMENT,
        MatchRelationType.PARTIAL_ALIGNMENT,
        MatchRelationType.PREFERENCE_ALIGNMENT,
    }:
        return MatchInsightExtraction(candidate_alignments=[item])
    if item.relation_type in {
        MatchRelationType.EVIDENCE_MISSING,
        MatchRelationType.CONFIRMED_GAP,
        MatchRelationType.EXPERIENCE_DEPTH_GAP,
    }:
        return MatchInsightExtraction(candidate_gaps=[item])
    if item.relation_type == MatchRelationType.POTENTIAL_FRICTION:
        return MatchInsightExtraction(candidate_frictions=[item])
    return MatchInsightExtraction(candidate_unknowns=[item])


def valid_candidate_for(context, relation: MatchRelationType) -> MatchInsightCandidate:
    skill = ref(context, ProfileSignalCategory.SKILL, profile=True)
    development = ref(context, ProfileSignalCategory.DEVELOPMENT_AREA, profile=True)
    preference = ref(context, ProfileSignalCategory.CAREER_PREFERENCE, profile=True)
    value = ref(context, ProfileSignalCategory.VALUE, profile=True)
    required = ref(context, JobSignalCategory.REQUIRED_CAPABILITY, profile=False)
    actual = ref(context, JobSignalCategory.ACTUAL_WORK, profile=False)
    cases = {
        MatchRelationType.STRONG_ALIGNMENT: (
            MatchDimension.CAPABILITY_ALIGNMENT,
            signal_ids(skill, required),
        ),
        MatchRelationType.PARTIAL_ALIGNMENT: (
            MatchDimension.GROWTH_OPPORTUNITY,
            signal_ids(skill, actual),
        ),
        MatchRelationType.EVIDENCE_MISSING: (
            MatchDimension.CAPABILITY_ALIGNMENT,
            signal_ids(job_ref=required),
        ),
        MatchRelationType.CONFIRMED_GAP: (
            MatchDimension.CAPABILITY_ALIGNMENT,
            signal_ids(development, required),
        ),
        MatchRelationType.EXPERIENCE_DEPTH_GAP: (
            MatchDimension.EXPERIENCE_EVIDENCE,
            signal_ids(skill, actual),
        ),
        MatchRelationType.PREFERENCE_ALIGNMENT: (
            MatchDimension.CAREER_PREFERENCE_ALIGNMENT,
            signal_ids(preference, actual),
        ),
        MatchRelationType.POTENTIAL_FRICTION: (
            MatchDimension.VALUE_WORKSTYLE_ALIGNMENT,
            signal_ids(value, actual),
        ),
        MatchRelationType.UNKNOWN: (
            MatchDimension.EXPERIENCE_EVIDENCE,
            signal_ids(job_ref=actual),
        ),
    }
    dimension, link = cases[relation]
    return candidate(relation, dimension, link)


def test_pydantic_diagnostic_exposes_structure_without_raw_input() -> None:
    raw_private_value = "raw-private-invalid-relation"
    payload = {
        "candidate_alignments": [
            {
                "candidate_id": "candidate_001",
                "dimension": "capability_alignment",
                "relation_type": raw_private_value,
                "title": "Synthetic",
                "description": "Synthetic",
                "confidence": 0.8,
                "profile_signal_ids": [],
                "job_signal_ids": [],
                "needs_user_review": True,
            }
        ]
    }
    provider = FakeLLMProvider(payload)
    with pytest.raises(LLMStructuredOutputError) as caught:
        provider.generate_structured(
            [LLMMessage(role=MessageRole.USER, content="sanitized")],
            MatchInsightExtraction,
            GenerationOptions(model="fake", max_retries=0),
            prompt_name="match_insight",
            prompt_version="v1",
        )
    assert isinstance(caught.value.__cause__, ValidationError)
    diagnostic = caught.value.safe_diagnostics()[0]
    assert diagnostic == {
        "stage": "MatchInsightExtraction",
        "error_code": "PYDANTIC_FIELD_INVALID",
        "message": "Input should use a supported relation discriminator.",
        "loc": "candidate_alignments.0",
        "type": "union_tag_invalid",
    }
    assert raw_private_value not in repr(caught.value.safe_diagnostics())


def test_duplicate_candidate_id_has_focused_pydantic_code() -> None:
    _, _, context = match_case()
    first = valid_candidate_for(context, MatchRelationType.STRONG_ALIGNMENT)
    second = first.model_copy(update={"title": "Second synthetic candidate"})
    with pytest.raises(ValidationError) as raw_error:
        MatchInsightExtraction(candidate_alignments=[first, second])
    diagnostic_error = LLMStructuredOutputError.from_pydantic(
        stage="MatchInsightExtraction",
        error=raw_error.value,
    )
    assert diagnostic_error.safe_diagnostics()[0]["error_code"] == "DUPLICATE_CANDIDATE_ID"


def test_prompt_fields_and_serialized_enums_match_schema() -> None:
    prompt = load_match_insight_prompt()
    for enum_type in (MatchDimension, MatchRelationType, ActionType):
        for item in enum_type:
            assert f"`{item.value}`" in prompt
    for field_name in NormalizedMatchCandidate.model_fields:
        assert f"`{field_name}`" in prompt
    for family in (
        BilateralMatchCandidate,
        EvidenceMissingCandidate,
        UnknownMatchCandidate,
    ):
        assert "relation_type" in family.model_fields
    for field_name in MatchInsightExtraction.model_fields:
        assert f"`{field_name}`" in prompt


def test_prompt_visible_id_namespaces_round_trip_through_assembler() -> None:
    profile, intelligence, context = match_case("AI Product Intern")
    extraction = public_offline_match_extraction(context)
    extraction.validate_context(context)
    result = MatchInsightAssembler().assemble(
        profile=profile,
        context=context,
        extraction=MatchInsightExtraction.model_validate(extraction.model_dump()),
        analysis_metadata={},
    )
    assert result.insights()
    valid_targets = {
        item.label for item in [*context.profile_signals, *context.job_signals]
    }
    assert all(item.target_label in valid_targets for item in result.action_items)


@pytest.mark.parametrize("relation", list(MatchRelationType))
def test_every_relation_has_a_valid_minimum_contract(relation: MatchRelationType) -> None:
    profile, _, context = match_case()
    item = valid_candidate_for(context, relation)
    result = MatchInsightAssembler().assemble(
        profile=profile,
        context=context,
        extraction=extraction_for(item),
        analysis_metadata={},
    )
    assert result.insights()[0].relation_type == relation
    assert result.insights()[0].dimension == item.dimension


@pytest.mark.parametrize(
    ("relation", "missing_side", "error_code"),
    [
        (MatchRelationType.STRONG_ALIGNMENT, "profile", "RELATION_REQUIRES_PROFILE_SIGNAL"),
        (MatchRelationType.PARTIAL_ALIGNMENT, "job", "RELATION_REQUIRES_JOB_SIGNAL"),
        (MatchRelationType.EVIDENCE_MISSING, "job", "RELATION_REQUIRES_JOB_SIGNAL"),
        (MatchRelationType.CONFIRMED_GAP, "profile", "RELATION_REQUIRES_PROFILE_SIGNAL"),
        (
            MatchRelationType.EXPERIENCE_DEPTH_GAP,
            "profile",
            "EXPERIENCE_DEPTH_GAP_WITHOUT_BASE_EXPERIENCE",
        ),
        (MatchRelationType.PREFERENCE_ALIGNMENT, "profile", "RELATION_REQUIRES_PROFILE_SIGNAL"),
        (MatchRelationType.POTENTIAL_FRICTION, "job", "RELATION_REQUIRES_JOB_SIGNAL"),
    ],
)
def test_relation_missing_side_has_safe_diagnostic(
    relation: MatchRelationType,
    missing_side: str,
    error_code: str,
) -> None:
    profile, _, context = match_case()
    source = valid_candidate_for(context, relation)
    payload = source.model_dump()
    payload[f"{missing_side}_signal_ids"] = []
    item = NormalizedMatchCandidate.model_validate(payload)
    link = MatchEvidenceResolver().resolve(
        context,
        profile_signal_ids=item.profile_signal_ids,
        job_signal_ids=item.job_signal_ids,
    )
    with pytest.raises(LLMStructuredOutputError) as caught:
        MatchInsightAssembler()._validate_required_references(item, link)
    assert caught.value.error_code == error_code
    assert caught.value.safe_diagnostics()[0]["identifier"] == item.candidate_id


def test_unknown_without_any_reference_has_safe_diagnostic() -> None:
    profile, _, context = match_case()
    item = NormalizedMatchCandidate(
        candidate_id="candidate_unknown",
        dimension=MatchDimension.EXPERIENCE_EVIDENCE,
        relation_type=MatchRelationType.UNKNOWN,
        title="Synthetic evidence relation",
        description="A public synthetic relation for deterministic validation.",
        confidence=0.8,
    )
    link = MatchEvidenceResolver().resolve(
        context,
        profile_signal_ids=[],
        job_signal_ids=[],
    )
    with pytest.raises(LLMStructuredOutputError) as caught:
        MatchInsightAssembler()._validate_required_references(item, link)
    assert caught.value.error_code == "RELATION_REQUIRES_REFERENCE"


def test_unknown_id_namespaces_have_focused_error_codes() -> None:
    _, _, context = match_case()
    base = valid_candidate_for(context, MatchRelationType.STRONG_ALIGNMENT)
    fields = {
        "profile_signal_ids": "UNKNOWN_PROFILE_SIGNAL_ID",
        "job_signal_ids": "UNKNOWN_JOB_SIGNAL_ID",
    }
    for field_name, expected_code in fields.items():
        payload = base.model_dump()
        payload[field_name] = [f"unknown_{field_name}"]
        extraction = extraction_for(validate_match_insight_candidate(payload))
        with pytest.raises(LLMStructuredOutputError) as caught:
            extraction.validate_context(context)
        assert caught.value.error_code == expected_code
        assert caught.value.safe_diagnostics()[0]["identifier"] == f"unknown_{field_name}"


@pytest.mark.parametrize(
    ("relation", "profile_category", "error_code"),
    [
        (
            MatchRelationType.CONFIRMED_GAP,
            ProfileSignalCategory.SKILL,
            "CONFIRMED_GAP_WITHOUT_CONFIRMED_GAP_EVIDENCE",
        ),
        (
            MatchRelationType.PREFERENCE_ALIGNMENT,
            ProfileSignalCategory.SKILL,
            "PREFERENCE_ALIGNMENT_WITHOUT_CONFIRMED_PREFERENCE",
        ),
        (
            MatchRelationType.POTENTIAL_FRICTION,
            ProfileSignalCategory.SKILL,
            "POTENTIAL_FRICTION_WITHOUT_CONFIRMED_PREFERENCE",
        ),
    ],
)
def test_relation_semantic_failures_have_focused_codes(
    relation: MatchRelationType,
    profile_category: ProfileSignalCategory,
    error_code: str,
) -> None:
    profile, _, context = match_case()
    profile_ref = ref(context, profile_category, profile=True)
    job_ref = ref(context, JobSignalCategory.ACTUAL_WORK, profile=False)
    dimension = {
        MatchRelationType.CONFIRMED_GAP: MatchDimension.CAPABILITY_ALIGNMENT,
        MatchRelationType.PREFERENCE_ALIGNMENT: MatchDimension.CAPABILITY_ALIGNMENT,
        MatchRelationType.POTENTIAL_FRICTION: MatchDimension.VALUE_WORKSTYLE_ALIGNMENT,
    }[relation]
    item = candidate(relation, dimension, signal_ids(profile_ref, job_ref))
    with pytest.raises(LLMStructuredOutputError) as caught:
        MatchInsightAssembler().assemble(
            profile=profile,
            context=context,
            extraction=extraction_for(item),
            analysis_metadata={},
        )
    assert caught.value.error_code == error_code
    assert caught.value.safe_diagnostics()[0]["identifier"] == item.candidate_id


def test_action_policy_and_prompt_are_consistent() -> None:
    expected = {
        MatchRelationType.EVIDENCE_MISSING: {
            ActionType.VERIFY_EXISTING_CAPABILITY,
            ActionType.BUILD_PORTFOLIO_EVIDENCE,
        },
        MatchRelationType.CONFIRMED_GAP: {
            ActionType.DEEPEN_CAPABILITY,
            ActionType.GAIN_PRACTICAL_EXPERIENCE,
        },
        MatchRelationType.EXPERIENCE_DEPTH_GAP: {
            ActionType.BUILD_PORTFOLIO_EVIDENCE,
            ActionType.DEEPEN_CAPABILITY,
            ActionType.GAIN_PRACTICAL_EXPERIENCE,
        },
        MatchRelationType.POTENTIAL_FRICTION: {ActionType.CLARIFY_PREFERENCE},
        MatchRelationType.UNKNOWN: {
            ActionType.CLARIFY_PREFERENCE,
            ActionType.INVESTIGATE_JOB_UNKNOWN,
        },
    }
    assert MatchInsightAssembler._ACTION_POLICY == expected
    prompt = load_match_insight_prompt()
    assert "`target_label` 必须原样复制" in prompt
    for relation, actions in expected.items():
        assert f"`{relation.value}`" in prompt
        assert all(f"`{action.value}`" in prompt for action in actions)


def test_unsupported_action_target_has_safe_action_identifier() -> None:
    profile, _, context = match_case("AI Product Intern")
    extraction = public_offline_match_extraction(context)
    payload = extraction.model_dump()
    action = payload["candidate_actions"][0]
    action_id = action["action_id"]
    action["target_label"] = "Unsupported synthetic trend"
    with pytest.raises(LLMStructuredOutputError) as caught:
        MatchInsightAssembler().assemble(
            profile=profile,
            context=context,
            extraction=MatchInsightExtraction.model_validate(payload),
            analysis_metadata={},
        )
    assert caught.value.error_code == "ACTION_TARGET_UNSUPPORTED"
    assert caught.value.safe_diagnostics()[0]["identifier"] == action_id
