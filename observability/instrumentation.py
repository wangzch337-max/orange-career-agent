"""Small observational decorators; enabled only inside a bounded explicit scope."""

from functools import wraps

from observability.adapters import event_sources, record_legacy_event
from observability.context import current_binding, diagnostic_scope
from observability.events import diagnostic_span, emit
from observability.models import DiagnosticComponent as C, DiagnosticStatus as S
from observability.redaction import validate_metadata


def result_statistics(operation, result, instance, args, kwargs):
    counts, metadata = {}, {}
    value = result[0] if isinstance(result, tuple) and result else result
    if operation == "self_discovery_run":
        profile = value.user_profile
        counts = {"source_evidence_count": len(profile.evidence), "profile_signal_count": sum(len(getattr(profile, name)) for name in
            ("skills", "interests", "values", "goals", "strengths", "development_areas", "career_preferences")),
            "uncertainty_count": len(value.uncertainties), "provider_call_count": 1}
        metadata = {"profile_version": profile.version, "validation_result": "passed"}
    elif operation == "job_intelligence_run":
        counts = {"job_count": 1, "source_evidence_count": len(value.evidence),
            "required_skill_count": len(value.required_capabilities), "preferred_skill_count": len(value.preferred_capabilities),
            "uncertainty_count": len(value.uncertainties), "provider_call_count": 1}
        metadata = {"validation_result": "passed"}
    elif operation == "match_run":
        counts = {"relation_count": len(value.insights()), "action_count": len(value.action_items), "provider_call_count": 1}
        for insight in value.insights():
            name = insight.relation_type.value
            counts[name] = counts.get(name, 0) + 1
        metadata = {"validation_result": "passed", "action_types": sorted({item.action_type.value for item in value.action_items})}
    elif operation == "provider_call":
        counts = {"provider_call_count": 1}
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            count = getattr(value.usage, key)
            if count is not None:
                counts[key] = count
        metadata = {"provider": value.provider, "validation_result": "passed", "retry_count": value.retry_count}
        if value.model in {"fake-model", "fake-self-discovery-v2", "fake-job-intelligence-v1", "fake-match-insight-v1", "fake-match-insight-v5", "qwen3.8-flash"}:
            metadata["model_id"] = value.model
    elif operation == "embedding_batch":
        counts = {"batch_size": len(result), "dimension": instance.dimension}
        metadata = {"provider": instance.provider_name, "cache_only": not getattr(instance, "allow_download", False)}
        from observability.redaction import STRING_VALUES
        if instance.model_id in STRING_VALUES["model_id"]:
            metadata["model_id"] = instance.model_id
    elif operation in {"memory_retrieve", "memory_context_build"}:
        counts = {"result_count": len(result.items) if hasattr(result, "items") else len(result)}
        if hasattr(result, "items"):
            counts["context_record_count"] = len(result.items)
        if hasattr(instance, "last_mode"):
            metadata["retrieval_mode"] = instance.last_mode
    elif operation == "memory_change_detect":
        counts = {"change_candidate_count": int(result is not None)}
    elif operation == "memory_change_resolve":
        if not isinstance(result, tuple):
            return {"counts": {}, "safe_metadata": {}}  # controller delegates to the measured command
        candidate = value
        choice = args[2] if len(args) > 2 else kwargs.get("choice")
        if choice is not None:
            metadata["change_choice"] = choice.value
        # Record a bounded decision category, not the current input's value.
        counts = {"change_candidate_count": 1, "record_count": int(result[1] is not None)}
    elif operation == "profile_refine":
        counts = {"memory_context_count": len(value.memory_refs)}
        metadata = {"draft_profile_version": value.draft_profile.version, "review_required": value.requires_profile_review,
                    "current_input_is_newest": value.current_input_is_newest}
    elif operation == "profile_refine_confirm":
        metadata = {"confirmed_profile_version": value.version}
    elif operation == "role_recall":
        counts = {"memory_context_count": len(result[0].items), "statement_count": len(result[1])}
    elif operation == "action_review":
        counts = {"action_count": 1}
        metadata = {"action_state": "evidence_review_requested"}
    elif operation == "action_status":
        state = args[2] if len(args) > 2 else kwargs.get("status")
        states = {"未开始": "not_started", "进行中": "in_progress", "已完成": "completed", "暂时跳过": "skipped"}
        counts = {"action_count": 1}
        if state in states:
            metadata = {"action_state": states[state]}
    return {"counts": counts, "safe_metadata": metadata}


def observe(component, operation):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            if current_binding() is None:
                return function(*args, **kwargs)
            try:
                sources = event_sources(args[0]) if args else []
                offsets = [(source, len(source)) for source in sources]
                sync = getattr(args[0], "vector_sync_diagnostics", []) if args else []
                sync_offset = len(sync)
            except Exception:
                current_binding().collector.recording_failure_count += 1
                offsets, sync, sync_offset = [], [], 0
            with diagnostic_span(component, operation) as payload:
                try:
                    result = function(*args, **kwargs)
                finally:
                    for source, offset in offsets:
                        for event in source[offset:]:
                            record_legacy_event(event)
                    for diagnostic in sync[sync_offset:]:
                        if diagnostic.cleanup_required:
                            emit(C.VECTOR_INDEX, "vector_sync", S.FAILED, error_category="diagnostic_failure",
                                 safe_metadata={"cleanup_required": True, "warning": "vector_cleanup_required"})
                try:
                    payload.update(result_statistics(operation, result, args[0] if args else None, args, kwargs))
                except Exception:
                    current_binding().collector.recording_failure_count += 1
                return result
        return wrapped
    return decorate


def session_operation(component, operation):
    """Controller-owned scope; rendering does not create or adapt events."""
    def decorate(function):
        observed = observe(component, operation)(function)
        @wraps(function)
        def wrapped(self, *args, **kwargs):
            if operation == "workflow_start" and self.state is not None:
                return function(self, *args, **kwargs)
            # Evaluation owns a separate outer scope; never mix its events with the UI collector.
            if current_binding() is not None:
                return observed(self, *args, **kwargs)
            if not self.diagnostics_enabled:
                return function(self, *args, **kwargs)
            with diagnostic_scope(self.diagnostic_collector, self.diagnostic_context):
                return observed(self, *args, **kwargs)
        return wrapped
    return decorate
