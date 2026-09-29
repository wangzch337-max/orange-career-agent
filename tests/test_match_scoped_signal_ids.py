"""Request-scoped signal-ID constraints for MatchInsight v5."""

import json

import pytest
from pydantic import ValidationError

from agents.match_context import MatchContextBuilder
from agents.match_insight_demo import build_offline_job_intelligence, load_public_profile
from agents.match_insight_models import (
    MatchInsightExtraction,
    allowed_match_signal_ids,
    build_match_insight_response_model,
)
from data.models import MatchRelationType
from providers.errors import LLMStructuredOutputError
from providers.fake import FakeLLMProvider
from providers.models import GenerationOptions, LLMMessage, MessageRole


def product_context():
    profile = load_public_profile()
    intelligence = next(
        item
        for item in build_offline_job_intelligence()
        if item.role_title == "AI Product Intern"
    )
    return MatchContextBuilder().build(profile, intelligence)


def candidate(
    relation: MatchRelationType = MatchRelationType.STRONG_ALIGNMENT,
    *,
    profile_signal_ids: list[str],
    job_signal_ids: list[str],
) -> dict[str, object]:
    return {
        "candidate_id": "candidate_001",
        "dimension": "capability_alignment",
        "relation_type": relation.value,
        "title": "Public scoped-ID test",
        "description": "A bounded relation for offline validation.",
        "confidence": 0.8,
        "profile_signal_ids": profile_signal_ids,
        "job_signal_ids": job_signal_ids,
        "needs_user_review": True,
    }


def schema_id_enums(context):
    schema = build_match_insight_response_model(context).model_json_schema()
    properties = schema["$defs"]["RequestScopedBilateralMatchCandidate"]["properties"]
    return (
        properties["profile_signal_ids"]["items"]["enum"],
        properties["job_signal_ids"]["items"]["enum"],
        schema,
    )


def test_allowed_signal_ids_are_derived_from_exact_context() -> None:
    context = product_context()
    profile_ids, job_ids = allowed_match_signal_ids(context)
    assert profile_ids == tuple(item.signal_id for item in context.profile_signals)
    assert job_ids == tuple(item.signal_id for item in context.job_signals)


def test_context_signal_namespaces_must_be_disjoint() -> None:
    context = product_context()
    overlapping = context.model_copy(
        update={
            "job_signals": [
                context.job_signals[0].model_copy(
                    update={"signal_id": context.profile_signals[0].signal_id}
                ),
                *context.job_signals[1:],
            ]
        }
    )
    with pytest.raises(ValueError, match="namespaces must be disjoint"):
        allowed_match_signal_ids(overlapping)


def test_generated_schema_contains_only_request_scoped_ids() -> None:
    context = product_context()
    profile_enum, job_enum, schema = schema_id_enums(context)
    assert profile_enum == [item.signal_id for item in context.profile_signals]
    assert job_enum == [item.signal_id for item in context.job_signals]
    assert "unrelated_profile_signal_999" not in profile_enum
    assert "unrelated_job_signal_999" not in job_enum
    assert "job_001_pref_001" not in job_enum
    encoded = json.dumps(schema, sort_keys=True)
    assert '"discriminator"' in encoded
    assert '"oneOf"' in encoded


def test_valid_profile_and_job_ids_parse_in_scoped_bilateral_candidate() -> None:
    context = product_context()
    model = build_match_insight_response_model(context)
    profile_id = context.profile_signals[0].signal_id
    job_id = context.job_signals[0].signal_id
    result = model.model_validate(
        {"candidate_alignments": [candidate(
            profile_signal_ids=[profile_id],
            job_signal_ids=[job_id],
        )]}
    )
    parsed = result.candidate_alignments[0]
    assert parsed.profile_signal_ids == [profile_id]
    assert parsed.job_signal_ids == [job_id]


