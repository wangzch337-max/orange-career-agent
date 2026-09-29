"""Deterministic authority-boundary tests for Phase 5 Match actions."""

import hashlib
from pathlib import Path

import pytest

from agents.action_renderer import ActionRenderer
from agents.match_context import MatchContextBuilder
from agents.match_insight import public_offline_match_extraction
from agents.match_insight_assembler import MatchInsightAssembler
from agents.match_insight_demo import build_offline_job_intelligence, load_public_profile
from agents.match_insight_models import MatchInsightExtraction
from data.models import ActionType
from providers.errors import LLMStructuredOutputError
from providers.prompts import MATCH_INSIGHT_PROMPT_PATH, MATCH_INSIGHT_PROMPT_VERSION
from tools.report import DeterministicReportBuilder


ROOT = Path(__file__).resolve().parents[1]


def data_analyst_case():
    profile = load_public_profile()
    intelligence = next(
        item
        for item in build_offline_job_intelligence()
        if item.role_title == "Data Analyst"
    )
    context = MatchContextBuilder().build(profile, intelligence)
    extraction = public_offline_match_extraction(context)
    return profile, intelligence, context, extraction


@pytest.mark.parametrize(
    ("action_type", "description", "expected_evidence"),
    [
        (
            ActionType.VERIFY_EXISTING_CAPABILITY,
            "Review existing course and project evidence to determine whether you already have demonstrable SQL experience.",
            "One or more verifiable examples of SQL use, or an explicit confirmation that no such experience currently exists.",
        ),
        (
            ActionType.BUILD_PORTFOLIO_EVIDENCE,
            "Create a small portfolio artifact demonstrating SQL.",
            "A verifiable artifact demonstrating SQL.",
        ),
        (
            ActionType.DEEPEN_CAPABILITY,
            "Complete a focused exercise or project to deepen SQL.",
            "A verifiable exercise or project demonstrating deeper SQL.",
        ),
        (
            ActionType.GAIN_PRACTICAL_EXPERIENCE,
            "Gain hands-on experience applying SQL in a realistic task.",
            "A verifiable record of applying SQL in a realistic task.",
        ),
        (
            ActionType.CLARIFY_PREFERENCE,
            "Clarify your current preference regarding SQL.",
            "A user-confirmed preference statement regarding SQL.",
        ),
        (
            ActionType.INVESTIGATE_JOB_UNKNOWN,
            "Investigate the role information related to SQL.",
            "A reliable source clarifying SQL.",
        ),
    ],
)
def test_action_renderer_has_generic_templates_for_every_action_type(
    action_type, description, expected_evidence
) -> None:
    profile, _, context, extraction = data_analyst_case()
    result = MatchInsightAssembler().assemble(
        profile=profile,
        context=context,
        extraction=extraction,
        analysis_metadata={},
    )
    rendered = ActionRenderer().render(
        action_type=action_type,
        target_label="SQL",
        related_insights=[result.insights()[0]],
    )
    assert rendered.description == description
    assert rendered.expected_evidence == expected_evidence
    assert rendered.rationale


def test_provider_action_prose_is_discarded_from_authoritative_action_and_report() -> None:
    profile, intelligence, context, extraction = data_analyst_case()
    payload = extraction.model_dump()
    poisoned = "Use Streamlit, Matplotlib, Kubernetes, and LangChain immediately."
    for action in payload["candidate_actions"]:
        action["description"] = poisoned
        action["expected_evidence"] = poisoned
        action["rationale"] = poisoned
    result = MatchInsightAssembler().assemble(
        profile=profile,
        context=context,
        extraction=MatchInsightExtraction.model_validate(payload),
        analysis_metadata={},
    )
    rendered = " ".join(
        f"{item.description} {item.expected_evidence} {item.rationale}"
        for item in result.action_items
    )
    for unsupported in ("Streamlit", "Matplotlib", "Kubernetes", "LangChain"):
        assert unsupported not in rendered
    assert all(item.description != poisoned for item in result.action_items)
    assert all(item.expected_evidence != poisoned for item in result.action_items)
    report = DeterministicReportBuilder().build(
        "workflow_action_grounding",
        profile,
        [intelligence],
        [result],
    )
    assert report.next_actions[result.job_id] == [
        item.description for item in result.action_items
    ]
    assert poisoned not in report.model_dump_json()


def test_verify_action_does_not_duplicate_experience_in_generic_target() -> None:
    profile, _, context, extraction = data_analyst_case()
    result = MatchInsightAssembler().assemble(
        profile=profile,
        context=context,
        extraction=extraction,
        analysis_metadata={},
    )
    rendered = ActionRenderer().render(
        action_type=ActionType.VERIFY_EXISTING_CAPABILITY,
        target_label="Experience evaluating LLM application behavior",
        related_insights=[result.insights()[0]],
    )
    assert "experience experience" not in rendered.description.casefold()
    assert rendered.description.endswith(
        "demonstrable experience evaluating LLM application behavior."
    )


@pytest.mark.parametrize(
    "replacement",
    ["sql", "Tertiary Exploration", "Dashboard Design (rewritten)"],
)
def test_target_label_requires_exact_context_label_without_semantic_rename(
    replacement: str,
) -> None:
    profile, _, context, extraction = data_analyst_case()
    payload = extraction.model_dump()
    payload["candidate_actions"][0]["target_label"] = replacement
    with pytest.raises(LLMStructuredOutputError) as caught:
        MatchInsightAssembler().assemble(
            profile=profile,
            context=context,
            extraction=MatchInsightExtraction.model_validate(payload),
            analysis_metadata={},
        )
    assert caught.value.error_code == "ACTION_TARGET_UNSUPPORTED"


def test_match_v1_is_frozen_and_v5_is_active() -> None:
    digest = hashlib.sha256(
        (ROOT / "config" / "prompts" / "match_insight_v1.md").read_bytes()
    ).hexdigest()
    assert digest == "151b41c72a29a27b80b35c5ff7d1bfc6e5fd3c4086e0e0dc7ad4415b60f7928d"
    assert MATCH_INSIGHT_PROMPT_VERSION == "v5"
    assert MATCH_INSIGHT_PROMPT_PATH.name == "match_insight_v5.md"
