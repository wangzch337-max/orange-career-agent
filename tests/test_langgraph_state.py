"""Focused contract and privacy tests for Phase 6 graph state."""

from typing import get_type_hints

import pytest
from pydantic import ValidationError

from workflows.langgraph_state import (
    GraphErrorCategory,
    GraphWorkflowStatus,
    OrangeGraphState,
    ProfileReviewAction,
    ProfileReviewDecision,
    SafeGraphError,
)
from workflows.langgraph_workflow import create_initial_graph_state


def test_langgraph_dependency_is_available() -> None:
    import langgraph
    from langgraph.checkpoint.sqlite import SqliteSaver

    assert langgraph is not None
    assert SqliteSaver is not None


def test_orange_graph_state_is_explicit_and_excludes_runtime_objects() -> None:
    fields = set(get_type_hints(OrangeGraphState))
    assert fields == {
        "workflow_id",
        "subject_id",
        "workflow_status",
        "checkpoint_mode",
        "selected_job_ids",
        "profile",
        "current_profile_ref",
        "profile_uncertainties",
        "clarification_questions",
        "self_discovery_metadata",
        "job_records",
        "job_intelligence",
        "match_results",
        "report",
        "graph_events",
        "safe_error",
        "review_outcome",
        "self_discovery_call_count",
    }
    forbidden = {"provider", "client", "connection", "credentials", "api_key", "prompt", "messages", "user_input", "memory_service", "memory_store", "retriever"}
    assert fields.isdisjoint(forbidden)


def test_initial_state_has_opaque_identity_and_no_credentials() -> None:
    state = create_initial_graph_state(
        selected_job_ids=("job_001",), checkpoint_mode="memory"
    )
    assert state["workflow_id"].startswith("orange_")
    assert state["workflow_status"] == GraphWorkflowStatus.RUNNING.value
    assert "api" not in str(state).casefold()
    assert "authorization" not in str(state).casefold()


def test_selected_jobs_must_be_nonempty_and_unique() -> None:
    with pytest.raises(ValueError):
        create_initial_graph_state(selected_job_ids=(), checkpoint_mode="memory")
    with pytest.raises(ValueError):
        create_initial_graph_state(
            selected_job_ids=("job_001", "job_001"), checkpoint_mode="memory"
        )


def test_profile_review_decision_is_minimal_and_strict() -> None:
    confirm = ProfileReviewDecision(action=ProfileReviewAction.CONFIRM)
    revise = ProfileReviewDecision(
        action=ProfileReviewAction.REVISE,
        education_summary="Updated public education summary",
    )
    assert confirm.revision_changes() == {}
    assert revise.revision_changes() == {
        "education_summary": "Updated public education summary"
    }
    with pytest.raises(ValidationError):
        ProfileReviewDecision(action=ProfileReviewAction.REVISE)
    with pytest.raises(ValidationError):
        ProfileReviewDecision(action="confirm", unrelated_command=True)


def test_safe_graph_error_has_distinct_categories() -> None:
    error = SafeGraphError(
        category=GraphErrorCategory.PROVIDER_FAILURE,
        node_name="self_discovery",
        message="Provider failed safely.",
        retryable=True,
    )
    assert error.category != GraphErrorCategory.VALIDATION_FAILURE
    assert GraphWorkflowStatus.WAITING_FOR_HUMAN != GraphWorkflowStatus.FAILED
