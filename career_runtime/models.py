"""Closed runtime contracts. No scratchpad, reasoning or arbitrary tool arguments."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError
from career_runtime.response_budget import HARD_VISIBLE_CHARACTERS, MAX_STREAM_CHUNKS


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Relevance(str, Enum):
    DIRECT_CAREER = "DIRECT_CAREER"
    CAREER_ADJACENT = "CAREER_ADJACENT"
    LEARNING_OR_TECHNICAL = "LEARNING_OR_TECHNICAL"
    GENERAL_QA = "GENERAL_QA"
    PROFILE_OR_MEMORY = "PROFILE_OR_MEMORY"
    ROLE_EXPLORATION = "ROLE_EXPLORATION"
    META_OR_CLARIFICATION = "META_OR_CLARIFICATION"


class ToolName(str, Enum):
    PROFILE = "current_profile"
    MEMORY = "relevant_memory"
    GOALS = "goals_preferences"
    EVIDENCE = "course_project_evidence"
    ROLE = "known_role"
    MATCH = "existing_match"
    PROFILE_DRAFT = "profile_draft"
    MEMORY_CANDIDATE = "memory_candidate"


class ToolInput(Contract):
    sections: list[Literal["skills", "interests", "values", "goals", "strengths", "development_areas", "career_preferences"]] = Field(max_length=3)
    role_id: Literal["", "job_001", "job_007", "job_013"]
    dimension: Literal["", "career_direction_priority", "work_style_primary_focus"]
    value: Literal["", "ai_application", "ai_product", "data_analysis", "hands_on", "product_and_requirements"]
    # An exact quotation of CURRENT user input, not a model-generated biography.
    user_quote: str = Field(max_length=500)


class ToolRequest(Contract):
    name: ToolName
    arguments: ToolInput

    @model_validator(mode="before")
    @classmethod
    def unused_arguments(cls, data):
        # Only omitted, semantically UNUSED fields acquire canonical empty values.
        # Required arguments, explicit null, unknown names and alternate shapes fail.
        if isinstance(data, dict) and isinstance(data.get("name"), str) and data["name"] in TOOL_ARGUMENTS and isinstance(data.get("arguments"), dict):
            unused = set(ToolInput.model_fields) - set(TOOL_ARGUMENTS[data["name"]])
            arguments = dict(data["arguments"])
            for key in unused:
                arguments.setdefault(key, [] if key == "sections" else "")
            return {**data, "arguments": arguments}
        return data

    @model_validator(mode="after")
    def arguments_consistent(self):
        used = TOOL_ARGUMENTS[self.name.value]
        for key in set(ToolInput.model_fields) - set(used):
            if getattr(self.arguments, key):
                raise PydanticCustomError("tool_unused_argument", "Unused arguments must be empty.")
        if self.name == ToolName.PROFILE and (not self.arguments.sections or len(set(self.arguments.sections)) != len(self.arguments.sections)):
            raise PydanticCustomError("tool_required_argument", "Select distinct profile sections.")
        if self.name in {ToolName.ROLE, ToolName.MATCH} and not self.arguments.role_id:
            raise PydanticCustomError("tool_required_argument", "A registered role is required.")
        if self.name in {ToolName.PROFILE_DRAFT, ToolName.MEMORY_CANDIDATE}:
            if not self.arguments.user_quote or self.arguments.value not in CANDIDATE_VALUES.get(self.arguments.dimension, ()):
                raise PydanticCustomError("tool_candidate_argument", "Candidate arguments must use one supported dimension.")
        return self


# One source for prompt/catalog, validation and public synthetic test builders.
TOOL_ARGUMENTS = {
    "current_profile": ("sections",), "relevant_memory": ("role_id",),
    "goals_preferences": (), "course_project_evidence": (),
    "known_role": ("role_id",), "existing_match": ("role_id",),
    "profile_draft": ("dimension", "value", "user_quote"),
    "memory_candidate": ("dimension", "value", "user_quote"),
}
CANDIDATE_VALUES = {
    "career_direction_priority": ("ai_application", "ai_product", "data_analysis"),
    "work_style_primary_focus": ("hands_on", "product_and_requirements"),
}
PROFILE_TOOLS = {ToolName.PROFILE, ToolName.GOALS, ToolName.EVIDENCE, ToolName.PROFILE_DRAFT, ToolName.MATCH}
MEMORY_TOOLS = {ToolName.MEMORY, ToolName.MEMORY_CANDIDATE}
ROLE_TOOLS = {ToolName.ROLE, ToolName.MATCH}


class Plan(Contract):
    intent: Literal["answer", "explore", "recall", "goal_change", "refine", "clarify"]
    relevance: Relevance
    response_mode: Literal["direct", "evidence_based", "clarification"]
    needs_profile: bool
    needs_memory: bool
    needs_role: bool
    needs_tools: bool
    tools: list[ToolRequest] = Field(max_length=3)
    needs_clarification: bool
    clarification_reason: Literal["none", "missing_goal", "ambiguous_request", "missing_source", "authority_conflict"]
    evidence_requirements: list[Literal["profile", "memory", "role", "course_project"]] = Field(max_length=4)
    suggestion_policy: Literal["none", "optional_relevant"]
    continue_after_tools: bool
    dialogue_act: Literal["new_topic", "normal_followup", "continue_previous", "expand_previous", "clarify_previous", "refer_to_previous_item"] = "normal_followup"
    referenced_message_ids: list[str] = Field(default_factory=list, max_length=2)

    @model_validator(mode="after")
    def consistent(self):
        if self.needs_tools != bool(self.tools):
            raise PydanticCustomError("plan_tool_state", "Tool state must match requests.")
        if self.needs_clarification != (self.clarification_reason != "none"):
            raise PydanticCustomError("plan_clarification_state", "Clarification requires a bounded reason.")
        if (self.response_mode == "clarification") != self.needs_clarification:
            raise PydanticCustomError("plan_response_mode", "Response mode must match clarification state.")
        names = {request.name for request in self.tools}
        if (self.needs_profile, self.needs_memory, self.needs_role) != (
            bool(names & PROFILE_TOOLS), bool(names & MEMORY_TOOLS), bool(names & ROLE_TOOLS)):
            raise PydanticCustomError("plan_source_flags", "Source flags must match requested tools.")
        if len({request.model_dump_json() for request in self.tools}) != len(self.tools):
            raise PydanticCustomError("plan_duplicate_tool", "A planning point cannot repeat a tool request.")
        if self.continue_after_tools and (not self.tools or self.needs_clarification):
            raise PydanticCustomError("plan_continuation", "Continuation requires executable tool observations.")
        if len(set(self.referenced_message_ids)) != len(self.referenced_message_ids) or any(not value or len(value) > 160 for value in self.referenced_message_ids):
            raise PydanticCustomError("plan_conversation_reference", "Conversation references must be distinct bounded IDs.")
        return self


class Reference(Contract):
    ref: str = Field(min_length=1, max_length=160)
    kind: Literal["profile_evidence", "memory", "job_evidence"]
    source_type: str = Field(min_length=1, max_length=80)
    authority: Literal["confirmed_profile", "confirmed_historical_memory", "public_role_archetype"]


class ContextItem(Contract):
    label: str = Field(min_length=1, max_length=600)
    category: str = Field(min_length=1, max_length=80)
    refs: list[Reference] = Field(max_length=8)
    status: Literal["confirmed", "unknown", "public_fixture"]
    confidence: float | None = Field(default=None, ge=0, le=1)
    inference_type: str | None = Field(default=None, max_length=80)


class ToolResult(Contract):
    name: ToolName
    status: Literal["succeeded", "unavailable", "denied", "failed"]
    items: list[ContextItem] = Field(max_length=12)
    summary: Literal["read_completed", "no_confirmed_source", "not_permitted", "tool_failure", "candidate_pending_review"]


class Proposal(Contract):
    kind: Literal["profile", "memory"]
    dimension: Literal["career_direction_priority", "work_style_primary_focus"]
    value: Literal["ai_application", "ai_product", "data_analysis", "hands_on", "product_and_requirements"]
    user_quote: str = Field(min_length=1, max_length=500)


class ResponseCore(Contract):
    # This FIRST JSON property is the only incremental user-visible stream.
    visible_response: str = Field(min_length=1, max_length=HARD_VISIBLE_CHARACTERS)
    citations: list[str] = Field(max_length=24)
    candidate_proposals: list[Proposal] = Field(max_length=2)

    @model_validator(mode="after")
    def integrity(self):
        if len(set(self.citations)) != len(self.citations):
            raise ValueError("Repeated citations are not allowed.")
        return self


class ResponseEnvelope(ResponseCore):
    # Integrity fields precede the ONLY optional provider field on the wire.
    suggestions: list[str] = Field(max_length=4)

    @model_validator(mode="after")
    def suggestions_safe(self):
        if any(not item.strip() or len(item) > 120 for item in self.suggestions):
            raise ValueError("Suggestions must be short optional next turns.")
        if len(set(self.suggestions)) != len(self.suggestions):
            raise ValueError("Repeated suggestions are not allowed.")
        return self


class StreamMetrics(Contract):
    transport_completed: bool = False
    provider_finish_category: Literal["pending", "normal_stop", "output_limit", "filtered", "unexpected", "missing", "interrupted", "refused", "cancelled"] = "pending"
    output_limit_reached: bool = False
    stream_chunk_count: int = Field(default=0, ge=0, le=MAX_STREAM_CHUNKS)
    visible_length_bucket: Literal["empty", "short", "medium", "long", "very_long", "over_limit"] = "empty"
    metadata_tail_present: bool = False
    envelope_complete: bool = False
    core_valid: bool = False
    optional_metadata_valid: bool = False
    degraded_optional_metadata: bool = False
    persistence_committed: bool = False
    close_failed: bool = False
    duplicate_finalization_count: int = Field(default=0, ge=0, le=1)
    cancellation_requested: bool = False
    partial_response: bool = False
    local_close_attempted: bool = False


class TurnStatus(str, Enum):
    COMPLETED = "COMPLETED"
    FAILED_TRANSPORT = "FAILED_TRANSPORT"
    FAILED_VALIDATION = "FAILED_VALIDATION"
    FAILED_PERSISTENCE = "FAILED_PERSISTENCE"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class PreviousTurn(Contract):
    status: TurnStatus = TurnStatus.UNKNOWN
    assistant_message_id: str = Field(default="", max_length=160)


class ProfileContextStamp(Contract):
    profile_id: str = Field(min_length=1, max_length=160)
    version: int = Field(ge=1)


def length_bucket(size):
    return next(label for bound, label in ((0, "empty"), (600, "short"), (2500, "medium"),
        (6000, "long"), (HARD_VISIBLE_CHARACTERS, "very_long"), (float("inf"), "over_limit")) if size <= bound)


class Activity(Contract):
    stage: Literal["understand", "plan", "profile", "memory", "evidence", "role", "match", "candidate", "respond", "complete", "failed", "bounded"]
    status: Literal["started", "succeeded", "failed", "skipped"]


class SafeUsage(Contract):
    provider: Literal["qwen", "fake"]
    model: Literal["qwen3.8-flash", "fake-model"]
    prompt_name: Literal["orange_planner", "orange_planner_repair", "orange_response"]
    prompt_version: Literal["v1"]
    thinking_enabled: Literal[False]
    input_tokens: int | None = Field(ge=0)
    output_tokens: int | None = Field(ge=0)
    total_tokens: int | None = Field(ge=0)
    latency_ms: int = Field(ge=0)
    status: Literal["succeeded"]
    retry_count: int = Field(ge=0, le=1)


class SafeFailure(Contract):
    category: Literal["validation_failure", "provider_failure", "runtime_failure", "provider_unavailable"]
    stage: Literal["context", "planning", "response_stream", "response_validation", "provider_setup", "persistence"]
    reason: Literal["structured_validation", "provider_error", "execution_error", "unknown_reference", "invented_candidate", "repeated_suggestion", "suggestion_policy", "stream_order", "stream_mismatch", "output_limit", "transport_incomplete", "stream_interrupted", "invalid_core", "persistence_error", "runtime_history_claim"]
    latency_ms: int = Field(ge=0)


ACTIVITY_LABELS = {
    "understand": "理解这条消息", "plan": "确定需要的上下文",
    "profile": "读取已确认画像", "memory": "查找相关已确认记忆",
    "evidence": "核对已有经历证据", "role": "查看已有岗位资料",
    "match": "读取已有证据关系", "candidate": "准备待复核候选",
    "respond": "组织回答", "complete": "回答已完成",
    "failed": "本次回答未完成", "bounded": "已达到本次执行边界",
}
