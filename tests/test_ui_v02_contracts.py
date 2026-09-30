"""Product-contract tests for Orange Interactive Demo v0.2."""

from __future__ import annotations

from pathlib import Path

import pytest

from data.models import ActionType, EvidenceSourceType, MatchRelationType
from memory.models import MemoryStatus, MemoryType
from ui.demo_controller import (
    APPROVED_ROLE_IDS,
    APPROVED_ROLE_TITLES,
    DemoController,
    DemoValidationError,
    DemoWorkflowError,
    ROLE_DEPRIORITIZATION_REASONS,
)
from ui.presentation import (
    ACTION_RECIPES,
    ASK_ORANGE_QUESTIONS,
    ROLE_CLARIFICATION_OPTIONS,
    ROLE_CLARIFICATION_PROMPTS,
    action_task_view,
    ask_orange_answer,
    career_direction_card_view,
    match_insight_groups,
    memory_summary_view,
)
from workflows.langgraph_state import GraphWorkflowStatus


@pytest.fixture
def completed_controller():
    controller = DemoController()
    controller.start()
    controller.confirm_profile()
    yield controller
    controller.close()


def test_profile_revision_resumes_same_thread_without_rediscovery() -> None:
    controller = DemoController()
    try:
        paused = controller.start()
        workflow_id = paused["workflow_id"]
        before = controller.dependencies.self_discovery_agent.llm_provider.call_count
        revised = controller.revise_profile_summary("公开合成的 AI 相关硕士背景")
        assert revised["workflow_status"] == GraphWorkflowStatus.WAITING_FOR_HUMAN.value
        assert revised["workflow_id"] == workflow_id
        assert revised["profile"]["version"] == 2
        assert controller.dependencies.self_discovery_agent.llm_provider.call_count == before == 1
        completed = controller.confirm_profile()
        assert completed["profile"]["version"] == 2
        assert completed["self_discovery_call_count"] == 1
    finally:
        controller.close()


def test_roles_stay_unavailable_before_real_profile_confirmation() -> None:
    controller = DemoController()
    try:
        controller.start()
        with pytest.raises(DemoWorkflowError):
            controller.job_records()
        with pytest.raises(DemoWorkflowError):
            controller.match_results()
        assert controller.state["job_records"] == []
        assert controller.state["match_results"] == []
    finally:
        controller.close()


def test_three_direction_cards_use_ui_copy_and_validated_overlap(
    completed_controller,
) -> None:
    controller = completed_controller
    views = [
        career_direction_card_view(job, record, result, controller.confirmed_profile())
        for job, record, result in zip(
            controller.job_records(),
            controller.job_intelligence(),
            controller.match_results(),
        )
    ]
    assert tuple(view.title for view in views) == APPROVED_ROLE_TITLES
    assert all(view.one_line for view in views)
    assert all(view.validated_overlaps for view in views)
    assert all(view.clarification_need for view in views)
    serialized = str(views).casefold()
    assert "#1" not in serialized
    assert "best role" not in serialized
    assert "score" not in serialized


@pytest.mark.parametrize("job_id", APPROVED_ROLE_IDS)
def test_each_role_has_one_bounded_clarification_prompt(job_id: str) -> None:
    assert job_id in ROLE_CLARIFICATION_PROMPTS
    assert ROLE_CLARIFICATION_PROMPTS[job_id].endswith("？")
    assert ROLE_CLARIFICATION_OPTIONS == (
        "很喜欢",
        "可以接受",
        "不太喜欢",
        "没做过，不知道",
    )


def test_role_answer_is_session_only_until_explicit_save(completed_controller) -> None:
    controller = completed_controller
    controller.answer_role_clarification("job_007", "可以接受")
    assert controller.role_clarifications["job_007"] == "可以接受"
    assert controller.active_memories() == []
    record = controller.save_role_clarification("job_007")
    assert record.memory_type == MemoryType.USER_FEEDBACK
    assert record.status == MemoryStatus.CONFIRMED
    assert record.source_type == EvidenceSourceType.EXPLICIT_USER_INPUT
    assert record.metadata["job_id"] == "job_007"
    assert controller.save_role_clarification("job_007").memory_id == record.memory_id
    assert len(controller.active_memories()) == 1


def test_saved_feedback_uses_temporary_demo_database(completed_controller) -> None:
    controller = completed_controller
    controller.answer_role_clarification("job_001", "很喜欢")
    controller.save_role_clarification("job_001")
    path = controller.memory_service.database.path
    assert path.name == "orange_demo_memory.sqlite3"
    assert path.is_file()
    assert "orange_ui_demo_" in path.as_posix()


def test_deprioritization_is_only_exploration_state_not_match_mutation(
    completed_controller,
) -> None:
    controller = completed_controller
    before = controller.match_for("job_013").model_dump(mode="json")
    controller.set_role_exploration(
        "job_013",
        "暂时不考虑",
        reason=ROLE_DEPRIORITIZATION_REASONS[3],
    )
    after = controller.match_for("job_013").model_dump(mode="json")
    assert after == before
    assert controller.role_deprioritization_reasons["job_013"] == "只是目前优先级较低"
    assert controller.active_memories() == []
    view = controller.exploration_map()
    assert view.deprioritized == ("Data Analyst",)
    assert "Data Analyst" not in view.continue_exploring


