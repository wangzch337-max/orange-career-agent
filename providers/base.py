"""Provider-independent strict structured-generation contract."""

from abc import ABC, abstractmethod
from typing import Sequence, Type, TypeVar

from pydantic import BaseModel

from providers.models import GenerationOptions, LLMMessage, StructuredLLMResponse


ResponseT = TypeVar("ResponseT", bound=BaseModel)


class LLMProvider(ABC):
    """Future Agent code depends on this boundary, never on vendor transport."""

    name: str

    @abstractmethod
    def generate_structured(
        self,
        messages: Sequence[LLMMessage],
        response_model: Type[ResponseT],
        options: GenerationOptions,
        *,
        prompt_name: str,
        prompt_version: str,
    ) -> StructuredLLMResponse[ResponseT]:
        """Generate and validate one strict structured response."""