@pytest.mark.parametrize(
    ("field_name", "unknown_id", "error_type"),
    [
        ("profile_signal_ids", "profile_signal_unknown", "unknown_profile_signal_id"),
        ("job_signal_ids", "job_001_pref_001", "unknown_job_signal_id"),
    ],
)
def test_unknown_ids_fail_request_scoped_structured_validation(
    field_name: str,
    unknown_id: str,
    error_type: str,
) -> None:
    context = product_context()
    raw = candidate(
        profile_signal_ids=[context.profile_signals[0].signal_id],
        job_signal_ids=[context.job_signals[0].signal_id],
    )
    raw[field_name] = [unknown_id]
    provider = FakeLLMProvider({"candidate_alignments": [raw]})
    with pytest.raises(LLMStructuredOutputError) as caught:
        provider.generate_structured(
            [LLMMessage(role=MessageRole.USER, content="sanitized")],
            build_match_insight_response_model(context),
            GenerationOptions(model="fake", max_retries=0),
            prompt_name="match_insight",
            prompt_version="v5",
        )
    diagnostic = caught.value.safe_diagnostics()[0]
    assert diagnostic["type"] == error_type
    assert diagnostic["error_code"] == (
        "UNKNOWN_PROFILE_SIGNAL_ID"
        if field_name == "profile_signal_ids"
        else "UNKNOWN_JOB_SIGNAL_ID"
    )
    assert unknown_id not in repr(caught.value.safe_diagnostics())


def test_profile_and_job_signal_namespaces_are_not_interchangeable() -> None:
    context = product_context()
    model = build_match_insight_response_model(context)
    profile_id = context.profile_signals[0].signal_id
    job_id = context.job_signals[0].signal_id
    for profile_ids, job_ids, error_type in (
        ([job_id], [job_id], "unknown_profile_signal_id"),
        ([profile_id], [profile_id], "unknown_job_signal_id"),
    ):
        with pytest.raises(ValidationError) as caught:
            model.model_validate(
                {"candidate_alignments": [candidate(
                    profile_signal_ids=profile_ids,
                    job_signal_ids=job_ids,
                )]}
            )
        assert any(error["type"] == error_type for error in caught.value.errors())


def test_relation_families_compose_with_scoped_ids() -> None:
    context = product_context()
    model = build_match_insight_response_model(context)
    profile_id = context.profile_signals[0].signal_id
    job_id = context.job_signals[0].signal_id

    with pytest.raises(ValidationError):
        model.model_validate({"candidate_alignments": [candidate(
            profile_signal_ids=[],
            job_signal_ids=[job_id],
        )]})

    evidence_missing = model.model_validate({"candidate_gaps": [candidate(
        MatchRelationType.EVIDENCE_MISSING,
        profile_signal_ids=[],
        job_signal_ids=[job_id],
    )]})
    assert evidence_missing.candidate_gaps[0].profile_signal_ids == []

    for profile_ids, job_ids in (
        ([profile_id], []),
        ([], [job_id]),
        ([profile_id], [job_id]),
    ):
        parsed = model.model_validate({"candidate_unknowns": [candidate(
            MatchRelationType.UNKNOWN,
            profile_signal_ids=profile_ids,
            job_signal_ids=job_ids,
        )]})
        assert parsed.candidate_unknowns
    with pytest.raises(ValidationError):
        model.model_validate({"candidate_unknowns": [candidate(
            MatchRelationType.UNKNOWN,
            profile_signal_ids=[],
            job_signal_ids=[],
        )]})


def test_deterministic_exact_id_validator_remains_as_second_layer() -> None:
    context = product_context()
    extraction = MatchInsightExtraction.model_validate(
        {"candidate_alignments": [candidate(
            profile_signal_ids=[context.profile_signals[0].signal_id],
            job_signal_ids=["job_001_pref_001"],
        )]}
    )
    with pytest.raises(LLMStructuredOutputError) as caught:
        extraction.validate_context(context)
    assert caught.value.error_code == "UNKNOWN_JOB_SIGNAL_ID"
