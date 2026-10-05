"""Strict, ephemeral contracts. None is a Profile or a Memory write command."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from clarification.policy import MAX_NEEDS, MAX_REFS, MAX_SOURCES, ReasonCode

Ref = Annotated[str, Field(strict=True, pattern=r"^(?:rs|pf|mm|cv|cu|an)_[0-9]{3}$")]
Refs = Annotated[tuple[Ref, ...], Field(max_length=MAX_REFS)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True,
                              revalidate_instances="always")


class ClarificationSource(Contract):
    ref: Ref
    kind: Literal["resume", "profile", "memory", "conversation", "current", "answer"]
    authority: Literal["resume_provided", "confirmed_profile", "confirmed_historical_memory",
                       "conversation_context", "explicit_user_input"]
    category: str = Field(strict=True, max_length=60)
    text: str = Field(strict=True, min_length=1, max_length=600, repr=False)
    ambiguity: str = Field(strict=True, max_length=60)
    explicit_goal: bool = Field(strict=True)
    detail_known: bool = Field(default=False, strict=True)
    semantic_scope: str = Field(pattern=r"^[0-9a-f]{20}$")
    # Local resolver metadata is never serialized into the provider prompt.
    origin_refs: tuple[str, ...] = Field(default=(), max_length=8, exclude=True, repr=False)


class ClarificationNeed(Contract):
    need_id: str = Field(pattern=r"^need_[0-9a-f]{20}$")
    topic: str = Field(max_length=100)
    reason_code: ReasonCode
    source_refs: Refs
    priority: Literal["conflict", "direction", "ownership", "capability", "detail"]
    answerability: Literal["user_can_answer"] = "user_can_answer"
    already_known: Literal[False] = False
    uncertainty: Literal["unknown", "ambiguous", "possible_change"]
    conflict_summary: Literal["none", "different_explicit_intents", "historical_information_may_be_stale"]
    allowed_questions: tuple[str, ...] = Field(min_length=1, max_length=2, repr=False)
    allowed_replies: tuple[str, ...] = Field(max_length=4, repr=False)


class ClarificationDecision(Contract):
    should_ask: bool = Field(strict=True)
    # These three omissions have exactly the same meaning as null/null/[];
    # the branch validator still rejects an absent need/question when asking.
    # The SDK wire schema requires all keys; defaults are local compatibility.
    selected_need_id: str | None = Field(default=None, pattern=r"^need_[0-9a-f]{20}$")
    question: str | None = Field(default=None, strict=True, min_length=1, max_length=360, repr=False)
    suggested_replies: tuple[Annotated[str, Field(strict=True, min_length=1, max_length=100)], ...] = Field(default=(), max_length=4, repr=False)
    # Closed safe rationale, not free prose or model reasoning.
    reason_summary: Literal["highest_value_supported_need", "no_useful_question_now"]
    source_refs: Refs
    confidence: Literal["grounded", "uncertain"]

    @model_validator(mode="after")
    def zero_or_one(self):
        if self.should_ask:
            if self.selected_need_id is None or self.question is None or self.reason_summary != "highest_value_supported_need":
                raise ValueError("INVALID_CLARIFICATION_PLAN")
        elif (self.selected_need_id is not None or self.question is not None or self.suggested_replies or
              self.source_refs or self.reason_summary != "no_useful_question_now"):
            raise ValueError("INVALID_CLARIFICATION_PLAN")
        return self


class ClarificationContext(Contract):
    sources: tuple[ClarificationSource, ...] = Field(max_length=MAX_SOURCES, repr=False)
    needs: tuple[ClarificationNeed, ...] = Field(max_length=MAX_NEEDS, repr=False)
    current_source_ref: Ref | None
    partial: bool = Field(strict=True)


class QuestionBinding(Contract):
    owner_scope_id: str = Field(repr=False)
    conversation_id: str = Field(repr=False)
    state_version: int = Field(ge=0)
    resume_source_id: str
    resume_evidence_version: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    profile_id: str | None = Field(repr=False)
    profile_version: int | None = Field(ge=1)


class OpenClarification(Contract):
    question_id: str = Field(pattern=r"^question_[0-9a-f]{32}$")
    binding: QuestionBinding = Field(repr=False)
    need: ClarificationNeed = Field(repr=False)
    decision: ClarificationDecision = Field(repr=False)
    resolved_sources: tuple[tuple[str, str, tuple[str, ...]], ...] = Field(max_length=8, repr=False)


class ClarificationAnswerCandidate(Contract):
    candidate_id: str = Field(pattern=r"^clarification_answer_[0-9a-f]{32}$")
    question_id: str
    need_id: str
    topic: str
    user_answer: str = Field(strict=True, min_length=1, max_length=2000, repr=False)
    source: Literal["explicit_user_input"] = "explicit_user_input"
    status: Literal["candidate"] = "candidate"
    uncertainty: Literal["none", "explicit_uncertainty"]
    created_at: datetime
    binding: QuestionBinding = Field(repr=False)
    resolved_sources: tuple[tuple[str, str, tuple[str, ...]], ...] = Field(max_length=8, repr=False)
