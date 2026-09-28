"""Provider-independent boundary tests."""

import inspect

from providers.base import LLMProvider
from providers.fake import FakeLLMProvider
from providers.qwen import QwenProvider


def test_llm_provider_is_a_small_abstract_contract() -> None:
    assert inspect.isabstract(LLMProvider)
    signature = inspect.signature(LLMProvider.generate_structured)
    assert "messages" in signature.parameters
    assert "response_model" in signature.parameters
    assert "options" in signature.parameters


def test_implementations_satisfy_provider_contract() -> None:
    assert issubclass(FakeLLMProvider, LLMProvider)
    assert issubclass(QwenProvider, LLMProvider)
