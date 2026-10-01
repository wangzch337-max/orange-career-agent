"""Production invariants, diagnostics privacy, evaluation links and developer UI."""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from evaluation.boundaries import OfflineBoundary
from evaluation.runner import EvaluationRunner, OUTPUT_ROOT
from evaluation.models import EvaluationStatus
from observability.collector import DiagnosticEventCollector
from observability.context import diagnostic_scope, current_binding
from observability.diagnostics import safe_event_view
from observability.models import ObservabilityContext, DiagnosticComponent as C, DiagnosticStatus as S, run_id
from memory.models import MemoryChangeChoice
from ui.demo_controller import DemoController


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def completed():
    controller = DemoController()
    try:
        controller.start(); controller.confirm_profile()
        yield controller
    finally:
        controller.close()


def dump(controller):
    return json.dumps([safe_event_view(e) for e in controller.diagnostics_snapshot()["events"]], ensure_ascii=False)


def test_phase8a_checkpoint_and_no_telemetry_dependencies():
    messages = subprocess.check_output(["git", "log", "--format=%s", "-10"], cwd=ROOT, text=True)
    assert "feat: add scenario-based evaluation framework" in messages
    requirements = (ROOT / "requirements.txt").read_text().casefold()
    for dependency in ("langsmith", "langfuse", "sentry", "datadog", "opentelemetry", "posthog", "mixpanel"):
        assert dependency not in requirements
    for path in (ROOT / "observability").glob("*.py"):
        source = path.read_text()
        assert "import httpx" not in source and "import requests" not in source


def test_workflow_interrupt_resume_same_run_self_discovery_once_and_no_render_recording():
    controller = DemoController()
    try:
        identity = controller.diagnostic_context.run_id
        controller.start()
        waiting = controller.diagnostics_snapshot()
        assert waiting["summary"].workflow_status == "waiting_for_human" and waiting["summary"].status == S.WAITING
        assert any(e.source_event_type and e.source_event_type.value == "graph_interrupted" for e in waiting["events"])
        before = len(waiting["events"])
        controller.start(); controller.diagnostics_snapshot(); controller.safe_trace()
        assert len(controller.diagnostics_snapshot()["events"]) == before
        controller.confirm_profile()
        events = controller.diagnostics_snapshot()["events"]
        assert controller.diagnostic_context.run_id == identity
        assert sum(e.operation == "self_discovery_run" and e.status == S.SUCCEEDED for e in events) == 1
        assert any(e.source_event_type and e.source_event_type.value == "graph_resumed" for e in events)
        assert controller.state["self_discovery_call_count"] == 1 and controller.diagnostics_snapshot()["summary"].recording_failure_count == 0
    finally:
        controller.close()


@pytest.mark.parametrize("component,operation", [(C.SELF_DISCOVERY, "self_discovery_run"),
    (C.JOB_INTELLIGENCE, "job_intelligence_run"), (C.MATCH_INSIGHT, "match_run"), (C.PROVIDER, "provider_call")])
def test_actual_component_counts_and_durations(completed, component, operation):
    events = completed.diagnostic_collector.timeline(completed.diagnostic_context.run_id, component)
    finished = [e for e in events if e.operation == operation and e.status == S.SUCCEEDED]
    assert finished and all(e.duration_ms is not None and e.duration_ms >= 0 for e in finished)
    assert all(e.counts["provider_call_count"] == 1 for e in finished)
    if component == C.MATCH_INSIGHT:
        counts = [e.counts for e in finished]
        assert [c["relation_count"] for c in counts] == [len(result.insights()) for result in completed.match_results()]
        assert [c["action_count"] for c in counts] == [len(result.action_items) for result in completed.match_results()]
    assert not completed.memory_context_coordinator.events  # JI/Match still do not consume Memory


def test_product_content_prompts_profiles_and_evidence_absent(completed):
    completed.role_memory_context("job_001")
    text = dump(completed)
    profile = completed.confirmed_profile()
    for evidence in profile.evidence:
        assert evidence.statement not in text
    for memory in completed.active_memories():
        assert memory.content not in text
    for record in completed.job_records():
        assert record.description not in text
    for result in completed.match_results():
        for insight in result.insights():
            assert insight.description not in text
    for forbidden in ("chain_of_thought", "hidden_reasoning", "profile_json", "memory_content", "api_key", "Authorization", "overall_score"):
        assert forbidden not in text


