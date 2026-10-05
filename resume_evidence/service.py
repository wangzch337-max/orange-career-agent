"""One strict call through the existing LLMProvider; no Agent or authority writes."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import logging
import sys
from typing import Literal

from pydantic import ValidationError

from providers.base import LLMProvider
from providers.models import GenerationOptions, LLMMessage, LLMUsage
from resume_evidence.context import ProviderResumeContext
from resume_evidence.models import ResumeEvidenceExtraction
from resume_evidence.policy import MODEL, PROMPT_NAME, PROMPT_VERSION
from resume_evidence.prompt import load_resume_evidence_prompt
from resume_evidence.validation import validate_extraction, ResumeValidationError

_PRIVATE_CALL = ContextVar("orange_resume_private_provider_call", default=False)


class _PrivateTransportLogFilter(logging.Filter):
    def filter(self, record):
        return not _PRIVATE_CALL.get()


@contextmanager
def private_transport_logging():
    """Transport debug payloads must not log this request; other contexts unchanged."""
    for name in set(sys.modules) | set(logging.Logger.manager.loggerDict):
        if name.split(".")[0] in {"openai", "httpx", "httpcore"}:
            logger = logging.getLogger(name)
            if not any(isinstance(item, _PrivateTransportLogFilter) for item in logger.filters):
                logger.addFilter(_PrivateTransportLogFilter())
    token = _PRIVATE_CALL.set(True)
    try:
        yield
    finally:
        _PRIVATE_CALL.reset(token)


@dataclass(frozen=True)
class ResumeUsage:
    provider: Literal["fake", "qwen"]
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    latency_ms: int
    retries: int = 0


class ResumeEvidenceExtractor:
    def extract(self, provider: LLMProvider, context: ProviderResumeContext):
        options = GenerationOptions(model=MODEL, thinking_enabled=False, max_retries=0,
                                    temperature=0, max_output_tokens=4096, timeout_seconds=30)
        messages = [LLMMessage(role="system", content=load_resume_evidence_prompt()),
                    LLMMessage(role="user", content=context.serialized())]
        with private_transport_logging():
            response = provider.generate_structured(messages, ResumeEvidenceExtraction, options,
                prompt_name=PROMPT_NAME, prompt_version=PROMPT_VERSION)
        try:
            # Do not trust a provider's constructed or differently typed model.
            extraction = ResumeEvidenceExtraction.model_validate(response.data.model_dump(mode="json", warnings=False))
            usage = LLMUsage.model_validate(response.usage.model_dump(warnings=False))
            if (response.provider not in {"fake", "qwen"} or response.model != MODEL or
                    response.thinking_enabled or response.retry_count != 0):
                raise ValueError("INVALID_PROVIDER_ENVELOPE")
            if any(value is not None and value > 1_000_000 for value in (usage.input_tokens, usage.output_tokens, usage.total_tokens)):
                raise ValueError("INVALID_PROVIDER_ENVELOPE")
            if type(response.latency_ms) is not int or not 0 <= response.latency_ms <= 120_000:
                raise ValueError("INVALID_PROVIDER_ENVELOPE")
        except (ValidationError, ValueError, AttributeError, TypeError):
            raise ResumeValidationError("INVALID_STRUCTURED_OUTPUT") from None
        extraction = validate_extraction(extraction, context)
        return extraction, ResumeUsage(response.provider, usage.input_tokens, usage.output_tokens,
                                       usage.total_tokens, response.latency_ms)
