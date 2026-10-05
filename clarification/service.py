"""Existing provider abstraction; one request, strict scoped plan, no repairs."""

import json
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, create_model

from clarification.diagnostics import parse_failure
from clarification.models import ClarificationDecision
from clarification.needs import highest_value_needs
from clarification.policy import MAX_CONTEXT_CHARS, PROMPT_NAME, PROMPT_VERSION
from providers.models import GenerationOptions, LLMMessage, LLMUsage
from providers.errors import LLMStructuredOutputError
from resume_evidence.service import ResumeUsage, private_transport_logging

PROMPT_PATH = Path(__file__).resolve().parents[1] / "config/prompts/clarification_v1.md"


class ClarificationError(ValueError):
    def __init__(self, code, *, parse_diagnostic=None):
        self.code = code
        self.parse_diagnostic = parse_diagnostic
        super().__init__(code)


def no_question():
    return ClarificationDecision(should_ask=False, selected_need_id=None, question=None,
        suggested_replies=(), reason_summary="no_useful_question_now", source_refs=(), confidence="grounded")


def request_model(needs):
    ids = tuple(n.need_id for n in needs)
    questions = tuple(q for n in needs for q in n.allowed_questions)
    return create_model("ScopedClarificationDecision", __base__=ClarificationDecision,
        selected_need_id=(Literal[ids] | None, Field(default=None)),
        question=(Literal[questions] | None, Field(default=None, repr=False)))


def validate_decision(decision, context):
    known = {s.ref for s in context.sources}
    if any(ref not in known for ref in decision.source_refs):
        raise ClarificationError("INVALID_REFERENCE")
    if not decision.should_ask:
        return decision
    candidates = {n.need_id: n for n in highest_value_needs(context.needs)}
    need = candidates.get(decision.selected_need_id)
    if need is None:
        raise ClarificationError("INVALID_CLARIFICATION_PLAN")
    # Bounded templates permit semantic choice, not unsupported assumptions in
    # free prose. Provider wording is not an authority/security boundary.
    if (decision.question not in need.allowed_questions or len(set(decision.source_refs)) != len(decision.source_refs) or
            set(decision.source_refs) != set(need.source_refs) or
            len(set(decision.suggested_replies)) != len(decision.suggested_replies) or
            not set(decision.suggested_replies) <= set(need.allowed_replies)):
        raise ClarificationError("INVALID_CLARIFICATION_PLAN")
    if decision.question.count("？") + decision.question.count("?") != 1 or "\n" in decision.question:
        raise ClarificationError("INVALID_CLARIFICATION_PLAN")
    return decision


class ClarificationSelector:
    def select(self, provider, context):
        eligible = highest_value_needs(context.needs)
        if not eligible:
            return no_question(), None
        payload = {"sources": [s.model_dump() for s in context.sources],
                   "eligible_needs": [n.model_dump() for n in eligible], "partial": context.partial}
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(serialized) > MAX_CONTEXT_CHARS:
            raise ClarificationError("CLARIFICATION_CONTEXT_FAILED")
        options = GenerationOptions(model="qwen3.8-flash", thinking_enabled=False, max_retries=0,
                                    temperature=0, max_output_tokens=1200, timeout_seconds=30)
        messages = [LLMMessage(role="system", content=PROMPT_PATH.read_text(encoding="utf-8").strip()),
                    LLMMessage(role="user", content=serialized)]
        try:
            with private_transport_logging():
                response = provider.generate_structured(messages, request_model(eligible), options,
                    prompt_name=PROMPT_NAME, prompt_version=PROMPT_VERSION)
        except (LLMStructuredOutputError, ValidationError) as error:
            # Do not keep the exception/cause or its arbitrary loc/messages.
            raise ClarificationError("INVALID_CLARIFICATION_PLAN",
                                     parse_diagnostic=parse_failure(error)) from None
        try:
            decision = ClarificationDecision.model_validate(response.data.model_dump(mode="json", warnings=False))
        except ValidationError as error:
            raise ClarificationError("INVALID_CLARIFICATION_PLAN",
                                     parse_diagnostic=parse_failure(error)) from None
        except Exception:
            raise ClarificationError("INVALID_CLARIFICATION_PLAN") from None
        try:
            usage = LLMUsage.model_validate(response.usage.model_dump(warnings=False))
            if (response.provider not in {"fake", "qwen"} or response.model != options.model or response.retry_count != 0 or
                    response.thinking_enabled or response.prompt_name != PROMPT_NAME or response.prompt_version != PROMPT_VERSION or
                    type(response.latency_ms) is not int or not 0 <= response.latency_ms <= 120_000 or
                    any(n is not None and (type(n) is not int or n > 1_000_000) for n in
                        (usage.input_tokens, usage.output_tokens, usage.total_tokens))):
                raise ValueError("INVALID_CLARIFICATION_PLAN")
        except Exception:
            raise ClarificationError("INVALID_CLARIFICATION_PLAN") from None
        decision = validate_decision(decision, context)
        return decision, ResumeUsage(response.provider, usage.input_tokens, usage.output_tokens,
                                     usage.total_tokens, response.latency_ms)