def test_memory_recall_change_defer_update_and_profile_confirmation(completed):
    before_match = completed.match_for("job_001").model_dump()
    service, subject = completed.memory_service, completed.subject_id
    completed.role_memory_context("job_001")
    before = service.memory_store.list_history(subject)
    candidate = completed.submit_structured_preference(dimension="work_style.primary_focus", value="product_and_requirement_work",
                                                      display_label="SENSITIVE_SENTINEL")
    completed.resolve_memory_change(candidate.candidate_id, MemoryChangeChoice.DEFER)
    assert service.memory_store.list_history(subject) == before
    candidate = completed.submit_structured_preference(dimension="work_style.primary_focus", value="product_and_requirement_work",
                                                      display_label="SENSITIVE_SENTINEL")
    completed.resolve_memory_change(candidate.candidate_id, MemoryChangeChoice.UPDATE_LONG_TERM)
    assert completed.current_profile_from_memory().version == 1
    completed.confirm_pending_profile_refinement()
    assert completed.current_profile_from_memory().version == 2
    assert completed.match_for("job_001").model_dump() == before_match
    events = completed.diagnostics_snapshot()["events"]
    operations = {e.operation for e in events}
    assert {"memory_change_deferred", "memory_superseded", "memory_vector_removed", "memory_vector_indexed",
            "profile_refine", "profile_refine_confirm", "role_recall", "memory_context_built", "memory_retrieve"}.issubset(operations)
    assert any(e.counts.get("stale_filtered_count") == 0 for e in events)
    assert any(e.counts.get("context_record_count", e.counts.get("result_count", 0)) > 0 for e in events)
    source_counts = [e for e in events if e.operation == "memory_retrieval_sources"]
    assert source_counts and any(e.counts.get("candidate_count", 0) > 0 for e in source_counts)
    assert any({"lexical_result_count", "semantic_result_count", "hybrid_result_count"}.issubset(e.counts) for e in source_counts)
    assert "SENSITIVE_SENTINEL" not in dump(completed)
    assert completed.diagnostics_snapshot()["summary"].recording_failure_count == 0


def test_action_evidence_review_does_not_upgrade_profile(completed):
    before = completed.confirmed_profile().model_dump()
    completed.mark_action_already_done(completed.match_for("job_001").action_items[0].action_id)
    assert completed.confirmed_profile().model_dump() == before
    events = completed.diagnostics_snapshot()["events"]
    assert any(e.safe_metadata.get("action_state") == "evidence_review_requested" for e in events)


def test_two_sessions_and_close_reset_do_not_share_events():
    first, second = DemoController(), DemoController()
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(lambda c: c.start(), (first, second)))
        assert first.diagnostic_context.run_id != second.diagnostic_context.run_id
        assert all(e.run_id == first.diagnostic_context.run_id for e in first.diagnostics_snapshot()["events"])
        assert all(e.run_id == second.diagnostic_context.run_id for e in second.diagnostics_snapshot()["events"])
        assert first.subject_id not in dump(second) and second.subject_id not in dump(first)
        old = first.diagnostic_context.run_id
        first.close()
        assert not first.diagnostic_collector.timeline(old)
        fresh = DemoController()
        try:
            assert fresh.diagnostic_context.run_id != old and fresh.diagnostics_snapshot()["summary"].event_count == 0
        finally:
            fresh.close()
    finally:
        first.close(); second.close()


def semantic_payload(value):
    if isinstance(value, dict):
        return {k: semantic_payload(v) for k, v in value.items() if k not in {"created_at", "updated_at", "confirmed_at", "latency_ms", "duration_ms"}}
    if isinstance(value, list):
        return [semantic_payload(v) for v in value]
    return value


def test_observability_on_off_same_authoritative_domain_output():
    enabled, disabled = DemoController(), DemoController(diagnostics_enabled=False)
    try:
        for c in (enabled, disabled):
            c.start(); c.confirm_profile()
        assert semantic_payload(enabled.confirmed_profile().model_dump()) == semantic_payload(disabled.confirmed_profile().model_dump())
        assert semantic_payload([r.model_dump() for r in enabled.match_results()]) == semantic_payload([r.model_dump() for r in disabled.match_results()])
        assert not disabled.diagnostics_snapshot()["events"]
    finally:
        enabled.close(); disabled.close()


