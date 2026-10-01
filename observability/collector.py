"""Session-local bounded collector. No database, exporter or singleton."""

from collections import Counter
from threading import RLock

from observability.models import DiagnosticEvent, DiagnosticStatus as S, DiagnosticComponent as C, DiagnosticRunSummary


class DiagnosticEventCollector:
    def __init__(self, *, max_events=4000):
        self.max_events = max_events
        self._events = []
        self._sources = set()
        self._lock = RLock()
        self.recording_failure_count = 0

    def record(self, event: DiagnosticEvent):
        # Revalidate and copy even if someone bypassed model validators/model_copy.
        validated = DiagnosticEvent.model_validate(event.model_dump())
        with self._lock:
            if len(self._events) >= self.max_events:
                self.recording_failure_count += 1
                return None
            if any(item.event_id == validated.event_id for item in self._events):
                return validated
            if validated.parent_event_id is not None and not any(
                item.event_id == validated.parent_event_id and item.run_id == validated.run_id for item in self._events
            ):
                raise ValueError("Parent must exist in the same diagnostic run")
            validated = DiagnosticEvent.model_validate({**validated.model_dump(), "sequence": len(self._events) + 1})
            self._events.append(validated)
            return validated.model_copy(deep=True)

    def record_source(self, run_id, source_id, make_event):
        with self._lock:
            key = (run_id, source_id)
            if key in self._sources:
                return None
            event = self.record(make_event())
            if event is not None:
                self._sources.add(key)
            return event

    def timeline(self, run_id, component=None):
        with self._lock:
            return [item.model_copy(deep=True) for item in sorted(self._events, key=lambda e: (e.timestamp, e.sequence, e.event_id))
                    if item.run_id == run_id and (component is None or item.component == component)]

    def clear_run(self, run_id):
        with self._lock:
            self._events = [item for item in self._events if item.run_id != run_id]
            self._sources = {item for item in self._sources if item[0] != run_id}

    def reset(self):
        with self._lock:
            self._events.clear()
            self._sources.clear()
            self.recording_failure_count = 0

    def summary(self, run_id):
        events = self.timeline(run_id)
        workflow = [item.safe_metadata["workflow_status"] for item in events if "workflow_status" in item.safe_metadata]
        workflow_status = workflow[-1] if workflow else None
        failures = sum(item.status == S.FAILED for item in events)
        status = S.FAILED if failures else S.WAITING if workflow_status == "waiting_for_human" else S.SUCCEEDED if events else S.SKIPPED
        # Only measured root-operation durations; do not double-count child spans or user wait time.
        durations = [item.duration_ms for item in events if item.duration_ms is not None and
                     item.operation in {"workflow_start", "workflow_resume", "evaluation_scenario_run"}]
        return DiagnosticRunSummary(run_id=run_id, status=status, started_at=events[0].timestamp if events else None,
            duration_ms=sum(durations) if durations else None, event_count=len(events),
            component_counts=dict(Counter(item.component for item in events)), failure_count=failures,
            warning_count=sum("warning" in item.safe_metadata for item in events), workflow_status=workflow_status,
            provider_call_count=sum(item.component == C.PROVIDER and item.operation == "provider_call" and item.status == S.STARTED for item in events),
            memory_retrieval_count=sum(item.operation == "memory_retrieve" and item.status == S.STARTED for item in events),
            recording_failure_count=self.recording_failure_count)
