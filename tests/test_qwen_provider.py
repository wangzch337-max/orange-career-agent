"""Qwen request, parsing, usage, error mapping, and retry tests."""

from types import SimpleNamespace

import httpx
import openai
import pytest
from pydantic import SecretStr

from providers.demo import offline_response
from providers.errors import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMStructuredOutputError,
    LLMTimeoutError,
)
from providers.models import (
    GenerationOptions,
    LLMMessage,
    MessageRole,
    ProfileSignalExtraction,
)
from providers.qwen import QwenProvider


class ParseEndpoint:
    def __init__(self, effects):
        self.effects = list(effects)
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        effect = self.effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect


class ClientStub:
    def __init__(self, effects):
        self.endpoint = ParseEndpoint(effects)
        self.chat = SimpleNamespace(completions=self.endpoint)


def completion(parsed=None, *, usage=None, request_id="request-safe-001"):
    message = SimpleNamespace(parsed=parsed)
    return SimpleNamespace(
        id=request_id,
        choices=[SimpleNamespace(message=message)],
        usage=usage,
    )


def provider(client, *, sleeps=None, clock=None):
    sleep_calls = sleeps if sleeps is not None else []
    return QwenProvider(
        SecretStr("unit-test-key"),
        SecretStr("https://workspace.invalid/compatible-mode/v1"),
        client=client,
        sleep_fn=lambda seconds: sleep_calls.append(seconds),
        clock_fn=clock or (lambda: 1.0),
    )


def generate(qwen, *, options=None):
    return qwen.generate_structured(
        [LLMMessage(role=MessageRole.USER, content="sanitized")],
        ProfileSignalExtraction,
        options or GenerationOptions(max_retries=0),
        prompt_name="profile_signal_extraction",
        prompt_version="v1",
    )


def request_for_error():
    return httpx.Request("POST", "https://service.invalid/v1/chat/completions")


def status_error(error_type, status_code):
    request = request_for_error()
    response = httpx.Response(status_code, request=request)
    return error_type("transport detail", response=response, body=None)


def test_qwen_constructs_strict_parsing_request() -> None:
    client = ClientStub([completion(offline_response())])
    response = generate(provider(client))
    call = client.endpoint.calls[0]
    assert call["model"] == "qwen3.8-flash"
    assert call["response_format"] is ProfileSignalExtraction
    assert call["extra_body"] == {"enable_thinking": False}
    assert call["temperature"] == 0.1
    assert call["max_tokens"] == 800
    assert response.data.candidate_skills


def test_qwen_rejects_thinking_mode_before_transport() -> None:
    client = ClientStub([completion(offline_response())])
    with pytest.raises(LLMConfigurationError, match="关闭 thinking"):
        generate(provider(client), options=GenerationOptions(thinking_enabled=True))
    assert client.endpoint.calls == []


def test_qwen_uses_configured_model() -> None:
    client = ClientStub([completion(offline_response())])
    response = generate(
        provider(client),
        options=GenerationOptions(model="qwen3.8-flash", max_retries=0),
    )
    assert response.model == "qwen3.8-flash"
    assert client.endpoint.calls[0]["model"] == "qwen3.8-flash"


def test_pydantic_parse_success_and_request_id() -> None:
    response = generate(provider(ClientStub([completion(offline_response())])))
    assert isinstance(response.data, ProfileSignalExtraction)
    assert response.request_id == "request-safe-001"


def test_malformed_parsed_result_is_structured_error() -> None:
    invalid = {"candidate_skills": [{"label": "AI", "confidence": 8, "evidence_ids": ["x"]}]}
    with pytest.raises(LLMStructuredOutputError):
        generate(provider(ClientStub([completion(invalid)])))


def test_empty_response_is_structured_error() -> None:
    empty = SimpleNamespace(id="empty", choices=[], usage=None)
    with pytest.raises(LLMStructuredOutputError, match="空响应"):
        generate(provider(ClientStub([empty])))


def test_authentication_error_maps_without_retry() -> None:
    client = ClientStub([status_error(openai.AuthenticationError, 401)])
    sleeps = []
    with pytest.raises(LLMAuthenticationError, match="认证失败"):
        generate(
            provider(client, sleeps=sleeps),
            options=GenerationOptions(max_retries=2),
        )
    assert len(client.endpoint.calls) == 1
    assert sleeps == []


def test_timeout_error_mapping_without_retry_budget() -> None:
    timeout = openai.APITimeoutError(request_for_error())
    with pytest.raises(LLMTimeoutError):
        generate(provider(ClientStub([timeout])))


def test_rate_limit_error_mapping() -> None:
    error = status_error(openai.RateLimitError, 429)
    with pytest.raises(LLMRateLimitError):
        generate(provider(ClientStub([error])))


def test_transient_timeout_retries_then_succeeds() -> None:
    client = ClientStub(
        [openai.APITimeoutError(request_for_error()), completion(offline_response())]
    )
    sleeps = []
    response = generate(
        provider(client, sleeps=sleeps),
        options=GenerationOptions(max_retries=1),
    )
    assert response.retry_count == 1
    assert len(client.endpoint.calls) == 2
    assert sleeps == [0.25]


def test_retryable_server_error_is_bounded() -> None:
    errors = [status_error(openai.InternalServerError, 500) for _ in range(3)]
    client = ClientStub(errors)
    sleeps = []
    with pytest.raises(LLMProviderError) as caught:
        generate(
            provider(client, sleeps=sleeps),
            options=GenerationOptions(max_retries=2),
        )
    assert caught.value.retryable is True
    assert len(client.endpoint.calls) == 3
    assert sleeps == [0.25, 0.5]


def test_non_retryable_bad_request_does_not_retry() -> None:
    client = ClientStub([status_error(openai.BadRequestError, 400)])
    sleeps = []
    with pytest.raises(LLMProviderError) as caught:
        generate(
            provider(client, sleeps=sleeps),
            options=GenerationOptions(max_retries=3),
        )
    assert caught.value.retryable is False
    assert len(client.endpoint.calls) == 1
    assert sleeps == []


def test_usage_and_latency_are_normalized() -> None:
    usage = SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18)
    times = iter([10.0, 10.125])
    response = generate(
        provider(ClientStub([completion(offline_response(), usage=usage)]), clock=lambda: next(times))
    )
    assert response.usage.input_tokens == 11
    assert response.usage.output_tokens == 7
    assert response.usage.total_tokens == 18
    assert response.latency_ms == 125


def test_safe_observability_metadata_has_no_credentials() -> None:
    response = generate(provider(ClientStub([completion(offline_response())])))
    rendered = repr(response.safe_metadata())
    assert "unit-test-key" not in rendered
    assert "workspace.invalid" not in rendered
    assert response.safe_metadata()["thinking_enabled"] is False
