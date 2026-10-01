"""Validated snapshot projections for a developer-only, content-free view."""

from observability.models import DiagnosticComponent as C, DiagnosticEvent, DiagnosticRunSummary, DiagnosticTimelineEntry


def snapshot(collector, run_id):
    events = collector.timeline(run_id)
    return {"summary": collector.summary(run_id),
            "timeline": [DiagnosticTimelineEntry(event_id=e.event_id, component=e.component, operation=e.operation,
                status=e.status, duration_ms=e.duration_ms) for e in events],
            "events": events}


def safe_event_view(event):
    # Revalidation is mandatory at the rendering boundary too.
    e = DiagnosticEvent.model_validate(event.model_dump())
    return {"schema_version": e.schema_version, "event_id": e.event_id, "run_id": e.run_id, "parent_event_id": e.parent_event_id,
            "timestamp": e.timestamp.isoformat(), "started_at": e.started_at.isoformat() if e.started_at else None,
            "sequence": e.sequence, "workflow_id": e.workflow_id, "thread_id": e.thread_id,
            "subject_id": e.subject_id, "scenario_id": e.scenario_id,
            "component": e.component.value, "operation": e.operation, "status": e.status.value,
            "duration_ms": e.duration_ms, "source_event_type": e.source_event_type.value if e.source_event_type else None,
            "counts": dict(e.counts), "safe_metadata": dict(e.safe_metadata), "correlation_ids": dict(e.correlation_ids),
            "error_category": e.error_category}