def test_collector_failure_does_not_corrupt_workflow(monkeypatch):
    c = DemoController()
    try:
        monkeypatch.setattr(c.diagnostic_collector, "record", lambda event: (_ for _ in ()).throw(RuntimeError("SENSITIVE_SENTINEL")))
        c.start(); c.confirm_profile()
        assert c.state["workflow_status"] == "completed" and len(c.match_results()) == 3
        assert c.diagnostics_snapshot()["summary"].recording_failure_count > 0
        assert "SENSITIVE_SENTINEL" not in dump(c)
    finally:
        c.close()


def test_evaluation_correlations_isolated_bounded_and_no_warnings_for_uncertainty():
    runner = EvaluationRunner()
    report = runner.run()
    assert report.summary.model_dump() == {"total": 27, "pass": 20, "fail": 0, "expected_uncertainty": 7, "needs_review": 0}
    ids = [s.diagnostic_run_id for s in report.scenarios]
    assert len(set(ids)) == 27
    for scenario in report.scenarios:
        events = runner.diagnostic_collectors[scenario.diagnostic_run_id].timeline(scenario.diagnostic_run_id)
        assert events and all(e.scenario_id == scenario.scenario_id for e in events)
        assert all(set(check.related_event_ids).issubset({e.event_id for e in events}) for check in scenario.checks)
        if scenario.status == EvaluationStatus.EXPECTED_UNCERTAINTY:
            assert not any(e.safe_metadata.get("warning") == "evaluation_needs_review" for e in events)
    serialized = json.loads(report.model_dump_json())
    assert all(s["diagnostic_run_id"] for s in serialized["scenarios"])
    assert "events" not in serialized and "timeline" not in serialized


def test_synthetic_evaluator_failure_links_to_relevant_safe_event(monkeypatch):
    from evaluation.scenarios.execute import execute_scenario
    def corrupted(scenario_id, path):
        result = execute_scenario(scenario_id, path)
        result["profile_confirmed"] = True
        return result
    monkeypatch.setattr("evaluation.runner.execute_scenario", corrupted)
    runner = EvaluationRunner()
    report = runner.run(scenario_ids=["SD_001"])
    scenario = report.scenarios[0]
    assert scenario.status == EvaluationStatus.FAIL
    finding = next(f for f in scenario.findings if f.check_id == "draft_not_authority")
    assert finding.related_event_ids
    events = runner.diagnostic_collectors[scenario.diagnostic_run_id].timeline(scenario.diagnostic_run_id)
    assert all(any(e.event_id == ref and e.component == C.EVALUATION and e.status == S.FAILED for e in events)
               for ref in finding.related_event_ids)
    payload = json.loads(report.model_dump_json())
    assert payload["scenarios"][0]["findings"][0]["related_event_ids"]
    from evaluation.report import markdown_report
    markdown = markdown_report(report)
    assert scenario.diagnostic_run_id in markdown and finding.related_event_ids[0] in markdown


def test_developer_trace_sections_collapsed_safe_and_reset():
    from tests.test_streamlit_app import _complete_profile, _button
    app = AppTest.from_file(ROOT / "ui/app.py", default_timeout=20).run()
    trace = next(e for e in app.expander if e.label == "开发者执行轨迹（安全）")
    assert trace.proto.expanded is False
    _complete_profile(app)
    labels = "\n".join(str(item.value) for item in app.markdown)
    for section in ("Run Summary", "Workflow Timeline", "Component Activity", "Memory Activity", "Match Diagnostics", "Warnings / Failures"):
        assert section in labels
    c = app.session_state["orange_demo_controller"]
    old_id = c.diagnostic_context.run_id
    old_events = c.diagnostics_snapshot()["events"]
    diagnostics_json = "\n".join(str(item.value) for item in app.json)
    for evidence in c.confirmed_profile().evidence:
        assert evidence.statement not in diagnostics_json
    assert "Raw Safe Events" in [e.label for e in app.expander]
    _button(app, "重新开始 Demo").click().run()
    fresh = app.session_state["orange_demo_controller"]
    assert fresh.diagnostic_context.run_id != old_id and not fresh.diagnostics_snapshot()["events"]
    assert not app.exception


