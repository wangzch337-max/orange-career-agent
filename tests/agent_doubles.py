"""Offline scripted transport, deliberately NOT a production reply implementation."""

import json

from career_runtime.models import Plan, ResponseEnvelope, ToolInput, ToolName, ToolRequest, PROFILE_TOOLS, MEMORY_TOOLS, ROLE_TOOLS
from career_runtime.streaming import StreamingLLMProvider, StreamComplete, StreamDelta
from providers.models import StructuredLLMResponse


def request(name, *, sections=(), role_id="", dimension="", value="", user_quote=""):
    return ToolRequest(name=ToolName(name), arguments=ToolInput(sections=list(sections), role_id=role_id,
        dimension=dimension, value=value, user_quote=user_quote))


def plan(*, relevance="GENERAL_QA", tools=(), continuing=False, suggestions="none", intent="answer", clarify=False):
    return Plan(intent=intent, relevance=relevance, response_mode="clarification" if clarify else "direct",
        needs_profile=any(t.name in PROFILE_TOOLS for t in tools),
        needs_memory=any(t.name in MEMORY_TOOLS for t in tools),
        needs_role=any(t.name in ROLE_TOOLS for t in tools), needs_tools=bool(tools), tools=list(tools),
        needs_clarification=clarify, clarification_reason="missing_goal" if clarify else "none",
        evidence_requirements=[], suggestion_policy=suggestions, continue_after_tools=continuing)


def answer(text="这是公开合成答复。", *, suggestions=(), citations=(), proposals=()):
    return ResponseEnvelope(visible_response=text, suggestions=list(suggestions), citations=list(citations),
                            candidate_proposals=list(proposals))


class ScriptedProvider(StreamingLLMProvider):
    name = "fake"

    def __init__(self, plans=None, response=None, *, chunks=None, failure=None):
        self.plans = list(plans or [plan()])
        self.response = response or answer()
        self.chunks = chunks
        self.failure = failure
        self.requests = []
        self.structured_calls = self.stream_calls = 0
        self.delivered = 0

    def generate_structured(self, messages, response_model, options, *, prompt_name, prompt_version):
        self.structured_calls += 1
        self.requests.append(json.loads(messages[1].content))
        data = self.plans.pop(0)
        if isinstance(data, Exception):
            raise data
        data = response_model.model_validate(data.model_dump() if hasattr(data, "model_dump") else data)
        return StructuredLLMResponse(data=data, provider="fake", model="fake-model", latency_ms=0,
                                     prompt_name=prompt_name, prompt_version=prompt_version)

    def stream_structured(self, messages, response_model, options, *, prompt_name, prompt_version):
        self.stream_calls += 1
        self.requests.append(json.loads(messages[1].content))
        payload = self.response.model_dump_json()
        # Splitting exists only in this explicitly scripted OFFLINE test double.
        for chunk in self.chunks if self.chunks is not None else [payload[:38], payload[38:60], payload[60:]]:
            self.delivered += 1
            yield StreamDelta(chunk)
            if self.failure is not None:
                raise self.failure
        yield StreamComplete(StructuredLLMResponse(data=self.response, provider="fake", model="fake-model",
            latency_ms=0, prompt_name=prompt_name, prompt_version=prompt_version))
