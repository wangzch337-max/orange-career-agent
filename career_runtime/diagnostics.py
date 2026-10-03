"""Closed structural diagnostics; never accept input values or exception prose."""

from typing import Literal
from pydantic import Field, field_validator
from career_runtime.models import Contract, Plan, ToolInput, StreamMetrics, TurnStatus

Stage = Literal["context", "intent_classification", "planner_provider_transport", "planner_deserialization",
    "planner_schema_validation", "planner_semantic_validation", "tool_name_validation", "tool_input_validation",
    "tool_permission_validation", "tool_execution", "tool_result_validation", "replan",
    "response_provider_transport", "response_validation", "stream_failure", "response_optional_validation", "persistence", "conversation_validation"]
Kind = Literal["none", "missing_field", "extra_field", "invalid_enum", "invalid_shape", "malformed_json",
    "semantic_contradiction", "unknown_tool", "permission_denied", "security_rejection", "execution_failure", "provider_error"]
PATHS = {"$", "unknown_field", *Plan.model_fields, "arguments", "name"}
for prefix in ("arguments", *(f"tools[{i}].arguments" for i in range(3))):
    PATHS.update(f"{prefix}.{field}" for field in ToolInput.model_fields)
    PATHS.update(f"{prefix}.sections[{i}]" for i in range(3))
for i in range(3):
    PATHS.update((f"tools[{i}]", f"tools[{i}].name", f"tools[{i}].arguments"))
PATHS.update(f"evidence_requirements[{i}]" for i in range(4))


class StructuralIssue(Contract):
    field_path: str
    failure_kind: Kind

    @field_validator("field_path")
    @classmethod
    def closed_path(cls, value):
        if value not in PATHS:
            raise ValueError("Unregistered structural path.")
        return value


class RuntimeDiagnostic(Contract):
    stage: Stage
    status: Literal["succeeded", "failed", "skipped"]
    error_category: Literal["none", "validation_failure", "provider_failure", "security_violation", "tool_failure"]
    schema_model: Literal["none", "Plan", "ToolRequest", "ToolInput", "ToolResult", "ResponseEnvelope"] = "none"
    issues: list[StructuralIssue] = Field(default_factory=list, max_length=16)
    validation_issue_count: int = Field(default=0, ge=0, le=10000)
    missing_field_count: int = Field(default=0, ge=0, le=10000)
    extra_field_count: int = Field(default=0, ge=0, le=10000)
    invalid_enum_count: int = Field(default=0, ge=0, le=10000)
    tool_request_count: int = Field(default=0, ge=0, le=3)
    tool_name_category: Literal["none", "registered_read", "registered_candidate", "unknown"] = "none"
    plan_attempt: int = Field(default=0, ge=0, le=2)
    repair_attempt: int = Field(default=0, ge=0, le=1)
    repair_result: Literal["not_attempted", "success", "failure"] = "not_attempted"
    tool_step_index: int = Field(default=0, ge=0, le=4)
    stream: StreamMetrics | None = None
    previous_turn_status: TurnStatus = TurnStatus.UNKNOWN
    dialogue_act: Literal["new_topic", "normal_followup", "continue_previous", "expand_previous", "clarify_previous", "refer_to_previous_item"] = "normal_followup"


class ProviderAttempt(Contract):
    prompt_name: Literal["orange_planner", "orange_planner_repair", "orange_response"]
    status: Literal["succeeded", "failed"]
    latency_ms: int = Field(ge=0)
    provider_retry_count: int = Field(ge=0, le=1)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class CallAccounting(Contract):
    planner_invocation_count: int = Field(ge=0, le=2)
    repair_invocation_count: int = Field(ge=0, le=2)
    response_invocation_count: int = Field(ge=0, le=1)
    provider_request_count: int | None = Field(default=None, ge=0, le=7)
    provider_retry_count: int | None = Field(default=None, ge=0, le=2)
    tool_attempt_count: int = Field(ge=0, le=4)


class PlanFailure(RuntimeError):
    def __init__(self, diagnostic: RuntimeDiagnostic, *, repairable: bool):
        super().__init__("Structured planning failed.")
        self.diagnostic, self.repairable = diagnostic, repairable


def _path(loc):
    # Validate EVERY component before concatenation; unknown/extra keys may be secrets.
    known = {*Plan.model_fields, *ToolInput.model_fields, "name", "arguments"}
    if any((type(part) is str and part not in known) or (type(part) is not str and (type(part) is not int or part not in range(4))) for part in loc):
        return "unknown_field"
    value = ""
    for part in loc:
        value += f"[{part}]" if type(part) is int else ("." if value else "") + part
    return value if value in PATHS else "$" if not value else "unknown_field"


def structural_failure(exc, *, plan_attempt, repair_attempt):
    # Provider package imports observability: keep error adapters out of schema boot.
    from providers.errors import LLMStructuredOutputError
    if isinstance(exc, LLMStructuredOutputError):
        errors = [{"type": item.error_type or "invalid_shape", "loc": item.loc} for item in exc.diagnostics]
    else:
        errors = exc.errors(include_input=False, include_context=False, include_url=False)
    issues, stage, security = [], "planner_schema_validation", False
    kinds = []
    for error in errors:
        error_type, path = error["type"], _path(error.get("loc", ()))
        kind = {"missing": "missing_field", "extra_forbidden": "extra_field", "enum": "invalid_enum",
                "literal_error": "invalid_enum", "json_invalid": "malformed_json"}.get(error_type, "invalid_shape")
        if error_type.startswith("plan_"):
            kind, stage = "semantic_contradiction", "planner_semantic_validation"
        elif error_type.startswith("tool_"):
            kind, stage = "semantic_contradiction", "tool_input_validation"
            security |= error_type in {"tool_unused_argument", "tool_candidate_argument"}
        if path.endswith(".name") or path == "name":
            stage = "tool_name_validation"
            if kind == "invalid_enum":
                kind, security = "unknown_tool", True
        elif "arguments" in path:
            stage = "tool_input_validation"
            security |= kind == "invalid_enum"
        elif path in {"intent", "relevance"}:
            stage = "intent_classification"
        if kind == "malformed_json" or error_type in {"empty_response", "missing_structured_output"}:
            stage = "planner_deserialization"
        # No repair for extras: an unknown key can be a permission/owner/secret attempt.
        security |= kind == "extra_field" or error_type == "provider_refusal"
        issues.append(StructuralIssue(field_path=path, failure_kind=kind))
        kinds.append(kind)
    diagnostic = RuntimeDiagnostic(stage=stage, status="failed", error_category="security_violation" if security else "validation_failure",
        schema_model="Plan", issues=issues[:16], validation_issue_count=len(issues),
        missing_field_count=kinds.count("missing_field"), extra_field_count=kinds.count("extra_field"),
        invalid_enum_count=kinds.count("invalid_enum")+kinds.count("unknown_tool"), tool_name_category="unknown" if "unknown_tool" in kinds else "none",
        plan_attempt=plan_attempt, repair_attempt=repair_attempt, repair_result="failure" if repair_attempt else "not_attempted")
    return PlanFailure(diagnostic, repairable=not security)
