"""Deterministic FakeLLMProvider tests."""

import socket

import pytest

from providers.demo import offline_response
from providers.errors import LLMStructuredOutputError
from providers.fake import FakeLLMProvider
from providers.models import GenerationOptions, LLMMessage, MessageRole, ProfileSignalExtraction


def generate(provider: FakeLLMProvider):
    return provider.generate_structured(
        [LLMMessage(role=MessageRole.USER, content="sanitized")],
        ProfileSignalExtraction,
        GenerationOptions(model="fake-model", max_retries=0),
        prompt_name="profile_signal_extraction",
        prompt_version="v1",
    )


def test_fake_provider_returns_valid_structured_wrapper() -> None:
    provider = FakeLLMProvider(offline_response())
    response = generate(provider)
    assert isinstance(response.data, ProfileSignalExtraction)
    assert response.provider == "fake"
    assert response.prompt_name == "profile_signal_extraction"
    assert response.prompt_version == "v1"
    assert response.usage.total_tokens is None
    assert provider.call_count == 1


def test_fake_provider_rejects_malformed_result() -> None:
    provider = FakeLLMProvider(
        {"candidate_skills": [{"label": "AI", "confidence": 2, "evidence_ids": ["x"]}]}
    )
    with pytest.raises(LLMStructuredOutputError):
        generate(provider)


def test_fake_provider_rejects_empty_predefinition() -> None:
    with pytest.raises(LLMStructuredOutputError):
        generate(FakeLLMProvider(None))


def test_fake_provider_never_uses_network(monkeypatch) -> None:
    calls = []

    def tracked(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("network called")

    monkeypatch.setattr(socket, "create_connection", tracked)
    response = generate(FakeLLMProvider(offline_response()))
    assert response.data.candidate_skills
    assert calls == []
