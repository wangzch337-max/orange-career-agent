"""Measured coarse spans; diagnostics never swallow original product errors."""

from contextlib import contextmanager
from datetime import datetime, timezone
from time import perf_counter

from observability.context import current_binding, diagnostic_scope
from observability.models import DiagnosticEvent, DiagnosticComponent as C, DiagnosticStatus as S, ObservabilityContext
from observability.redaction import safe_exception_name


def emit(component, operation, status, **kwargs):
    binding = current_binding()
    if binding is None:
        return None
    try:
        event = DiagnosticEvent(**binding.context.model_dump(), component=component, operation=operation, status=status, **kwargs)
        return binding.collector.record(event)
    except Exception:
        # Never copy the failed payload or its exception message. Preserve product execution.
        binding.collector.recording_failure_count += 1
        return None


@contextmanager
def diagnostic_span(component, operation):
    binding = current_binding()
    if binding is None:
        yield {}
        return
    started_at, started = datetime.now(timezone.utc), perf_counter()
    start = emit(component, operation, S.STARTED, started_at=started_at)
    parent = start.event_id if start is not None else binding.context.parent_event_id
    context = ObservabilityContext(**{**binding.context.model_dump(), "parent_event_id": parent})
    payload = {}
    with diagnostic_scope(binding.collector, context):
        try:
            yield payload
        except BaseException as exc:
            name = safe_exception_name(exc)
            category = "validation_failure" if name in {"ValidationError", "ValueError", "TypeError", "KeyError", "PermissionError", "LLMStructuredOutputError"} else "provider_failure" if name == "LLMProviderError" else "unexpected_failure"
            emit(component, operation, S.FAILED, started_at=started_at,
                duration_ms=max(0, (perf_counter() - started) * 1000), error_category=category,
                safe_metadata={"exception_type": name})
            raise
        else:
            emit(component, operation, S.SUCCEEDED, started_at=started_at,
                 duration_ms=max(0, (perf_counter() - started) * 1000), **payload)
