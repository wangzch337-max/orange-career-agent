"""Closed contracts, fail-closed metadata, scoped spans and compatibility."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from data.models import AgentEvent, AgentName, ToolEvent, GraphEvent, EventType
from memory.models import MemoryEvent
from observability.adapters import adapt_event, record_legacy_event
from observability.collector import DiagnosticEventCollector
from observability.context import current_binding, diagnostic_scope
from observability.diagnostics import safe_event_view
from observability.events import diagnostic_span, emit
from observability.models import DiagnosticEvent, DiagnosticComponent as C, DiagnosticStatus as S, ObservabilityContext, run_id
from observability.redaction import UnsafeDiagnosticMetadata


@pytest.fixture
def context():
    return ObservabilityContext(run_id=run_id(), workflow_id="workflow_synthetic", subject_id="subject_synthetic")


def event(context, **kwargs):
    return DiagnosticEvent(**context.model_dump(), component=C.SYSTEM, operation="diagnostic_rejected", status=S.SKIPPED, **kwargs)


def test_schema_identity_parent_and_strict_envelope(context):
    first, second = event(context), event(context)
    assert first.schema_version == "orange.observability.v1"
    assert first.event_id != second.event_id and first.run_id == second.run_id
    assert first.parent_event_id is None
    with pytest.raises(ValidationError):
        DiagnosticEvent.model_validate({**first.model_dump(), "profile_json": "SENSITIVE"})


@pytest.mark.parametrize("field,value", [("run_id", "private text"), ("event_id", "memory_001"),
    ("operation", "user_private_answer"), ("component", "arbitrary"), ("status", "truth"),
    ("timestamp", datetime(2026, 1, 1)), ("duration_ms", -1), ("duration_ms", float("inf")),
    ("workflow_id", "person@example.invalid"), ("subject_id", "raw private answer")])
def test_invalid_envelope_rejected(context, field, value):
    payload = event(context).model_dump()
    with pytest.raises((ValidationError, UnsafeDiagnosticMetadata)):
        DiagnosticEvent.model_validate({**payload, field: value})


@pytest.mark.parametrize("key", ["prompt", "completion", "content", "profile", "memory_content", "raw_memory",
    "profile_json", "embedding", "api_key", "token", "password", "secret", "raw_input", "raw_output",
    "chain_of_thought", "reasoning", "cot", "reasoning_trace", "hidden_reasoning", "internal_reasoning"])
def test_unsafe_metadata_rejected_and_never_stored(context, key):
    collector = DiagnosticEventCollector()
    with pytest.raises((ValidationError, UnsafeDiagnosticMetadata)):
        collector.record(event(context, safe_metadata={key: "SENSITIVE_SENTINEL"}))
    assert collector.timeline(context.run_id) == []


@pytest.mark.parametrize("key,value", [("provider", "private_provider_text"), ("model_id", "credential_value"),
    ("workflow_status", {"profile": "raw"}), ("memory_types", ["SENSITIVE_SENTINEL"]),
    ("review_required", "true"), ("profile_version", True), ("measured_duration_ms", float("nan"))])
def test_safe_key_does_not_authorize_unsafe_value(context, key, value):
    with pytest.raises((ValidationError, UnsafeDiagnosticMetadata)):
        event(context, safe_metadata={key: value})


def test_safe_primitives_counts_and_small_enum_lists(context):
    item = event(context, counts={"relation_count": 2, "unknown": 1}, safe_metadata={"provider": "fake",
        "profile_version": 2, "review_required": True, "model_id": None, "measured_duration_ms": 1.25,
        "action_types": ["investigate_job_unknown"]})
    assert item.safe_metadata["measured_duration_ms"] == 1.25
    assert item.counts["unknown"] == 1
    for counts in ({"quality_score": 90}, {"result_count": True}, {"result_count": -1}, {"result_count": "3"}):
        with pytest.raises((ValidationError, UnsafeDiagnosticMetadata)):
            event(context, counts=counts)


def test_collector_revalidates_bypassed_model_and_defensive_copies(context):
    collector = DiagnosticEventCollector()
    corrupted = event(context).model_copy(update={"safe_metadata": {"prompt": "SENSITIVE_SENTINEL"}})
    with pytest.raises((ValidationError, UnsafeDiagnosticMetadata)):
        collector.record(corrupted)
    valid = event(context, counts={"result_count": 2})
    collector.record(valid)
    valid.counts["result_count"] = 999
    copied = collector.timeline(context.run_id)[0]
    copied.counts["result_count"] = 888
    assert collector.timeline(context.run_id)[0].counts["result_count"] == 2
    with pytest.raises((ValidationError, UnsafeDiagnosticMetadata)):
        safe_event_view(corrupted)


def test_timeline_collision_order_filters_parent_ownership_and_clear(context):
    collector = DiagnosticEventCollector()
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first, second = event(context, timestamp=timestamp), event(context, timestamp=timestamp)
    collector.record(first); collector.record(second)
    assert [item.event_id for item in collector.timeline(context.run_id)] == [first.event_id, second.event_id]
    other = ObservabilityContext(run_id=run_id())
    collector.record(event(other))
    assert len(collector.timeline(other.run_id)) == 1
    assert len(collector.timeline(context.run_id, C.SYSTEM)) == 2
    assert collector.timeline(context.run_id, C.MATCH_INSIGHT) == []
    with pytest.raises(ValueError):
        collector.record(DiagnosticEvent(**{**other.model_dump(), "parent_event_id": first.event_id},
            component=C.SYSTEM, operation="diagnostic_rejected", status=S.SKIPPED))
    collector.clear_run(context.run_id)
    assert not collector.timeline(context.run_id) and collector.timeline(other.run_id)
    collector.reset()
    assert not collector.timeline(other.run_id)


def test_span_monotonic_duration_hierarchy_and_scope_reset(context, monkeypatch):
    clock = iter([10.0, 11.0, 11.003, 11.005])
    monkeypatch.setattr("observability.events.perf_counter", lambda: next(clock))
    collector = DiagnosticEventCollector()
    with diagnostic_scope(collector, context):
        with diagnostic_span(C.WORKFLOW, "workflow_start"):
            with diagnostic_span(C.PROVIDER, "provider_call") as payload:
                payload["counts"] = {"provider_call_count": 1}
    assert current_binding() is None
    events = collector.timeline(context.run_id)
    provider = next(e for e in events if e.component == C.PROVIDER and e.status == S.SUCCEEDED)
    assert provider.duration_ms == pytest.approx(3.0)
    assert provider.parent_event_id in {e.event_id for e in events}
    summary = collector.summary(context.run_id)
    assert summary.event_count == 4 and summary.provider_call_count == 1 and summary.duration_ms == pytest.approx(1005)


def test_original_exception_reraised_no_message_or_private_class_name(context):
    collector = DiagnosticEventCollector()
    with pytest.raises(RuntimeError, match="SENSITIVE_SENTINEL"):
        with diagnostic_scope(collector, context), diagnostic_span(C.MEMORY, "memory_retrieve"):
            raise RuntimeError("SENSITIVE_SENTINEL")
    events = collector.timeline(context.run_id)
    failure = events[-1]
    assert failure.status == S.FAILED and failure.safe_metadata["exception_type"] == "RuntimeError"
    assert "SENSITIVE_SENTINEL" not in str([safe_event_view(e) for e in events])
    assert current_binding() is None


def test_recording_failure_and_cap_do_not_swallow_or_change_product_result(context, monkeypatch):
    collector = DiagnosticEventCollector(max_events=1)
    with diagnostic_scope(collector, context), diagnostic_span(C.SYSTEM, "diagnostic_rejected"):
        result = {"authoritative": 42}
    assert result == {"authoritative": 42} and collector.recording_failure_count == 1
    monkeypatch.setattr(collector, "record", lambda event: (_ for _ in ()).throw(RuntimeError("SENSITIVE_SENTINEL")))
    with diagnostic_scope(collector, context), diagnostic_span(C.SYSTEM, "diagnostic_rejected"):
        assert result["authoritative"] == 42
    assert collector.recording_failure_count >= 3


@pytest.mark.parametrize("kind", ["agent", "tool", "graph", "memory", "context"])
def test_legacy_adapters_preserve_type_not_summary_or_payload(context, kind):
    base = dict(event_id="memory_event_synthetic", summary="SENSITIVE_SENTINEL", event_type=EventType.MEMORY_RETRIEVED,
                component="MemoryService", safe_metadata={"result_count": 2})
    if kind == "agent":
        legacy = AgentEvent(**{**base, "event_id": "agent_event_001", "component": AgentName.SELF_DISCOVERY.value,
            "event_type": EventType.AGENT_COMPLETED}, agent_name=AgentName.SELF_DISCOVERY)
    elif kind == "tool":
        legacy = ToolEvent(**{**base, "event_id": "tool_event_001", "component": "MockJobDataProvider", "event_type": EventType.TOOL_COMPLETED}, tool_name="MockJobDataProvider")
    elif kind == "graph":
        legacy = GraphEvent(**{**base, "component": "LangGraphOrchestrator", "event_type": EventType.GRAPH_INTERRUPTED,
            "safe_metadata": {"workflow_status": "waiting_for_human"}}, workflow_id="workflow_synthetic")
    else:
        legacy = MemoryEvent(**{**base, "component": "MemoryContextCoordinator" if kind == "context" else "MemoryService",
            "event_type": EventType.MEMORY_CONTEXT_BUILT if kind == "context" else EventType.MEMORY_RETRIEVED}, subject_id="subject_synthetic")
    adapted = adapt_event(legacy, context)
    assert adapted.source_event_type == legacy.event_type and adapted.event_id != legacy.event_id
    assert "SENSITIVE_SENTINEL" not in adapted.model_dump_json()
    if kind == "graph":
        assert adapted.status == S.INTERRUPTED
    collector = DiagnosticEventCollector()
    with diagnostic_scope(collector, context):
        record_legacy_event(legacy); record_legacy_event(legacy)
    assert len(collector.timeline(context.run_id)) == 1


def test_adapter_unsafe_legacy_metadata_removed_with_safe_validation_warning(context):
    legacy = MemoryEvent(event_id="memory_event_synthetic", event_type=EventType.MEMORY_RETRIEVED,
        component="MemoryService", summary="SENSITIVE_SENTINEL", subject_id="subject_synthetic",
        safe_metadata={"prompt": "SENSITIVE_SENTINEL", "profile_json": {"raw": "SENSITIVE_SENTINEL"}})
    adapted = adapt_event(legacy, context)
    assert adapted.counts["rejected_field_count"] == 2
    assert adapted.safe_metadata["warning"] == "unsafe_metadata_rejected"
    assert "SENSITIVE_SENTINEL" not in adapted.model_dump_json()


def test_instrumentation_source_inspection_failure_does_not_change_result(context):
    from observability.instrumentation import observe
    class Product:
        @property
        def events(self):
            raise RuntimeError("SENSITIVE_SENTINEL")

        @observe(C.SYSTEM, "diagnostic_rejected")
        def execute(self):
            return 42
    collector = DiagnosticEventCollector()
    with diagnostic_scope(collector, context):
        assert Product().execute() == 42
    assert collector.recording_failure_count == 1
    assert "SENSITIVE_SENTINEL" not in str(collector.timeline(context.run_id))
