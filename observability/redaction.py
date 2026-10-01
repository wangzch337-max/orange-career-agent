"""Fail-closed allowlists; a safe key does not authorize an arbitrary string."""

import math
import re


class UnsafeDiagnosticMetadata(ValueError):
    def __init__(self):
        super().__init__("Diagnostic metadata rejected")


STRING_VALUES = {
    "provider": {"fake", "qwen", "fake_local", "local", "fastembed_local"},
    "model_id": {"stable-sha256-projection-v1", "qwen3.8-flash", "fake-model", "fake-self-discovery-v2",
                 "fake-job-intelligence-v1", "fake-match-insight-v1", "fake-match-insight-v5",
                 "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"},
    "workflow_status": {"running", "waiting_for_human", "completed", "failed"},
    "checkpoint_mode": {"memory", "sqlite"},
    "node": {"self_discovery", "profile_review_gate", "job_intelligence", "match_insight", "report", "END"},
    "retrieval_mode": {"hybrid", "semantic", "lexical", "lexical_only_fallback"},
    "use_case": {"profile_refinement", "role_exploration"},
    "memory_type": {"profile_signal", "career_preference", "goal", "user_feedback", "project_evidence", "course_evidence", "career_insight"},
    "memory_status": {"candidate", "confirmed", "superseded", "archived"},
    "change_choice": {"update_long_term", "keep_both", "defer", "uncertain"},
    "change_status": {"pending", "confirmed", "deferred", "uncertain"},
    "validation_result": {"passed", "failed"},
    "warning": {"stale_memory_filtered", "vector_cleanup_required", "unexpected_provider_retry",
                "evaluation_needs_review", "validation_failure", "diagnostic_recording_failed", "unsafe_metadata_rejected"},
    "exception_type": {"ValueError", "TypeError", "KeyError", "RuntimeError", "PermissionError", "ValidationError",
                       "LLMStructuredOutputError", "LLMProviderError", "InvalidMemoryTransitionError", "UnexpectedError",
                       "DemoWorkflowError", "DemoValidationError", "EvaluationBoundaryError"},
    "schema_name": {"SelfDiscoveryExtraction", "JobIntelligenceExtraction", "MatchInsightExtraction", "MatchInsightResponse"},
    "action_state": {"not_started", "in_progress", "completed", "skipped", "evidence_review_requested"},
}
ACTION_TYPES = {"verify_existing_capability", "build_portfolio_evidence", "deepen_capability", "gain_practical_experience",
                "clarify_preference", "investigate_job_unknown"}
RELATION_TYPES = {"strong_alignment", "partial_alignment", "evidence_missing", "confirmed_gap", "experience_depth_gap",
                  "preference_alignment", "potential_friction", "unknown"}
COUNT_KEYS = {
    "count", "result_count", "record_count", "provider_call_count", "source_evidence_count", "profile_signal_count",
    "uncertainty_count", "required_skill_count", "preferred_skill_count", "relation_count", "action_count",
    "candidate_count", "semantic_result_count", "lexical_result_count", "hybrid_result_count", "stale_filtered_count",
    "context_record_count", "memory_context_count", "change_candidate_count", "statement_count", "batch_size",
    "removed_count", "rejected_field_count", "evidence_count", "question_count", "dimension", "memory_count",
    "profile_count", "job_count", "retrieval_count", "self_discovery_call_count",
    "input_tokens", "output_tokens", "total_tokens", *RELATION_TYPES,
}
BOOL_KEYS = {"review_required", "cache_only", "cleanup_required", "current_input_is_newest"}
INT_KEYS = {"profile_version", "draft_profile_version", "confirmed_profile_version", "retry_count"}
ID_KEYS = {"workflow_id", "thread_id", "subject_id", "scenario_id", "memory_id", "job_id", "action_id", "source_event_id"}


def safe_id(value: str) -> str:
    if not isinstance(value, str) or len(value) > 150 or not re.fullmatch(
        r"(?:orange|workflow|subject|memory|job|action|agent_event|tool_event|SD|JI|MI|MEM|CONV|ACT|E2E)_[A-Za-z0-9_]+", value
    ):
        raise UnsafeDiagnosticMetadata()
    return value


def validate_metadata(value):
    if not isinstance(value, dict) or len(value) > 24:
        raise UnsafeDiagnosticMetadata()
    result = {}
    for key, item in value.items():
        if item is None and key in STRING_VALUES | {name: set() for name in BOOL_KEYS | INT_KEYS}:
            result[key] = None
            continue
        if key == "measured_duration_ms":
            if type(item) not in (int, float) or not math.isfinite(item) or item < 0:
                raise UnsafeDiagnosticMetadata()
        elif key in STRING_VALUES:
            if not isinstance(item, str) or item not in STRING_VALUES[key]:
                raise UnsafeDiagnosticMetadata()
        elif key in INT_KEYS:
            if type(item) is not int or item < 0:
                raise UnsafeDiagnosticMetadata()
        elif key in BOOL_KEYS:
            if type(item) is not bool:
                raise UnsafeDiagnosticMetadata()
        elif key in {"memory_types", "action_types", "relation_types"}:
            allowed = STRING_VALUES["memory_type"] if key == "memory_types" else ACTION_TYPES if key == "action_types" else RELATION_TYPES
            if not isinstance(item, list) or len(item) > 12 or any(not isinstance(v, str) or v not in allowed for v in item):
                raise UnsafeDiagnosticMetadata()
        else:
            raise UnsafeDiagnosticMetadata()
        result[key] = item
    return result


def validate_counts(value):
    if not isinstance(value, dict) or len(value) > 32 or any(
        key not in COUNT_KEYS or type(item) is not int or item < 0 for key, item in value.items()
    ):
        raise UnsafeDiagnosticMetadata()
    return dict(value)


def safe_exception_name(exc):
    name = type(exc).__name__
    return name if name in STRING_VALUES["exception_type"] else "UnexpectedError"
