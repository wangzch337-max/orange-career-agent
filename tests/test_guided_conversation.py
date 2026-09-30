"""Deterministic conversation and evolving-profile tests for Demo v0.2."""

from __future__ import annotations

import pytest

from ui.conversation import (
    AI_INTEREST_OPTIONS,
    CAREER_QUESTION_OPTIONS,
    ConversationStage,
    GuidedConversation,
    QuestionKind,
    conversation_progress,
)
from ui.demo_controller import DemoController, DemoWorkflowError
from ui.presentation import (
    AUTHORITY_EVIDENCE,
    AUTHORITY_EXPRESSED,
    AUTHORITY_PENDING,
    AUTHORITY_UNKNOWN,
    career_profile_view,
)


def test_initial_career_question_is_chinese_first_and_choice_bounded() -> None:
    conversation = GuidedConversation()
    question = conversation.current_question
    assert question is not None
    assert question.stage == ConversationStage.CAREER_QUESTION
    assert question.prompt == "你现在最想解决的职业问题是什么？"
    assert question.options == CAREER_QUESTION_OPTIONS
    assert question.kind == QuestionKind.SINGLE


def test_career_answer_is_session_local_and_advances_deterministically() -> None:
    conversation = GuidedConversation()
    answer = "我有几个方向，但不知道怎么选"
    next_stage = conversation.submit(
        ConversationStage.CAREER_QUESTION,
        answer,
        note="想先比较，而不是得到一个唯一答案",
    )
    assert next_stage == ConversationStage.ACTIVITY_PREFERENCE
    assert conversation.answer_for(ConversationStage.CAREER_QUESTION) == answer
    assert conversation.notes[ConversationStage.CAREER_QUESTION] == "想先比较，而不是得到一个唯一答案"


def test_implementation_preference_uses_one_small_followup_branch() -> None:
    conversation = GuidedConversation(stage=ConversationStage.ACTIVITY_PREFERENCE)
    assert (
        conversation.submit(
            ConversationStage.ACTIVITY_PREFERENCE,
            "把一个想法真正做成系统",
        )
        == ConversationStage.IMPLEMENTATION_DETAIL
    )
    assert (
        conversation.submit(
            ConversationStage.IMPLEMENTATION_DETAIL,
            "设计系统结构",
        )
        == ConversationStage.AI_INTEREST
    )


@pytest.mark.parametrize(
    "answer",
    (
        "分析数据、找规律",
        "思考一个产品应该怎么工作",
        "深入研究一个技术问题",
        "和别人讨论需求、协调推进",
        "我还说不清楚",
    ),
)
def test_non_implementation_activity_skips_followup(answer: str) -> None:
    conversation = GuidedConversation(stage=ConversationStage.ACTIVITY_PREFERENCE)
    assert (
        conversation.submit(ConversationStage.ACTIVITY_PREFERENCE, answer)
        == ConversationStage.AI_INTEREST
    )


def test_ai_interest_is_validated_multi_select_not_job_recommendation() -> None:
    conversation = GuidedConversation(stage=ConversationStage.AI_INTEREST)
    selected = (
        "用现有 AI / LLM 做真正的应用",
        "思考 AI 应该解决什么用户问题",
    )
    assert set(selected).issubset(AI_INTEREST_OPTIONS)
    assert (
        conversation.submit(ConversationStage.AI_INTEREST, selected)
        == ConversationStage.PROJECT_EVIDENCE
    )
    assert conversation.answer_for(ConversationStage.AI_INTEREST) == selected
    with pytest.raises(ValueError):
        GuidedConversation(stage=ConversationStage.AI_INTEREST).submit(
            ConversationStage.AI_INTEREST,
            ("我还不知道", "分析数据和规律"),
        )


def test_project_work_style_and_goal_stages_reach_review() -> None:
    conversation = GuidedConversation(stage=ConversationStage.PROJECT_EVIDENCE)
    assert conversation.submit(
        ConversationStage.PROJECT_EVIDENCE, "Campus Helper Prototype"
    ) == ConversationStage.PROJECT_CONTRIBUTION
    assert conversation.submit(
        ConversationStage.PROJECT_CONTRIBUTION,
        ("Python", "testing"),
    ) == ConversationStage.WORK_STYLE
    assert conversation.submit(
        ConversationStage.WORK_STYLE,
        "希望几种方式都有",
    ) == ConversationStage.CAREER_GOAL
    assert conversation.submit(
        ConversationStage.CAREER_GOAL,
        "找到自己最擅长的方向",
    ) == ConversationStage.PROFILE_REVIEW
    assert conversation.ready_for_profile_review is True


def test_project_unknown_path_does_not_invent_contribution_stage() -> None:
    conversation = GuidedConversation(stage=ConversationStage.PROJECT_EVIDENCE)
    assert conversation.submit(
        ConversationStage.PROJECT_EVIDENCE,
        "我还不能判断哪个项目最能代表我",
    ) == ConversationStage.WORK_STYLE
    view = career_profile_view(conversation)
    assert any("项目证据" in item.label for item in view.evidence_needs)


def test_conversation_rejects_out_of_order_or_unlisted_answers() -> None:
    conversation = GuidedConversation()
    with pytest.raises(ValueError):
        conversation.submit(ConversationStage.WORK_STYLE, "希望几种方式都有")
    with pytest.raises(ValueError):
        conversation.submit(ConversationStage.CAREER_QUESTION, "模型自由生成的路线")


def test_conversation_progress_is_stage_context_not_profile_percentage() -> None:
    current, total = conversation_progress(ConversationStage.ACTIVITY_PREFERENCE)
    assert current == 2
    assert total == 9
    assert "percent" not in f"{current}/{total}".casefold()


def test_dynamic_profile_distinguishes_evidence_expression_pending_and_unknown() -> None:
    conversation = GuidedConversation(stage=ConversationStage.PROJECT_CONTRIBUTION)
    conversation.answers[ConversationStage.AI_INTEREST] = (
        "用现有 AI / LLM 做真正的应用",
    )
    conversation.answers[ConversationStage.PROJECT_EVIDENCE] = "Campus Helper Prototype"
    conversation.submit(
        ConversationStage.PROJECT_CONTRIBUTION,
        ("Python", "API integration"),
    )
    view = career_profile_view(conversation)
    authorities = {
        item.authority
        for group in (
            view.demonstrated_capabilities,
            view.interests_and_work_style,
            view.exploration_directions,
            view.evidence_needs,
        )
        for item in group
    }
    assert AUTHORITY_EVIDENCE in authorities
    assert AUTHORITY_EXPRESSED in authorities
    assert AUTHORITY_PENDING in authorities
    assert AUTHORITY_UNKNOWN in authorities
    assert any(item.label == "AI 应用 / LLM 应用" for item in view.exploration_directions)


def test_guided_conversation_never_invokes_provider_or_starts_graph() -> None:
    controller = DemoController()
    try:
        provider = controller.dependencies.self_discovery_agent.llm_provider
        controller.submit_conversation_answer(
            ConversationStage.CAREER_QUESTION,
            "我只是想先更了解自己",
        )
        controller.submit_conversation_answer(
            ConversationStage.ACTIVITY_PREFERENCE,
            "分析数据、找规律",
        )
        assert provider.call_count == 0
        assert controller.state is None
    finally:
        controller.close()


def test_real_graph_cannot_be_prepared_before_guided_review_stage() -> None:
    controller = DemoController()
    try:
        with pytest.raises(DemoWorkflowError):
            controller.prepare_profile_review()
        assert controller.state is None
    finally:
        controller.close()