def test_deprioritization_requires_a_guided_reason(completed_controller) -> None:
    with pytest.raises(DemoValidationError):
        completed_controller.set_role_exploration("job_001", "暂时不考虑")


def test_match_group_views_preserve_all_domain_relations_and_careful_copy(
    completed_controller,
) -> None:
    controller = completed_controller
    groups = match_insight_groups(
        controller.match_for("job_007"),
        controller.confirmed_profile(),
        controller.intelligence_for("job_007"),
    )
    assert tuple(group.relation_type for group in groups) == tuple(MatchRelationType)
    copy = {group.relation_type: group.explanation for group in groups}
    assert "不代表你不具备" in copy[MatchRelationType.EVIDENCE_MISSING]
    assert "不代表你不适合" in copy[MatchRelationType.POTENTIAL_FRICTION]


def test_ask_orange_menu_is_predefined_deterministic_and_provider_free(
    completed_controller,
) -> None:
    controller = completed_controller
    record = controller.intelligence_for("job_007")
    result = controller.match_for("job_007")
    profile = controller.confirmed_profile()
    providers = (
        controller.dependencies.self_discovery_agent.llm_provider,
        controller.dependencies.job_intelligence_agent.llm_provider,
        controller.dependencies.match_insight_agent.llm_provider,
    )
    before = tuple(item.call_count for item in providers)
    first = [ask_orange_answer(item, record, result, profile) for item in ASK_ORANGE_QUESTIONS]
    second = [ask_orange_answer(item, record, result, profile) for item in ASK_ORANGE_QUESTIONS]
    assert first == second
    assert all(first)
    assert tuple(item.call_count for item in providers) == before
    with pytest.raises(ValueError):
        ask_orange_answer("任意自由问题", record, result, profile)


def test_action_task_view_preserves_authority_and_uses_bounded_recipes(
    completed_controller,
) -> None:
    result = completed_controller.match_for("job_007")
    assert set(ACTION_RECIPES) == set(ActionType)
    for action in result.action_items:
        view = action_task_view(action, result)
        assert view.why == action.rationale
        assert view.what_to_do[0] == action.description
        assert view.target == action.target_label
        assert view.expected_evidence == action.expected_evidence
        assert view.related_insight_ids == tuple(action.related_insight_ids)
        assert set(view.related_insight_ids).issubset(
            {item.insight_id for item in result.insights()}
        )
        unsupported = ("pytorch", "tensorflow", "langchain", "kubernetes")
        assert not any(term in str(view).casefold() for term in unsupported)


def test_action_status_and_already_done_are_session_only(completed_controller) -> None:
    controller = completed_controller
    profile_before = controller.confirmed_profile().model_dump(mode="json")
    action = controller.match_for("job_007").action_items[0]
    controller.set_action_status(action.action_id, "进行中")
    assert controller.action_status(action.action_id) == "进行中"
    controller.mark_action_already_done(action.action_id)
    assert action.action_id in controller.actions_needing_evidence_review
    assert controller.confirmed_profile().model_dump(mode="json") == profile_before
    assert controller.active_memories() == []


def test_exploration_map_uses_only_explicit_state_without_scores(
    completed_controller,
) -> None:
    controller = completed_controller
    controller.set_role_exploration("job_001", "继续探索")
    controller.set_role_exploration(
        "job_013",
        "暂时不考虑",
        reason="工作内容不感兴趣",
    )
    view = controller.exploration_map()
    assert view.continue_exploring == ("AI Product Intern",)
    assert view.keep_open == ("AI Application Engineer",)
    assert view.deprioritized == ("Data Analyst",)
    assert "score" not in str(view).casefold()
    assert "rank" not in str(view).casefold()


def test_memory_summary_contains_only_current_profile_and_active_feedback(
    completed_controller,
) -> None:
    controller = completed_controller
    candidate = controller.memory_service.create_candidate(
        subject_id=controller.subject_id,
        memory_type=MemoryType.USER_FEEDBACK,
        content="Candidate must not be authoritative",
        source_type=EvidenceSourceType.MODEL_INFERENCE,
    )
    archived = controller.memory_service.create_confirmed(
        subject_id=controller.subject_id,
        memory_type=MemoryType.USER_FEEDBACK,
        content="Archived feedback",
        source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
        confirmed_by_user=True,
    )
    controller.memory_service.archive(controller.subject_id, archived.memory_id)
    controller.answer_role_clarification("job_001", "很喜欢")
    active = controller.save_role_clarification("job_001")
    view = memory_summary_view(
        controller.current_profile_from_memory(),
        controller.active_memories(),
        controller.profile_history(),
    )
    assert active.content in view.user_feedback
    assert candidate.content not in view.user_feedback
    assert archived.content not in view.user_feedback
    assert view.profile_history == ("画像 v1 · 当前版本",)


def test_invalid_role_or_action_cannot_enter_session_state(completed_controller) -> None:
    controller = completed_controller
    with pytest.raises(DemoValidationError):
        controller.answer_role_clarification("job_unknown", "很喜欢")
    with pytest.raises(DemoValidationError):
        controller.set_action_status("action_unknown", "进行中")


def test_reset_cleanup_removes_only_its_temporary_database() -> None:
    controller = DemoController()
    path = Path(controller.memory_service.database.path)
    assert path.exists()
    controller.close()
    assert not path.exists()
