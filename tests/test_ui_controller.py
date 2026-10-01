"""Controller tests for the public, offline Orange vertical slice."""

from __future__ import annotations

from pathlib import Path

import pytest

from data.models import CareerReport, EvidenceSourceType, UserProfile
from memory.models import MemoryStatus, MemoryType
from providers.fake import FakeLLMProvider
from ui.demo_controller import (
    APPROVED_ROLE_IDS,
    APPROVED_ROLE_TITLES,
    DemoController,
)
from workflows.langgraph_state import GraphWorkflowStatus


@pytest.fixture
def controller():
    item = DemoController()
    yield item
    item.close()


def test_public_demo_controller_uses_only_fake_providers_and_temporary_memory(
    controller,
) -> None:
    assert APPROVED_ROLE_IDS == ("job_001", "job_007", "job_013")
    providers = (
        controller.dependencies.self_discovery_agent.llm_provider,
        controller.dependencies.job_intelligence_agent.llm_provider,
        controller.dependencies.match_insight_agent.llm_provider,
    )
    assert all(isinstance(provider, FakeLLMProvider) for provider in providers)
    memory_path = controller.memory_service.database.path
    assert memory_path.name == "orange_demo_memory.sqlite3"
    assert "data/private" not in memory_path.as_posix()
    assert memory_path != Path("data/private/memory/orange_memory.sqlite3").resolve()


def test_start_reaches_real_graph_interrupt_and_is_rerun_idempotent(controller) -> None:
    paused = controller.start()
    first_call_count = controller.dependencies.self_discovery_agent.llm_provider.call_count
    repeated = controller.start()
    assert repeated is paused
    assert paused["workflow_status"] == GraphWorkflowStatus.WAITING_FOR_HUMAN.value
    assert paused["self_discovery_call_count"] == 1
    assert first_call_count == 1
    assert controller.dependencies.self_discovery_agent.llm_provider.call_count == 1
    assert paused["job_intelligence"] == []
    assert paused["match_results"] == []
    assert paused["report"] is None
    assert paused["__interrupt__"]
    assert controller.profile_review_payload()["kind"] == "profile_review"


def test_confirm_resumes_same_thread_and_completes_without_rediscovery(controller) -> None:
    paused = controller.start()
    workflow_id = paused["workflow_id"]
    before_calls = controller.dependencies.self_discovery_agent.llm_provider.call_count
    completed = controller.confirm_profile()
    assert completed["workflow_id"] == workflow_id == controller.workflow_id
    assert completed["workflow_status"] == GraphWorkflowStatus.COMPLETED.value
    assert completed["self_discovery_call_count"] == 1
    assert controller.dependencies.self_discovery_agent.llm_provider.call_count == before_calls == 1
    assert isinstance(controller.confirmed_profile(), UserProfile)
    assert controller.confirmed_profile().confirmed is True
    assert isinstance(controller.report(), CareerReport)


def test_exactly_three_roles_preserve_approved_order_and_domain_outputs(controller) -> None:
    controller.start()
    controller.confirm_profile()
    assert tuple(item.title for item in controller.job_records()) == APPROVED_ROLE_TITLES
    assert tuple(item.role_title for item in controller.job_intelligence()) == (
        APPROVED_ROLE_TITLES
    )
    assert tuple(item.role_title for item in controller.match_results()) == (
        APPROVED_ROLE_TITLES
    )
    assert len(controller.report().role_insights) == 3


def test_memory_summary_uses_graph_profile_and_phase7c_public_scenario(controller) -> None:
    assert controller.current_profile_from_memory() is None
    controller.start()
    controller.confirm_profile()
    profile = controller.current_profile_from_memory()
    assert profile is not None and profile.confirmed is True
    assert profile.version == 1
    assert {item.metadata.get("signal_dimension") for item in controller.active_memories()} == {
        "work_style.primary_focus",
        "work_style.documentation_tolerance",
    }
    assert [item.version for item in controller.profile_history()] == [1]


def test_memory_summary_never_treats_non_active_history_as_active(controller) -> None:
    service = controller.memory_service
    candidate = service.create_candidate(
        subject_id=controller.subject_id,
        memory_type=MemoryType.CAREER_INSIGHT,
        content="Synthetic candidate",
        source_type=EvidenceSourceType.MODEL_INFERENCE,
    )
    confirmed = service.create_confirmed(
        subject_id=controller.subject_id,
        memory_type=MemoryType.GOAL,
        content="Synthetic confirmed goal",
        source_type=EvidenceSourceType.SYSTEM_FIXTURE,
        confirmed_by_user=True,
    )
    superseding = service.supersede(
        controller.subject_id,
        confirmed.memory_id,
        content="Synthetic replacement goal",
        source_type=EvidenceSourceType.SYSTEM_FIXTURE,
        confirmed_by_user=True,
    )
    archived = service.create_confirmed(
        subject_id=controller.subject_id,
        memory_type=MemoryType.USER_FEEDBACK,
        content="Synthetic feedback",
        source_type=EvidenceSourceType.SYSTEM_FIXTURE,
        confirmed_by_user=True,
    )
    service.archive(controller.subject_id, archived.memory_id)
    active = controller.active_memories()
    assert superseding.memory_id in {item.memory_id for item in active}
    assert {item.memory_id for item in active}.issuperset(
        {"memory_demo_hands_on_preference", "memory_demo_documentation_tolerance"}
    )
    history_status = {
        item.memory_id: item.status
        for item in service.memory_store.list_history(controller.subject_id)
    }
    assert history_status[candidate.memory_id] == MemoryStatus.CANDIDATE
    assert history_status[confirmed.memory_id] == MemoryStatus.SUPERSEDED
    assert history_status[archived.memory_id] == MemoryStatus.ARCHIVED


def test_independent_controller_sessions_do_not_share_state_or_storage() -> None:
    first = DemoController()
    second = DemoController()
    try:
        assert first.workflow_id != second.workflow_id
        assert first.subject_id != second.subject_id
        assert first.checkpointer is not second.checkpointer
        assert first.memory_service.database.path != second.memory_service.database.path
        first.start()
        assert second.state is None
        assert second.current_profile_from_memory() is None
    finally:
        first.close()
        second.close()


def test_safe_trace_contains_only_allowlisted_execution_metadata(controller) -> None:
    controller.start()
    controller.confirm_profile()
    trace = controller.safe_trace()
    assert trace
    assert {item["event_type"] for item in trace}.issuperset(
        {"graph_run_started", "graph_interrupted", "graph_resumed", "graph_completed"}
    )
    serialized = str(trace).casefold()
    for forbidden in (
        "api_key",
        "authorization",
        "raw prompt",
        "chain-of-thought",
        "project_experience",
    ):
        assert forbidden not in serialized
