"""Relation-aware provider schema tests for MatchInsight v4."""

import json

import pytest
from pydantic import ValidationError

from agents.match_insight_models import (
    BilateralMatchCandidate,
    EvidenceMissingCandidate,
    MatchInsightExtraction,
    NormalizedMatchCandidate,
    UnknownMatchCandidate,
    validate_match_insight_candidate,
)
from data.models import MatchRelationType
from providers.errors import LLMStructuredOutputError
from providers.fake import FakeLLMProvider
from providers.models import GenerationOptions, LLMMessage, MessageRole


BILATERAL_RELATIONS = (
    MatchRelationType.STRONG_ALIGNMENT,
    MatchRelationType.PARTIAL_ALIGNMENT,
    MatchRelationType.CONFIRMED_GAP,
    MatchRelationType.EXPERIENCE_DEPTH_GAP,
    MatchRelationType.PREFERENCE_ALIGNMENT,
    MatchRelationType.POTENTIAL_FRICTION,
)


def payload(
    relation: MatchRelationType,
    *,
    profile_signal_ids=None,
    job_signal_ids=None,
) -> dict[str, object]:
    return {
        "candidate_id": f"candidate_{relation.value}",
        "dimension": "capability_alignment",
        "relation_type": relation.value,
        "title": "Synthetic relation",
        "description": "A bounded public test candidate.",
        "confidence": 0.8,
        "profile_signal_ids": (
            ["profile_signal_001"]
            if profile_signal_ids is None
            else profile_signal_ids
        ),
        "job_signal_ids": (
            ["job_signal_001"] if job_signal_ids is None else job_signal_ids
        ),
        "needs_user_review": True,
    }


@pytest.mark.parametrize("relation", BILATERAL_RELATIONS)
@pytest.mark.parametrize("empty_side", ["profile_signal_ids", "job_signal_ids"])
def test_bilateral_candidate_requires_both_signal_sides(
    relation: MatchRelationType,
    empty_side: str,
) -> None:
    raw = payload(relation)
    raw[empty_side] = []
    with pytest.raises(ValidationError) as caught:
        validate_match_insight_candidate(raw)
    assert any(error["type"] == "too_short" for error in caught.value.errors())


@pytest.mark.parametrize("relation", BILATERAL_RELATIONS)
def test_bilateral_candidate_with_both_sides_parses(
    relation: MatchRelationType,
) -> None:
    candidate = validate_match_insight_candidate(payload(relation))
    assert isinstance(candidate, BilateralMatchCandidate)
    assert candidate.relation_type == relation
    assert candidate.profile_signal_ids == ["profile_signal_001"]
    assert candidate.job_signal_ids == ["job_signal_001"]


def test_evidence_missing_allows_empty_profile_and_requires_job() -> None:
    valid = validate_match_insight_candidate(
        payload(
            MatchRelationType.EVIDENCE_MISSING,
            profile_signal_ids=[],
        )
    )
    assert isinstance(valid, EvidenceMissingCandidate)
    assert valid.profile_signal_ids == []
    with pytest.raises(ValidationError):
        validate_match_insight_candidate(
            payload(
                MatchRelationType.EVIDENCE_MISSING,
                profile_signal_ids=[],
                job_signal_ids=[],
            )
        )


@pytest.mark.parametrize(
    ("profile_signal_ids", "job_signal_ids"),
    [
        (["profile_signal_001"], []),
        ([], ["job_signal_001"]),
        (["profile_signal_001"], ["job_signal_001"]),
    ],
)
def test_unknown_accepts_profile_job_or_both_signal_sides(
    profile_signal_ids: list[str],
    job_signal_ids: list[str],
) -> None:
    candidate = validate_match_insight_candidate(
        payload(
            MatchRelationType.UNKNOWN,
            profile_signal_ids=profile_signal_ids,
            job_signal_ids=job_signal_ids,
        )
    )
    assert isinstance(candidate, UnknownMatchCandidate)


def test_unknown_rejects_neither_signal_side_with_safe_diagnostic() -> None:
    raw = payload(
        MatchRelationType.UNKNOWN,
        profile_signal_ids=[],
        job_signal_ids=[],
    )
    provider = FakeLLMProvider({"candidate_unknowns": [raw]})
    with pytest.raises(LLMStructuredOutputError) as caught:
        provider.generate_structured(
            [LLMMessage(role=MessageRole.USER, content="sanitized")],
            MatchInsightExtraction,
            GenerationOptions(model="fake", max_retries=0),
            prompt_name="match_insight",
            prompt_version="v4",
        )
    diagnostic = caught.value.safe_diagnostics()[0]
    assert diagnostic["error_code"] == "UNKNOWN_REQUIRES_SIGNAL_REFERENCE"
    assert diagnostic["type"] == "unknown_signal_reference_required"


def test_relation_enum_serialization_is_exact() -> None:
    for relation in MatchRelationType:
        candidate = validate_match_insight_candidate(
            payload(
                relation,
                profile_signal_ids=(
                    [] if relation == MatchRelationType.EVIDENCE_MISSING else None
                ),
                job_signal_ids=(
                    [] if relation == MatchRelationType.UNKNOWN else None
                ),
            )
        )
        assert candidate.model_dump(mode="json")["relation_type"] == relation.value


def test_qwen_response_model_json_schema_is_relation_discriminated() -> None:
    schema = MatchInsightExtraction.model_json_schema()
    encoded = json.dumps(schema, sort_keys=True)
    bilateral = schema["$defs"]["BilateralMatchCandidate"]["properties"]
    assert bilateral["profile_signal_ids"]["minItems"] == 1
    assert bilateral["job_signal_ids"]["minItems"] == 1
    assert '"discriminator"' in encoded
    assert '"oneOf"' in encoded
    for relation in MatchRelationType:
        assert relation.value in encoded


def test_fake_provider_parses_relation_aware_union() -> None:
    raw = {
        "candidate_alignments": [payload(MatchRelationType.PARTIAL_ALIGNMENT)],
        "candidate_gaps": [
            payload(
                MatchRelationType.EVIDENCE_MISSING,
                profile_signal_ids=[],
            )
        ],
        "candidate_unknowns": [
            payload(
                MatchRelationType.UNKNOWN,
                profile_signal_ids=[],
            )
        ],
    }
    response = FakeLLMProvider(raw).generate_structured(
        [LLMMessage(role=MessageRole.USER, content="sanitized")],
        MatchInsightExtraction,
        GenerationOptions(model="fake", max_retries=0),
        prompt_name="match_insight",
        prompt_version="v4",
    )
    assert isinstance(response.data.candidate_alignments[0], BilateralMatchCandidate)
    assert isinstance(response.data.candidate_gaps[0], EvidenceMissingCandidate)
    assert isinstance(response.data.candidate_unknowns[0], UnknownMatchCandidate)


def test_normalization_copies_validated_fields_without_repair() -> None:
    candidate = validate_match_insight_candidate(
        payload(MatchRelationType.PARTIAL_ALIGNMENT)
    )
    normalized = NormalizedMatchCandidate.from_provider(candidate)
    assert normalized.model_dump(mode="json") == candidate.model_dump(mode="json")
