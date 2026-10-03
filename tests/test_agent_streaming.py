"""Transport-level streaming, Unicode, failure and reasoning exclusion."""

from types import SimpleNamespace as NS

import pytest
from pydantic import SecretStr

from career_runtime.models import ResponseEnvelope, Plan
from career_runtime.streaming import StreamingQwenProvider, StreamDelta, StreamComplete, VisibleJSONStream
from providers.models import GenerationOptions, LLMMessage
from providers.errors import LLMProviderError, LLMStructuredOutputError
from tests.agent_doubles import answer, plan


class Chunks:
    def __init__(self, values):
        self.values = values
        self.closed = False
        self.delivered = 0

    def __iter__(self):
        for value in self.values:
            self.delivered += 1
            if isinstance(value, Exception):
                raise value
            yield value

    def close(self):
        self.closed = True


def chunk(text="", finish=None, usage=None):
    return NS(choices=[NS(delta=NS(content=text, reasoning_content="NEVER_EXPOSE_PRIVATE_REASONING"), finish_reason=finish)], usage=usage)


class Transport:
    def __init__(self, values):
        self.stream = Chunks(values)
        self.calls = []
        self.chat = NS(completions=self)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.stream


def provider(transport):
    return StreamingQwenProvider(SecretStr("sk-test-not-a-real-secret"), SecretStr("https://example.invalid"), client=transport)


def test_real_adapter_yields_before_transport_finishes_and_counts_usage():
    payload = answer("真实传输块边界。").model_dump_json()
    transport = Transport([chunk(payload[:36]), chunk(payload[36:]), chunk(finish="stop", usage=NS(prompt_tokens=10, completion_tokens=20, total_tokens=30))])
    iterator = provider(transport).stream_structured([LLMMessage(role="user", content="公开测试")], ResponseEnvelope,
        GenerationOptions(max_retries=3), prompt_name="orange_response", prompt_version="v1")
    first = next(iterator)
    assert isinstance(first, StreamDelta) and first.content == payload[:36]
    assert transport.stream.delivered == 1 and not transport.stream.closed
    remaining = list(iterator)
    assert isinstance(remaining[-1], StreamComplete)
    assert remaining[-1].response.usage.total_tokens == 30
    assert remaining[-1].response.retry_count == 0
    assert len(transport.calls) == 1 and transport.stream.closed
    assert transport.calls[0]["stream"] is True
    assert transport.calls[0]["extra_body"] == {"enable_thinking": False}
    assert transport.calls[0]["response_format"]["json_schema"]["strict"] is True
    assert "NEVER_EXPOSE" not in repr(remaining)


@pytest.mark.parametrize("ending", ["length", "content_filter", None])
def test_incomplete_stream_no_final_and_never_retry(ending):
    transport = Transport([chunk(answer().model_dump_json(), finish=ending)])
    with pytest.raises(LLMStructuredOutputError):
        list(provider(transport).stream_structured([], ResponseEnvelope, GenerationOptions(max_retries=3),
             prompt_name="orange_response", prompt_version="v1"))
    assert len(transport.calls) == 1 and transport.stream.closed


def test_stream_failure_closes_transport_without_retry():
    transport = Transport([chunk('{"visible_response":"partial'), LLMProviderError("safe failure", retryable=True)])
    with pytest.raises(LLMProviderError):
        list(provider(transport).stream_structured([], ResponseEnvelope, GenerationOptions(max_retries=3),
             prompt_name="orange_response", prompt_version="v1"))
    assert len(transport.calls) == 1 and transport.stream.closed


def test_structured_planner_reuses_bounded_existing_retry_mechanism():
    class RetryTransport:
        def __init__(self):
            self.calls = 0
            self.chat = NS(completions=self)

        def parse(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise LLMProviderError("safe transient", retryable=True)
            return NS(choices=[NS(message=NS(parsed=plan()))], usage=None, id=None)
    transport = RetryTransport()
    result = StreamingQwenProvider(SecretStr("fake"), SecretStr("https://example.invalid"), client=transport, sleep_fn=lambda _: None).generate_structured(
        [], Plan, GenerationOptions(max_retries=1), prompt_name="orange_planner", prompt_version="v1")
    assert transport.calls == 2 and result.retry_count == 1


@pytest.mark.parametrize("text", ['中文换行\n反斜线\\引号"', "emoji 🍊", "混合 UTF-16 🍊 and 中文"])
def test_json_projection_survives_every_chunk_boundary(text):
    import json
    payload = json.dumps(answer(text).model_dump(), ensure_ascii=True)
    for boundary in range(1, len(payload)):
        projection = VisibleJSONStream()
        assert projection.feed(payload[:boundary]) + projection.feed(payload[boundary:]) == text
        assert projection.visible == text


@pytest.mark.parametrize("payload", ['{"reasoning":"hidden"}', '{"scratchpad":"hidden"}', '{"visible_response":"ok","reasoning":"hidden"}'])
def test_hidden_reasoning_cannot_be_a_response_field(payload):
    with pytest.raises(ValueError):
        ResponseEnvelope.model_validate_json(payload)
    if not payload.startswith('{"visible_response"'):
        with pytest.raises(ValueError):
            VisibleJSONStream().feed(payload)
