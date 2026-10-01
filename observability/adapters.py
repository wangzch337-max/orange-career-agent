"""Explicit projections of existing events; summary/content are never copied."""

from data.models import EventType, AgentName
from observability.context import current_binding
from observability.events import emit
from observability.models import DiagnosticEvent, DiagnosticComponent as C, DiagnosticStatus as S
from observability.redaction import validate_metadata, validate_counts, safe_id


COMPONENTS = {
    AgentName.SELF_DISCOVERY.value: C.SELF_DISCOVERY, AgentName.JOB_INTELLIGENCE.value: C.JOB_INTELLIGENCE,
    AgentName.MATCH_INSIGHT.value: C.MATCH_INSIGHT, AgentName.ORCHESTRATOR.value: C.WORKFLOW,
    "LangGraphOrchestrator": C.WORKFLOW, "MemoryService": C.MEMORY,
    "SemanticMemoryRetriever": C.MEMORY_RETRIEVAL, "HybridMemoryRetriever": C.MEMORY_RETRIEVAL,
    "MemoryContextCoordinator": C.MEMORY_CONTEXT, "MemoryChangeDetector": C.MEMORY,
    "MemoryChangeService": C.MEMORY, "RoleMemoryContextService": C.ROLE_EXPLORATION,
    "MemoryVectorIndex": C.VECTOR_INDEX, "MockCourseDataProvider": C.SYSTEM,
    "MockJobDataProvider": C.SYSTEM, "DeterministicReportBuilder": C.REPORT,
}
STARTED = {EventType.AGENT_STARTED, EventType.TOOL_CALLED, EventType.GRAPH_RUN_STARTED,
           EventType.GRAPH_NODE_STARTED, EventType.JOB_INTELLIGENCE_STARTED, EventType.MATCH_INSIGHT_STARTED,
           EventType.MEMORY_CONTEXT_REQUESTED}
FAILED = {EventType.VALIDATION_FAILED, EventType.WORKFLOW_FAILED, EventType.GRAPH_FAILED,
          EventType.PROFILE_CONFIRMATION_BLOCKED_MATCH}
WAITING = {EventType.PROFILE_CONFIRMATION_REQUIRED}
INTERRUPTED = {EventType.GRAPH_INTERRUPTED}


def adapt_event(event, context):
    raw = event.model_dump() if hasattr(event, "model_dump") else event
    event_type = EventType(raw["event_type"])
    component = COMPONENTS.get(raw.get("component"), C.SYSTEM)
    status = S.STARTED if event_type in STARTED else S.FAILED if event_type in FAILED else S.WAITING if event_type in WAITING else S.INTERRUPTED if event_type in INTERRUPTED else S.SUCCEEDED
    metadata, counts, ids = {}, {}, {}
    forbidden_keys = {"prompt", "completion", "content", "profile", "raw_memory", "memory_content", "profile_json",
        "embedding", "api_key", "token", "password", "secret", "raw_input", "raw_output", "chain_of_thought",
        "reasoning", "cot", "reasoning_trace", "hidden_reasoning", "internal_reasoning"}
    rejected = sum(key.casefold() in forbidden_keys for key in raw.get("safe_metadata", {}))
    if rejected:
        counts["rejected_field_count"] = rejected
        metadata["warning"] = "unsafe_metadata_rejected"
    for key, value in raw.get("safe_metadata", {}).items():
        target = "retrieval_mode" if key == "mode" else "memory_status" if key == "status" and value in {"candidate", "confirmed", "superseded", "archived"} else key
        try:
            counts.update(validate_counts({target: value}))
            continue
        except ValueError:
            pass
        try:
            metadata.update(validate_metadata({target: value}))
        except ValueError:
            pass  # explicitly projected, never raw metadata passthrough
        if key in {"relation_counts", "signal_counts"} and isinstance(value, dict):
            for child_key, count in value.items():
                try:
                    counts.update(validate_counts({child_key: count}))
                except ValueError:
                    pass
    for key in ("workflow_id", "subject_id", "memory_id", "event_id"):
        value = raw.get(key)
        if value:
            try:
                ids["source_event_id" if key == "event_id" else key] = safe_id(value)
            except ValueError:
                pass
    if raw.get("node_name"):
        try:
            metadata.update(validate_metadata({"node": raw["node_name"]}))
        except ValueError:
            pass
    if raw.get("profile_version") is not None:
        metadata["profile_version"] = raw["profile_version"]
    if event_type == EventType.MEMORY_VECTOR_STALE_FILTERED:
        metadata["warning"] = "stale_memory_filtered"
    if metadata.get("cleanup_required"):
        metadata["warning"] = "vector_cleanup_required"
    return DiagnosticEvent(**context.model_dump(), component=component, operation=event_type.value, status=status,
        timestamp=raw["timestamp"], duration_ms=raw.get("duration_ms"), source_event_type=event_type,
        counts=counts, safe_metadata=metadata, correlation_ids=ids,
        error_category="validation_failure" if status == S.FAILED else None)


def record_legacy_event(event):
    binding = current_binding()
    if binding is None:
        return
    try:
        source_id = event.event_id if hasattr(event, "event_id") else event["event_id"]
        binding.collector.record_source(binding.context.run_id, source_id, lambda: adapt_event(event, binding.context))
    except Exception:
        binding.collector.recording_failure_count += 1


# Named compatibility surfaces share the same explicit projection.
AgentEventAdapter = adapt_event
ToolEventAdapter = adapt_event
GraphEventAdapter = adapt_event
MemoryEventAdapter = adapt_event


def event_sources(instance):
    """Known ephemeral producer lists only, never domain state introspection."""
    sources, visited = [], set()
    def visit(obj, depth):
        if obj is None or id(obj) in visited or depth > 3:
            return
        visited.add(id(obj))
        events = getattr(obj, "events", None)
        if isinstance(events, list):
            sources.append(events)
        for attr in ("memory_service", "coordinator", "semantic_retriever", "hybrid_retriever", "vector_index"):
            visit(getattr(obj, attr, None), depth + 1)
    visit(instance, 0)
    return sources
