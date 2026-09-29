"""Offline orchestration, interrupt, routing and failure tests."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest

from data.models import CareerReport, EventType, UserProfile
from providers.errors import LLMTimeoutError
from providers.fake import FakeLLMProvider
from workflows.langgraph_checkpoint import create_memory_checkpointer
from workflows.langgraph_runtime import (
    DEFAULT_SELECTED_JOB_IDS,
    build_public_offline_dependencies,
)
from workflows.langgraph_state import (
    GraphErrorCategory,
    GraphWorkflowStatus,
    ProfileReviewAction,
    ProfileReviewDecision,
    UnknownWorkflowError,
)
from workflows.langgraph_workflow import (
    OrangeGraphRunner,
    build_orange_graph,
    create_initial_graph_state,
)
from workflows.stages import ProfileNotConfirmedError


def _runner(dependencies=None):
    dependencies = dependencies or build_public_offline_dependencies()
    graph = build_orange_graph(
        dependencies=dependencies,
        checkpointer=create_memory_checkpointer(),
    )
    return dependencies, OrangeGraphRunner(graph)


def _start(runner: OrangeGraphRunner, workflow_id: str = "phase6_test"):
    return runner.start(
        create_initial_graph_state(
            selected_job_ids=DEFAULT_SELECTED_JOB_IDS,
            checkpoint_mode="memory",
            workflow_id=workflow_id,
        )
    )


def _confirm(runner: OrangeGraphRunner, workflow_id: str):
    return runner.resume(
        workflow_id,
        ProfileReviewDecision(action=ProfileReviewAction.CONFIRM),
    )


def test_default_dependencies_are_fake_and_never_construct_qwen() -> None:
    dependencies = build_public_offline_dependencies()
    assert isinstance(dependencies.self_discovery_agent.llm_provider, FakeLLMProvider)
    assert isinstance(dependencies.job_intelligence_agent.llm_provider, FakeLLMProvider)
    assert isinstance(dependencies.match_insight_agent.llm_provider, FakeLLMProvider)
    assert all(
        "qwen" not in type(value).__module__.casefold()
        for value in (
            dependencies.self_discovery_agent.llm_provider,
            dependencies.job_intelligence_agent.llm_provider,
            dependencies.match_insight_agent.llm_provider,
        )
    )


def test_graph_calls_existing_agents_and_deterministic_report(monkeypatch) -> None:
    dependencies = build_public_offline_dependencies()
    calls = {"self": 0, "job": 0, "match": 0, "report": 0}

    original_self = dependencies.self_discovery_agent.discover
    original_job = dependencies.job_intelligence_agent.analyze
    original_match = dependencies.match_insight_agent.analyze
    original_report = dependencies.report_builder.build

    def self_spy(*args, **kwargs):
        calls["self"] += 1
        return original_self(*args, **kwargs)

    def job_spy(*args, **kwargs):
        calls["job"] += 1
        return original_job(*args, **kwargs)

    def match_spy(*args, **kwargs):
        calls["match"] += 1
        return original_match(*args, **kwargs)

    def report_spy(*args, **kwargs):
        calls["report"] += 1
        return original_report(*args, **kwargs)

    monkeypatch.setattr(dependencies.self_discovery_agent, "discover", self_spy)
    monkeypatch.setattr(dependencies.job_intelligence_agent, "analyze", job_spy)
    monkeypatch.setattr(dependencies.match_insight_agent, "analyze", match_spy)
    monkeypatch.setattr(dependencies.report_builder, "build", report_spy)

    _, runner = _runner(dependencies)
    paused = _start(runner, "agent_spy")
    completed = _confirm(runner, "agent_spy")
    assert paused["workflow_status"] == GraphWorkflowStatus.WAITING_FOR_HUMAN.value
    assert calls == {"self": 1, "job": 3, "match": 3, "report": 1}
    assert completed["workflow_status"] == GraphWorkflowStatus.COMPLETED.value


def test_interrupt_is_real_safe_waiting_state_not_failure() -> None:
    _, runner = _runner()
    paused = _start(runner, "safe_interrupt")
    assert paused["workflow_status"] == GraphWorkflowStatus.WAITING_FOR_HUMAN.value
    assert paused["safe_error"] is None
    assert paused["job_intelligence"] == []
    assert paused["match_results"] == []
    assert paused["report"] is None
    interrupt_item = paused["__interrupt__"][0]
    payload = interrupt_item.value
    assert payload["kind"] == "profile_review"
    assert payload["profile"]["confirmed"] is False
    assert payload["profile"]["skills"]
    serialized = json.dumps(payload, ensure_ascii=False).casefold()
    for forbidden in ("api_key", "authorization", "raw prompt", "chain-of-thought", "evidence_ids"):
        assert forbidden not in serialized


def test_confirm_resumes_same_thread_without_rerunning_self_discovery() -> None:
    dependencies, runner = _runner()
    paused = _start(runner, "same_thread")
    before_calls = dependencies.self_discovery_agent.llm_provider.call_count
    completed = _confirm(runner, paused["workflow_id"])
    assert completed["workflow_id"] == paused["workflow_id"]
    assert completed["self_discovery_call_count"] == 1
    assert dependencies.self_discovery_agent.llm_provider.call_count == before_calls == 1
    assert UserProfile.model_validate(completed["profile"]).confirmed is True
    assert len(completed["job_intelligence"]) == 3
    assert len(completed["match_results"]) == 3
    assert isinstance(CareerReport.model_validate(completed["report"]), CareerReport)


def test_revision_preserves_immutability_and_requires_second_review() -> None:
    dependencies, runner = _runner()
    paused = _start(runner, "revision_thread")
    original_profile = deepcopy(paused["profile"])
    revised = runner.resume(
        "revision_thread",
        ProfileReviewDecision(
            action=ProfileReviewAction.REVISE,
            education_summary="Revised public education summary",
        ),
    )
    assert paused["profile"] == original_profile
    assert revised["profile"]["version"] == original_profile["version"] + 1
    assert revised["profile"]["confirmed"] is False
    assert revised["workflow_status"] == GraphWorkflowStatus.WAITING_FOR_HUMAN.value
    assert revised["__interrupt__"]
    assert revised["job_intelligence"] == []
    assert dependencies.self_discovery_agent.llm_provider.call_count == 1
    completed = _confirm(runner, "revision_thread")
    assert completed["profile"]["version"] == 2
    assert completed["profile"]["confirmed"] is True


def test_match_domain_guard_still_blocks_unconfirmed_profile() -> None:
    dependencies = build_public_offline_dependencies()
    courses = dependencies.self_discovery_agent.course_provider.load()
    draft = dependencies.self_discovery_agent.discover(
        dict(dependencies.self_discovery_input), courses
    ).user_profile
    jobs = dependencies.job_intelligence_agent.job_provider.load()
    job = next(item for item in jobs if item.job_id == DEFAULT_SELECTED_JOB_IDS[0])
    intelligence = dependencies.job_intelligence_agent.analyze(job)
    with pytest.raises(ProfileNotConfirmedError):
        dependencies.match_insight_agent.analyze(draft, intelligence)


def test_node_order_is_deterministic_and_has_no_score_or_ranking() -> None:
    _, runner = _runner()
    _start(runner, "order_thread")
    completed = _confirm(runner, "order_thread")
    completed_nodes = [
        event["node_name"]
        for event in completed["graph_events"]
        if event["event_type"] == EventType.GRAPH_NODE_COMPLETED.value
    ]
    assert completed_nodes == [
        "self_discovery",
        "profile_review_gate",
        "job_intelligence",
        "match_insight",
        "report",
    ]
    serialized = json.dumps(completed, ensure_ascii=False).casefold()
    assert '"overall_score"' not in serialized
    assert '"ranking"' not in serialized


def test_provider_failure_becomes_sanitized_failed_state(monkeypatch) -> None:
    dependencies = build_public_offline_dependencies()

    def fail(*args, **kwargs):
        raise LLMTimeoutError("sensitive provider details must not escape")

    monkeypatch.setattr(dependencies.self_discovery_agent, "discover", fail)
    _, runner = _runner(dependencies)
    failed = _start(runner, "provider_failure")
    assert failed["workflow_status"] == GraphWorkflowStatus.FAILED.value
    assert failed["safe_error"]["category"] == GraphErrorCategory.PROVIDER_FAILURE.value
    assert "sensitive" not in json.dumps(failed["safe_error"]).casefold()
    assert failed["profile"] is None


def test_validation_failure_becomes_sanitized_failed_state(monkeypatch) -> None:
    dependencies = build_public_offline_dependencies()

    def fail(*args, **kwargs):
        raise ValueError("raw invalid private payload")

    monkeypatch.setattr(dependencies.self_discovery_agent, "discover", fail)
    _, runner = _runner(dependencies)
    failed = _start(runner, "validation_failure")
    assert failed["workflow_status"] == GraphWorkflowStatus.FAILED.value
    assert failed["safe_error"]["category"] == GraphErrorCategory.VALIDATION_FAILURE.value
    assert "private payload" not in json.dumps(failed["safe_error"]).casefold()


def test_workflow_ids_are_isolated_and_wrong_resume_is_rejected() -> None:
    _, runner = _runner()
    first = _start(runner, "isolated_a")
    second = _start(runner, "isolated_b")
    completed = _confirm(runner, "isolated_a")
    assert completed["workflow_id"] == "isolated_a"
    assert runner.state("isolated_b")["workflow_status"] == GraphWorkflowStatus.WAITING_FOR_HUMAN.value
    assert first["profile"]["profile_id"] == second["profile"]["profile_id"]
    with pytest.raises(UnknownWorkflowError):
        _confirm(runner, "does_not_exist")


def test_graph_events_are_safe_and_structured() -> None:
    _, runner = _runner()
    _start(runner, "safe_events")
    completed = _confirm(runner, "safe_events")
    event_types = {event["event_type"] for event in completed["graph_events"]}
    assert {
        EventType.GRAPH_RUN_STARTED.value,
        EventType.GRAPH_INTERRUPTED.value,
        EventType.GRAPH_RESUMED.value,
        EventType.CHECKPOINT_CREATED.value,
        EventType.CHECKPOINT_RESUMED.value,
        EventType.GRAPH_COMPLETED.value,
    }.issubset(event_types)
    serialized = json.dumps(completed["graph_events"], ensure_ascii=False).casefold()
    for forbidden in ("authorization", "api_key", "raw prompt", "chain-of-thought"):
        assert forbidden not in serialized
