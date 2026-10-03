"""Offline checks for the narrow new-thread/canonical-profile compatibility seam."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest
from pydantic import ValidationError

from data.models import EventType, UserProfile
from memory.service import build_sqlite_memory_service
from workflows.langgraph_checkpoint import create_memory_checkpointer, sqlite_checkpointer
from workflows.langgraph_runtime import DEFAULT_SELECTED_JOB_IDS, build_public_offline_dependencies
from workflows.langgraph_state import (
    GraphWorkflowStatus, ProfileReviewAction, ProfileReviewDecision, UnknownWorkflowError,
)
from workflows.langgraph_workflow import (
    OrangeGraphRunner, build_orange_graph, create_initial_graph_state,
)
from workflows.stages import ProfileNotConfirmedError


SUBJECT = "subject_profile_reuse_test"


def _initial(workflow_id="reused_thread", *, subject_id=SUBJECT):
    return create_initial_graph_state(
        selected_job_ids=DEFAULT_SELECTED_JOB_IDS,
        checkpoint_mode="memory",
        workflow_id=workflow_id,
        subject_id=subject_id,
    )


def _runtime(tmp_path, *, checkpointer=None):
    service = build_sqlite_memory_service(tmp_path / "profile_reuse.sqlite3")
    dependencies = replace(build_public_offline_dependencies(), memory_service=service)
    runner = OrangeGraphRunner(build_orange_graph(
        dependencies=dependencies,
        checkpointer=checkpointer or create_memory_checkpointer(),
    ))
    paused = runner.start(_initial("original_confirmed_thread"))
    original = runner.resume(
        paused["workflow_id"],
        ProfileReviewDecision(action=ProfileReviewAction.CONFIRM),
    )
    assert original["workflow_status"] == GraphWorkflowStatus.COMPLETED.value
    return service, dependencies, runner, original


def _profile_rows(service):
    with service.database.connection() as connection:
        return [tuple(row) for row in connection.execute(
            "SELECT subject_id, profile_id, version, payload_json, semantic_hash, stored_at "
            "FROM profile_versions ORDER BY subject_id, profile_id, version"
        ).fetchall()]


def test_exact_canonical_version_enters_existing_protected_pipeline(tmp_path):
    service, _, runner, original = _runtime(tmp_path)
    canonical = service.get_current_confirmed_profile(SUBJECT)
    completed = runner.start_from_confirmed_profile(_initial(), memory_service=service)
    assert completed["workflow_status"] == GraphWorkflowStatus.COMPLETED.value
    assert completed["profile"] == canonical.model_dump(mode="json")
    assert completed["current_profile_ref"] == original["current_profile_ref"]
    assert completed["self_discovery_call_count"] == 0
    assert completed.get("__interrupt__", ()) == ()
    assert len(completed["job_intelligence"]) == 3
    assert len(completed["match_results"]) == 3
    assert completed["report"]["profile_id"] == canonical.profile_id
    completed_nodes = [item["node_name"] for item in completed["graph_events"]
                       if item["event_type"] == EventType.GRAPH_NODE_COMPLETED.value]
    assert completed_nodes == ["job_intelligence", "match_insight", "report"]


def test_reuse_preserves_stored_payload_bytes_and_all_timestamps(tmp_path):
    service, _, runner, _ = _runtime(tmp_path)
    canonical = service.get_current_confirmed_profile(SUBJECT)
    rows = _profile_rows(service)
    completed = runner.start_from_confirmed_profile(_initial(), memory_service=service)
    assert _profile_rows(service) == rows
    for field in ("created_at", "updated_at", "confirmed_at"):
        assert completed["profile"][field] == canonical.model_dump(mode="json")[field]
    assert service.get_current_confirmed_profile(SUBJECT) == canonical
    assert len(service.profile_store.list_profile_history(SUBJECT)) == 1


def test_reuse_never_discovers_confirms_or_saves_profile(tmp_path, monkeypatch):
    service, dependencies, runner, _ = _runtime(tmp_path)
    before_calls = dependencies.self_discovery_agent.llm_provider.call_count

    def forbidden(*args, **kwargs):
        raise AssertionError("Reuse must not discover, confirm or save a profile.")

    monkeypatch.setattr(dependencies.self_discovery_agent, "discover", forbidden)
    monkeypatch.setattr(UserProfile, "confirm", forbidden)
    monkeypatch.setattr(service, "save_confirmed_profile", forbidden)
    monkeypatch.setattr(service.profile_store, "save_confirmed_profile", forbidden)
    completed = runner.start_from_confirmed_profile(_initial(), memory_service=service)
    assert completed["workflow_status"] == GraphWorkflowStatus.COMPLETED.value
    assert dependencies.self_discovery_agent.llm_provider.call_count == before_calls


def test_multiple_fresh_threads_reference_one_authoritative_profile(tmp_path):
    service, _, runner, original = _runtime(tmp_path)
    before = deepcopy(runner.state(original["workflow_id"]))
    first = runner.start_from_confirmed_profile(_initial("new_a"), memory_service=service)
    second = runner.start_from_confirmed_profile(_initial("new_b"), memory_service=service)
    assert first["workflow_id"] != second["workflow_id"] != original["workflow_id"]
    assert first["current_profile_ref"] == second["current_profile_ref"] == original["current_profile_ref"]
    assert first["profile"] == second["profile"]
    assert runner.state(original["workflow_id"]) == before
    assert len(service.profile_store.list_profile_history(SUBJECT)) == 1


@pytest.mark.parametrize("workflow_id", ("original_confirmed_thread", "already_reused", "waiting_thread"))
def test_existing_workflow_cannot_be_restarted_at_reuse_entry(tmp_path, workflow_id):
    service, _, runner, _ = _runtime(tmp_path)
    if workflow_id == "already_reused":
        runner.start_from_confirmed_profile(_initial(workflow_id), memory_service=service)
    elif workflow_id == "waiting_thread":
        runner.start(_initial(workflow_id))
    before = deepcopy(runner.state(workflow_id))
    with pytest.raises(UnknownWorkflowError, match="cannot be restarted"):
        runner.start_from_confirmed_profile(_initial(workflow_id), memory_service=service)
    assert runner.state(workflow_id) == before


def test_absent_canonical_profile_keeps_confirmation_guard(tmp_path):
    service, _, runner, _ = _runtime(tmp_path)
    with pytest.raises(ProfileNotConfirmedError):
        runner.start_from_confirmed_profile(
            _initial(subject_id="subject_without_confirmation"), memory_service=service,
        )
    with pytest.raises(UnknownWorkflowError):
        runner.state("reused_thread")


def test_unconfirmed_profile_cannot_satisfy_reuse_entry(tmp_path, monkeypatch):
    service, _, runner, _ = _runtime(tmp_path)
    draft = service.get_current_confirmed_profile(SUBJECT).create_revision(education_summary="Draft only")
    monkeypatch.setattr(service, "get_current_confirmed_profile", lambda _: draft)
    with pytest.raises(ProfileNotConfirmedError):
        runner.start_from_confirmed_profile(_initial(), memory_service=service)
    with pytest.raises(UnknownWorkflowError):
        runner.state("reused_thread")


def test_malformed_canonical_result_is_rejected_before_checkpoint(tmp_path, monkeypatch):
    service, _, runner, _ = _runtime(tmp_path)
    malformed = service.get_current_confirmed_profile(SUBJECT).model_dump(mode="json")
    malformed["confirmed_at"] = None
    monkeypatch.setattr(service, "get_current_confirmed_profile", lambda _: malformed)
    with pytest.raises(ValidationError):
        runner.start_from_confirmed_profile(_initial(), memory_service=service)
    with pytest.raises(UnknownWorkflowError):
        runner.state("reused_thread")


@pytest.mark.parametrize("field,value", (
    ("profile", {"profile_id": "injected"}),
    ("current_profile_ref", {"subject_id": "different_subject", "profile_id": "injected", "version": 1}),
    ("self_discovery_call_count", 1),
    ("review_outcome", "confirm"),
    ("workflow_status", "waiting_for_human"),
    ("safe_error", {"category": "failed"}),
    ("report", {"status": "created"}),
    ("job_records", [{"job_id": "injected"}]),
    ("job_intelligence", [{"job_id": "injected"}]),
    ("match_results", [{"job_id": "injected"}]),
))
def test_reuse_accepts_only_fresh_state_not_caller_authority(tmp_path, field, value):
    service, _, runner, _ = _runtime(tmp_path)
    initial = _initial()
    initial[field] = value
    with pytest.raises(ValueError, match="fresh graph state"):
        runner.start_from_confirmed_profile(initial, memory_service=service)
    with pytest.raises(UnknownWorkflowError):
        runner.state("reused_thread")


@pytest.mark.parametrize("job_ids", ([], ["job_001", "job_001"], [""], [None], "job_001"))
def test_reuse_rejects_invalid_selected_jobs_before_checkpoint(tmp_path, job_ids):
    service, _, runner, _ = _runtime(tmp_path)
    initial = _initial()
    initial["selected_job_ids"] = job_ids
    with pytest.raises(ValueError, match="Selected job IDs"):
        runner.start_from_confirmed_profile(initial, memory_service=service)


@pytest.mark.parametrize("field,value", (("workflow_id", ""), ("workflow_id", None),
                                         ("subject_id", ""), ("subject_id", None)))
def test_reuse_requires_explicit_valid_identity(tmp_path, field, value):
    service, _, runner, _ = _runtime(tmp_path)
    initial = _initial()
    initial[field] = value
    with pytest.raises(ValueError):
        runner.start_from_confirmed_profile(initial, memory_service=service)


def test_subject_ownership_never_falls_back_to_another_confirmed_profile(tmp_path):
    service, _, runner, _ = _runtime(tmp_path)
    rows = _profile_rows(service)
    with pytest.raises(ProfileNotConfirmedError):
        runner.start_from_confirmed_profile(
            _initial(subject_id="subject_other_browser_scope"), memory_service=service,
        )
    assert _profile_rows(service) == rows
    assert service.get_current_confirmed_profile("subject_other_browser_scope") is None


def test_new_thread_resolves_latest_explicitly_confirmed_revision(tmp_path):
    service, _, runner, original = _runtime(tmp_path)
    first = service.get_current_confirmed_profile(SUBJECT)
    draft = first.create_revision(education_summary="Explicitly reviewed next-version summary")
    assert draft.version == first.version + 1 and not draft.confirmed
    assert service.get_current_confirmed_profile(SUBJECT) == first
    revision = draft.confirm()
    service.save_confirmed_profile(SUBJECT, revision)
    rows = _profile_rows(service)
    completed = runner.start_from_confirmed_profile(_initial(), memory_service=service)
    assert completed["profile"] == revision.model_dump(mode="json")
    assert completed["current_profile_ref"]["version"] == revision.version
    assert _profile_rows(service) == rows
    assert runner.state(original["workflow_id"])["profile"] == first.model_dump(mode="json")


def test_profile_reuse_does_not_mutate_caller_initial_state(tmp_path):
    service, _, runner, _ = _runtime(tmp_path)
    initial = _initial()
    before = deepcopy(initial)
    runner.start_from_confirmed_profile(initial, memory_service=service)
    assert initial == before


def test_reused_thread_checkpoint_is_reopenable_without_reexecution(tmp_path):
    checkpoint_path = tmp_path / "reuse_checkpoints.sqlite3"
    with sqlite_checkpointer(checkpoint_path) as checkpointer:
        service, _, runner, _ = _runtime(tmp_path, checkpointer=checkpointer)
        completed = runner.start_from_confirmed_profile(_initial(), memory_service=service)
    dependencies = replace(build_public_offline_dependencies(), memory_service=service)
    with sqlite_checkpointer(checkpoint_path) as checkpointer:
        reopened = OrangeGraphRunner(build_orange_graph(dependencies=dependencies, checkpointer=checkpointer))
        state = reopened.state("reused_thread")
        assert state["profile"] == completed["profile"]
        assert state["current_profile_ref"] == completed["current_profile_ref"]
        assert state["report"] == completed["report"]
        assert dependencies.self_discovery_agent.llm_provider.call_count == 0
        assert dependencies.job_intelligence_agent.llm_provider.call_count == 0
        assert dependencies.match_insight_agent.llm_provider.call_count == 0


def test_reuse_events_remain_safe_and_do_not_claim_new_confirmation(tmp_path):
    service, _, runner, _ = _runtime(tmp_path)
    completed = runner.start_from_confirmed_profile(_initial(), memory_service=service)
    binding = [item for item in completed["graph_events"]
               if item["event_type"] == EventType.CHECKPOINT_CREATED.value]
    assert len(binding) == 1
    assert "already confirmed" in binding[0]["summary"]
    assert set(binding[0]["safe_metadata"]) == {"checkpoint_mode", "profile_version"}
    assert not any(item["event_type"] == EventType.GRAPH_RESUMED.value
                   for item in completed["graph_events"])


def test_creation_time_reference_does_not_upgrade_when_current_version_changes(tmp_path):
    service, _, runner, original = _runtime(tmp_path)
    first = service.get_current_confirmed_profile(SUBJECT)
    revision = first.create_revision(education_summary="Later explicitly reviewed update").confirm()
    service.save_confirmed_profile(SUBJECT, revision)
    rows = _profile_rows(service)
    pinned = runner.start_from_confirmed_profile(
        _initial("thread_created_before_revision"), memory_service=service,
        profile_reference=original["current_profile_ref"],
    )
    assert pinned["profile"] == first.model_dump(mode="json")
    assert pinned["current_profile_ref"] == original["current_profile_ref"]
    assert service.get_current_confirmed_profile(SUBJECT) == revision
    assert _profile_rows(service) == rows


def test_reference_from_another_subject_cannot_bind_workflow(tmp_path):
    service, _, runner, original = _runtime(tmp_path)
    reference = {**original["current_profile_ref"], "subject_id": "subject_someone_else"}
    with pytest.raises(ValueError, match="belong to the workflow subject"):
        runner.start_from_confirmed_profile(
            _initial(), memory_service=service, profile_reference=reference,
        )
    with pytest.raises(UnknownWorkflowError):
        runner.state("reused_thread")


@pytest.mark.parametrize("reference_change", ({"profile_id": "missing_profile"}, {"version": 99}))
def test_missing_owned_profile_reference_does_not_fallback_to_current(tmp_path, reference_change):
    service, _, runner, original = _runtime(tmp_path)
    reference = {**original["current_profile_ref"], **reference_change}
    with pytest.raises(ProfileNotConfirmedError):
        runner.start_from_confirmed_profile(
            _initial(), memory_service=service, profile_reference=reference,
        )
    with pytest.raises(UnknownWorkflowError):
        runner.state("reused_thread")


def test_reopened_waiting_checkpoint_restores_real_interrupt_without_execution(tmp_path, monkeypatch):
    service, dependencies, runner, _ = _runtime(tmp_path)
    waiting = runner.start(_initial("unfinished_thread"))
    before = deepcopy(runner.state("unfinished_thread"))

    def forbidden(*args, **kwargs):
        raise AssertionError("Reading an existing checkpoint must not execute or save.")

    for agent in (dependencies.self_discovery_agent, dependencies.job_intelligence_agent,
                  dependencies.match_insight_agent):
        monkeypatch.setattr(agent, "discover" if agent is dependencies.self_discovery_agent else "analyze", forbidden)
    monkeypatch.setattr(service, "save_confirmed_profile", forbidden)
    for _ in range(3):
        reopened = runner.checkpoint_state("unfinished_thread", subject_id=SUBJECT)
        assert reopened["profile"] == waiting["profile"]
        assert reopened["workflow_status"] == GraphWorkflowStatus.WAITING_FOR_HUMAN.value
        assert reopened["__interrupt__"][0].value == waiting["__interrupt__"][0].value
    assert runner.state("unfinished_thread") == before


def test_checkpoint_read_preserves_historical_profile_version(tmp_path):
    service, _, runner, original = _runtime(tmp_path)
    first = service.get_current_confirmed_profile(SUBJECT)
    service.save_confirmed_profile(SUBJECT, first.create_revision(education_summary="Later version").confirm())
    reopened = runner.checkpoint_state(original["workflow_id"], subject_id=SUBJECT)
    assert reopened["profile"] == first.model_dump(mode="json")
    assert reopened["current_profile_ref"]["version"] == 1
    assert "__interrupt__" not in reopened


@pytest.mark.parametrize("workflow_id,subject_id", (("unknown_thread", SUBJECT),
                                                    ("original_confirmed_thread", "subject_other_scope")))
def test_checkpoint_read_rejects_unknown_or_unowned_thread(tmp_path, workflow_id, subject_id):
    _, _, runner, _ = _runtime(tmp_path)
    with pytest.raises(UnknownWorkflowError, match="No owned checkpoint"):
        runner.checkpoint_state(workflow_id, subject_id=subject_id)


def test_persisted_waiting_thread_reopens_and_resumes_same_original_draft(tmp_path):
    service = build_sqlite_memory_service(tmp_path / "waiting_profiles.sqlite3")
    dependencies = replace(build_public_offline_dependencies(), memory_service=service)
    checkpoint_path = tmp_path / "waiting_checkpoints.sqlite3"
    with sqlite_checkpointer(checkpoint_path) as checkpointer:
        runner = OrangeGraphRunner(build_orange_graph(dependencies=dependencies, checkpointer=checkpointer))
        waiting = runner.start(_initial("persistent_waiting_thread"))
    reopened_dependencies = replace(build_public_offline_dependencies(), memory_service=service)
    with sqlite_checkpointer(checkpoint_path) as checkpointer:
        reopened = OrangeGraphRunner(build_orange_graph(dependencies=reopened_dependencies, checkpointer=checkpointer))
        state = reopened.checkpoint_state("persistent_waiting_thread", subject_id=SUBJECT)
        assert state["profile"] == waiting["profile"]
        assert state["__interrupt__"][0].value == waiting["__interrupt__"][0].value
        completed = reopened.resume("persistent_waiting_thread", ProfileReviewDecision(action=ProfileReviewAction.CONFIRM))
        assert completed["workflow_status"] == GraphWorkflowStatus.COMPLETED.value
        assert completed["profile"]["created_at"] == waiting["profile"]["created_at"]
        assert reopened_dependencies.self_discovery_agent.llm_provider.call_count == 0
        assert len(service.profile_store.list_profile_history(SUBJECT)) == 1