@pytest.mark.parametrize("inactive_status", ["candidate", "archived", "superseded"])
def test_stale_vector_filtered_count_is_observed_without_raw_query(tmp_path, inactive_status):
    from memory.service import build_semantic_memory_service
    from memory.embeddings import FakeEmbeddingProvider
    from memory.models import MemoryType
    from data.models import EvidenceSourceType
    service = build_semantic_memory_service(memory_path=tmp_path / "canonical.sqlite3",
        vector_path=tmp_path / "vectors.sqlite3", embedding_provider=FakeEmbeddingProvider())
    collector, context = DiagnosticEventCollector(), ObservabilityContext(run_id=run_id(), subject_id="subject_synthetic")
    with diagnostic_scope(collector, context):
        record = service.create_confirmed(subject_id="subject_synthetic", memory_type=MemoryType.GOAL,
            content="RAW_QUERY_SENTINEL", source_type=EvidenceSourceType.SYSTEM_FIXTURE, confirmed_by_user=True)
        with service.database.connection() as connection:
            connection.execute("UPDATE memory_records SET status = ? WHERE memory_id = ?", (inactive_status, record.memory_id))
            connection.commit()
        assert not service.retrieve_semantic("subject_synthetic", "RAW_QUERY_SENTINEL")
    events = collector.timeline(context.run_id)
    assert any(e.counts.get("stale_filtered_count", 0) > 0 for e in events)
    assert any(e.safe_metadata.get("warning") == "stale_memory_filtered" for e in events)
    assert collector.recording_failure_count == 0
    assert "RAW_QUERY_SENTINEL" not in json.dumps([safe_event_view(e) for e in events])


def test_cleanup_failure_surfaces_safely_without_undoing_purge(completed, monkeypatch):
    from memory.errors import VectorIndexError
    def fail(subject):
        raise VectorIndexError("RAW_FAILURE_SENTINEL")
    monkeypatch.setattr(completed.memory_service.vector_index, "purge_subject", fail)
    with diagnostic_scope(completed.diagnostic_collector, completed.diagnostic_context):
        result = completed.memory_service.purge_subject(completed.subject_id)
    assert result.vector_cleanup_required and not completed.active_memories()
    events = completed.diagnostics_snapshot()["events"]
    assert any(e.safe_metadata.get("warning") == "vector_cleanup_required" for e in events)
    assert "RAW_FAILURE_SENTINEL" not in dump(completed)


def test_qwen_stub_usage_is_safe_no_transport_or_prompt_recording():
    from types import SimpleNamespace
    from tests.test_qwen_provider import ClientStub, completion, provider, generate
    from providers.demo import offline_response
    stub = ClientStub([completion(offline_response(), usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15))])
    collector, context = DiagnosticEventCollector(), ObservabilityContext(run_id=run_id())
    with diagnostic_scope(collector, context):
        response = generate(provider(stub))
    event = collector.timeline(context.run_id)[-1]
    assert response.provider == "qwen" and len(stub.endpoint.calls) == 1
    assert event.counts == {"provider_call_count": 1, "input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
    assert event.safe_metadata["retry_count"] == 0 and event.safe_metadata["model_id"] == "qwen3.8-flash"
    serialized = json.dumps(safe_event_view(event))
    assert "sanitized" not in serialized and "unit-test-key" not in serialized and "request-safe-001" not in serialized


def test_local_embedding_stub_cache_metadata_and_vectors_excluded():
    from memory.embeddings import LocalEmbeddingProvider
    class Vector:
        def tolist(self):
            return [0.125] * 8
    class Model:
        def passage_embed(self, values, batch_size):
            return [Vector() for _ in values]
    provider = LocalEmbeddingProvider(dimension=8, allow_download=False)
    provider._model = Model()  # offline inference stub; never load a model/cache
    collector, context = DiagnosticEventCollector(), ObservabilityContext(run_id=run_id())
    with diagnostic_scope(collector, context):
        assert len(provider.embed_batch(["RAW_EMBED_SENTINEL"])) == 1
    event = collector.timeline(context.run_id)[-1]
    assert event.counts == {"batch_size": 1, "dimension": 8}
    assert event.safe_metadata["cache_only"] is True
    serialized = json.dumps(safe_event_view(event))
    assert "RAW_EMBED_SENTINEL" not in serialized and "0.125" not in serialized


@pytest.mark.parametrize("unsafe", ["prompt text", "credential", "evt_bad"])
def test_evaluation_event_references_reject_content(unsafe):
    from pydantic import ValidationError
    from evaluation.models import CheckResult
    with pytest.raises(ValidationError):
        CheckResult(check_id="synthetic", kind="required", summary="safe", passed=False, related_event_ids=[unsafe])
