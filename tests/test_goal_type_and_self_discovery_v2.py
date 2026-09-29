"""Focused regression tests for conservative Self-Discovery v2 goal semantics."""

import pytest

from agents.match_context import MatchContextBuilder
from agents.match_insight_assembler import MatchInsightAssembler
from agents.match_insight_demo import build_offline_job_intelligence, load_public_profile
from agents.match_insight_models import (
    MatchInsightExtraction,
    ProfileSignalCategory,
    validate_match_insight_candidate,
)
from agents.profile_assembler import ProfileAssembler
from agents.self_discovery_models import (
    EvidenceBundle,
    GoalExtractionSignal,
    SelfDiscoveryExtraction,
    SelfDiscoverySourceEvidence,
    SkillSignal,
    StrengthSignal,
)
from data.models import (
    EvidenceItem,
    EvidenceSourceType,
    GoalType,
    InferenceType,
    MatchDimension,
    MatchRelationType,
)
from providers.errors import LLMStructuredOutputError
from providers.models import LLMUsage


def evidence_bundle(text: str = "The user explicitly stated this goal.") -> EvidenceBundle:
    source = SelfDiscoverySourceEvidence(
        id="goal_001",
        text=text,
        source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
        source_name="Synthetic input",
    )
    return EvidenceBundle(
        source_evidence=[source],
        domain_evidence=[
            EvidenceItem(
                id=source.id,
                source_type=source.source_type,
                source_name=source.source_name,
                statement=source.text,
                confidence=1.0,
            )
        ],
    )


def goal_extraction(goal_type: GoalType) -> SelfDiscoveryExtraction:
    return SelfDiscoveryExtraction(
        goals=[
            GoalExtractionSignal(
                goal_type=goal_type,
                label="Synthetic bounded goal",
                description="A synthetic goal used only for schema validation.",
                confidence=1.0,
                evidence_ids=["goal_001"],
                inference_type=InferenceType.EXPLICIT_FACT,
            )
        ]
    )


def test_goal_type_enum_has_three_explicit_categories() -> None:
    assert {item.value for item in GoalType} == {
        "career_goal",
        "project_goal",
        "learning_goal",
    }
    assert GoalType.PROJECT_GOAL.display_name_zh == "项目目标"


@pytest.mark.parametrize("goal_type", list(GoalType))
def test_assembler_preserves_each_goal_type(goal_type: GoalType) -> None:
    result = ProfileAssembler().assemble(
        profile_id="profile_goal_type",
        extraction=goal_extraction(goal_type),
        evidence=evidence_bundle(),
        extraction_metadata={},
        usage=LLMUsage(),
    )
    goal = result.user_profile.goals[0]
    assert goal.goal_type is goal_type
    assert goal.inference_type == InferenceType.EXPLICIT_FACT
    assert goal.evidence_ids == ["goal_001"]


def test_match_context_carries_project_goal_type_without_rewriting() -> None:
    profile = load_public_profile()
    project_goal = profile.goals[0].model_copy(
        update={"goal_type": GoalType.PROJECT_GOAL}
    )
    profile = profile.model_copy(update={"goals": [project_goal]})
    context = MatchContextBuilder().build(profile, build_offline_job_intelligence()[0])
    goal_ref = next(
        item for item in context.profile_signals
        if item.category == ProfileSignalCategory.GOAL
    )
    assert goal_ref.goal_type == GoalType.PROJECT_GOAL


def test_project_goal_alone_cannot_create_career_preference_alignment() -> None:
    profile = load_public_profile()
    project_goal = profile.goals[0].model_copy(
        update={"goal_type": GoalType.PROJECT_GOAL}
    )
    profile = profile.model_copy(
        update={"goals": [project_goal], "career_preferences": []}
    )
    context = MatchContextBuilder().build(profile, build_offline_job_intelligence()[0])
    goal_ref = next(
        item for item in context.profile_signals
        if item.category == ProfileSignalCategory.GOAL
    )
    job_ref = context.job_signals[0]
    extraction = MatchInsightExtraction(
        candidate_alignments=[
            validate_match_insight_candidate(
                {
                    "candidate_id": "unsupported_preference_001",
                    "dimension": MatchDimension.CAREER_PREFERENCE_ALIGNMENT,
                    "relation_type": MatchRelationType.PARTIAL_ALIGNMENT,
                    "title": "Unsupported career preference",
                    "description": "A project goal cannot establish a career preference.",
                    "confidence": 0.5,
                    "profile_signal_ids": [goal_ref.signal_id],
                    "job_signal_ids": [job_ref.signal_id],
                }
            )
        ]
    )
    with pytest.raises(LLMStructuredOutputError, match="goal 不能替代偏好"):
        MatchInsightAssembler().assemble(
            profile=profile,
            context=context,
            extraction=extraction,
            analysis_metadata={},
        )


def test_testing_and_git_only_evidence_cannot_support_devops_label() -> None:
    source = SelfDiscoverySourceEvidence(
        id="project_001",
        text="Automated tests, GitHub collaboration, and clean repository practices.",
        source_type=EvidenceSourceType.PROJECT,
        source_name="Synthetic project",
    )
    extraction = SelfDiscoveryExtraction(
        skills=[
            SkillSignal(
                label="Automated Testing & DevOps Practices",
                description="A broad professional capability claim.",
                confidence=0.8,
                evidence_ids=[source.id],
                inference_type=InferenceType.EVIDENCE_SUPPORTED_INFERENCE,
            )
        ]
    )
    with pytest.raises(LLMStructuredOutputError, match="DevOps"):
        extraction.validate_evidence_ids([source])


@pytest.mark.parametrize("label", ["Full-Stack Mobile Capability", "Backend Capability"])
def test_mobile_and_python_tooling_cannot_support_broad_stack_labels(label: str) -> None:
    source = SelfDiscoverySourceEvidence(
        id="project_001",
        text="Built iOS apps with SwiftUI plus Python tooling, API integration, data normalization, and tests.",
        source_type=EvidenceSourceType.PROJECT,
        source_name="Synthetic project",
    )
    extraction = SelfDiscoveryExtraction(
        strengths=[
            StrengthSignal(
                label=label,
                description="A broad professional capability claim.",
                confidence=0.8,
                evidence_ids=[source.id],
                inference_type=InferenceType.EVIDENCE_SUPPORTED_INFERENCE,
            )
        ]
    )
    with pytest.raises(LLMStructuredOutputError, match="证据范围"):
        extraction.validate_evidence_ids([source])


def test_direct_deployment_evidence_can_support_devops_label() -> None:
    source = SelfDiscoverySourceEvidence(
        id="project_001",
        text="Owned CI/CD deployment pipelines and container infrastructure.",
        source_type=EvidenceSourceType.PROJECT,
        source_name="Synthetic project",
    )
    extraction = SelfDiscoveryExtraction(
        skills=[
            SkillSignal(
                label="DevOps practices",
                description="Directly supported by deployment evidence.",
                confidence=0.8,
                evidence_ids=[source.id],
                inference_type=InferenceType.EVIDENCE_SUPPORTED_INFERENCE,
            )
        ]
    )
    assert extraction.validate_evidence_ids([source]) is extraction
