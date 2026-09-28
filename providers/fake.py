"""Deterministic, network-free provider for tests and offline development."""

from time import perf_counter
from typing import Mapping, Sequence, Type, TypeVar, Union

from pydantic import BaseModel, ValidationError

from providers.base import LLMProvider
from providers.errors import LLMStructuredOutputError
from providers.models import (
    GenerationOptions,
    LLMMessage,
    LLMUsage,
    StructuredLLMResponse,
)


ResponseT = TypeVar("ResponseT", bound=BaseModel)


class FakeLLMProvider(LLMProvider):
    """Return a predefined response without importing or opening network clients."""

    name = "fake"

    def __init__(
        self,
        predefined_response: Union[BaseModel, Mapping[str, object], None],
        *,
        predefined_responses: Sequence[Union[BaseModel, Mapping[str, object]]] | None = None,
    ) -> None:
        self.predefined_response = predefined_response
        self.predefined_responses = list(predefined_responses or [])
        self.call_count = 0

    def generate_structured(
        self,
        messages: Sequence[LLMMessage],
        response_model: Type[ResponseT],
        options: GenerationOptions,
        *,
        prompt_name: str,
        prompt_version: str,
    ) -> StructuredLLMResponse[ResponseT]:
        del messages
        started = perf_counter()
        self.call_count += 1
        selected = (
            self.predefined_responses[self.call_count - 1]
            if self.call_count <= len(self.predefined_responses)
            else self.predefined_response
        )
        if selected is None:
            raise LLMStructuredOutputError("Fake provider 没有预定义结构化响应。")
        raw = (
            selected.model_dump()
            if isinstance(selected, BaseModel)
            else selected
        )
        try:
            data = response_model.model_validate(raw)
        except ValidationError as exc:
            raise LLMStructuredOutputError("Fake provider 响应不符合 Pydantic schema。") from exc
        latency_ms = max(0, round((perf_counter() - started) * 1000))
        return StructuredLLMResponse[ResponseT](
            data=data,
            provider=self.name,
            model=options.model,
            usage=LLMUsage(),
            latency_ms=latency_ms,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            thinking_enabled=options.thinking_enabled,
        )
