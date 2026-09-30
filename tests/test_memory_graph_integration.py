"""Minimal idempotent LangGraph-to-memory persistence boundary tests."""

from __future__ import annotations

import json
from dataclasses import replace

from memory.service import build_sqlite_memory_service
from workflows.langgraph_checkpoint import create_memory_checkpointer
from workflows.langgraph_runtime import (
    DEFAULT_SELECTED_JOB_IDS,
    build_public_offline_dependencies,
)
from workflows.langgraph_state import ProfileReviewAction, ProfileReviewDecision
from workflows.langgraph_workflow import (
    OrangeGraphRunner,
    build_orange_graph,
    create_initial_graph_state,
)


def test_confirmed_profile_is_persisted_at_explicit_graph_boundary(tmp_path) -> None:
    service = build_sqlite_memory_service(tmp_path / "memory.sqlite3")
    dependencies = replace(
        build_public_offline_dependencies(), memory_service=service
    )
    runner = OrangeGraphRunner(
        build_orange_graph(
            dependencies=dependencies,
            checkpointer=create_memory_checkpointer(),
        )
    )
    initial = create_initial_graph_state(
        selected_job_ids=DEFAULT_SELECTED_JOB_IDS,
        checkpoint_mode="memory",
        workflow_id="memory_integration_workflow",
        subject_id="subject_graph001",
    )
    paused = runner.start(initial)
    assert service.get_current_confirmed_profile("subject_graph001") is None
    completed = runner.resume(
        paused["workflow_id"],
        ProfileReviewDecision(action=ProfileReviewAction.CONFIRM),
    )
    stored = service.get_current_confirmed_profile("subject_graph001")
    assert stored is not None and stored.confirmed is True
    assert completed["current_profile_ref"] == {
        "subject_id": "subject_graph001",
        "profile_id": stored.profile_id,
        "version": stored.version,
    }


def test_graph_confirmation_side_effect_is_idempotent_under_replay(tmp_path, monkeypatch) -> None:
    service = build_sqlite_memory_service(tmp_path / "memory.sqlite3")
    original_save = service.save_confirmed_profile
    save_calls = 0

    def replaying_save(subject_id, profile):
        nonlocal save_calls
        save_calls += 1
        first = original_save(subject_id, profile)
        repeated = original_save(subject_id, profile)
        assert repeated.created is False
        return first

    monkeypatch.setattr(service, "save_confirmed_profile", replaying_save)
    dependencies = replace(
        build_public_offline_dependencies(), memory_service=service
    )
    runner = OrangeGraphRunner(
        build_orange_graph(
            dependencies=dependencies,
            checkpointer=create_memory_checkpointer(),
        )
    )
    paused = runner.start(
        create_initial_graph_state(
            selected_job_ids=DEFAULT_SELECTED_JOB_IDS,
            checkpoint_mode="memory",
            workflow_id="memory_replay_workflow",
            subject_id="subject_graph002",
        )
    )
    runner.resume(
        paused["workflow_id"],
        ProfileReviewDecision(action=ProfileReviewAction.CONFIRM),
    )
    assert save_calls == 1
    assert len(service.profile_store.list_profile_history("subject_graph002")) == 1


def test_graph_checkpoint_state_contains_references_not_memory_services(tmp_path) -> None:
    service = build_sqlite_memory_service(tmp_path / "memory.sqlite3")
    dependencies = replace(
        build_public_offline_dependencies(), memory_service=service
    )
    runner = OrangeGraphRunner(
        build_orange_graph(
            dependencies=dependencies,
            checkpointer=create_memory_checkpointer(),
        )
    )
    paused = runner.start(
        create_initial_graph_state(
            selected_job_ids=DEFAULT_SELECTED_JOB_IDS,
            checkpoint_mode="memory",
            workflow_id="memory_state_workflow",
            subject_id="subject_graph003",
        )
    )
    serialized = json.dumps(paused, ensure_ascii=False, default=str).casefold()
    assert "memoryservice" not in serialized
    assert "sqlitememorystore" not in serialized
    assert "sqlite3.connection" not in serialized
    assert "api_key" not in serialized
