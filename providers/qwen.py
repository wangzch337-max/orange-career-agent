"""Qwen provider using Alibaba Model Studio's OpenAI-compatible transport."""

from time import perf_counter, sleep
from typing import Callable, Optional, Sequence, Type, TypeVar

import openai
from openai import OpenAI
from pydantic import BaseModel, SecretStr, ValidationError

from providers.base import LLMProvider
from providers.errors import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMError,
    LLMProviderError,
    LLMRateLimitError,
    LLMStructuredOutputError,
    LLMTimeoutError,
)
from providers.models import (
    GenerationOptions,
    LLMMessage,
    LLMSettings,
    LLMUsage,
    StructuredLLMResponse,
)


ResponseT = TypeVar("ResponseT", bound=BaseModel)


class QwenProvider(LLMProvider):
    """Strict structured output adapter for Orange's current live provider."""

    name = "qwen"

    def __init__(
        self,
        api_key: SecretStr,
        base_url: SecretStr,
        *,
        client: Optional[object] = None,
        sleep_fn: Callable[[float], None] = sleep,
        clock_fn: Callable[[], float] = perf_counter,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._client = client
        self._sleep = sleep_fn
        self._clock = clock_fn

    @classmethod
    def from_settings(cls, settings: LLMSettings) -> "QwenProvider":
        settings.require_live_qwen()
        assert settings.api_key is not None
        assert settings.base_url is not None
        return cls(settings.api_key, settings.base_url)

    def generate_structured(
        self,
        messages: Sequence[LLMMessage],
        response_model: Type[ResponseT],
        options: GenerationOptions,
        *,
        prompt_name: str,
        prompt_version: str,
    ) -> StructuredLLMResponse[ResponseT]:
        if options.thinking_enabled:
            raise LLMConfigurationError("Orange Qwen structured extraction 必须关闭 thinking。")
        client = self._client or self._create_client(options)
        started = self._clock()

        for retry_count in range(options.max_retries + 1):
            try:
                completion = client.chat.completions.parse(
                    model=options.model,
                    messages=[message.model_dump(mode="json") for message in messages],
                    response_format=response_model,
                    temperature=options.temperature,
                    max_tokens=options.max_output_tokens,
                    extra_body={"enable_thinking": False},
                )
                data = self._extract_parsed(completion, response_model)
                usage = self._normalize_usage(getattr(completion, "usage", None))
                latency_ms = max(0, round((self._clock() - started) * 1000))
                return StructuredLLMResponse[ResponseT](
                    data=data,
                    provider=self.name,
                    model=options.model,
                    usage=usage,
                    latency_ms=latency_ms,
                    prompt_name=prompt_name,
                    prompt_version=prompt_version,
                    request_id=getattr(completion, "id", None),
                    thinking_enabled=False,
                    retry_count=retry_count,
                )
            except Exception as exc:
                mapped = self._map_exception(exc)
                if mapped.retryable and retry_count < options.max_retries:
                    self._sleep(min(0.25 * (2**retry_count), 1.0))
                    continue
                raise mapped from None

        raise LLMProviderError("Qwen 请求未返回结果。")

    def _create_client(self, options: GenerationOptions) -> OpenAI:
        try:
            return OpenAI(
                api_key=self._api_key.get_secret_value(),
                base_url=self._base_url.get_secret_value(),
                timeout=options.timeout_seconds,
                max_retries=0,
            )
        except Exception as exc:
            raise LLMConfigurationError("无法建立 Qwen transport，请检查本地配置。") from exc

    @staticmethod
    def _extract_parsed(completion: object, response_model: Type[ResponseT]) -> ResponseT:
        choices = getattr(completion, "choices", None)
        if not choices:
            raise LLMStructuredOutputError("Qwen 返回了空响应。")
        parsed = getattr(choices[0].message, "parsed", None)
        if parsed is None:
            raise LLMStructuredOutputError("Qwen 未返回可解析的严格结构化数据。")
        try:
            if isinstance(parsed, response_model):
                return parsed
            return response_model.model_validate(parsed)
        except ValidationError as exc:
            raise LLMStructuredOutputError("Qwen 结构化数据未通过 Pydantic 验证。") from exc

    @staticmethod
    def _normalize_usage(usage: object) -> LLMUsage:
        if usage is None:
            return LLMUsage()
        return LLMUsage(
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
        )

    @staticmethod
    def _map_exception(exc: Exception) -> LLMError:
        if isinstance(exc, LLMError):
            return exc
        if isinstance(exc, openai.AuthenticationError):
            return LLMAuthenticationError("Qwen 认证失败，请检查本地配置。")
        if isinstance(exc, openai.APITimeoutError):
            return LLMTimeoutError()
        if isinstance(exc, openai.RateLimitError):
            return LLMRateLimitError()
        if isinstance(exc, openai.APIConnectionError):
            return LLMProviderError("暂时无法连接 Qwen 服务。", retryable=True)
        if isinstance(exc, openai.APIStatusError):
            status_code = getattr(exc, "status_code", None)
            if status_code is not None and status_code >= 500:
                return LLMProviderError(
                    "Qwen 服务暂时不可用。",
                    retryable=True,
                    status_code=status_code,
                )
            return LLMProviderError(
                "Qwen 请求被服务拒绝。",
                retryable=False,
                status_code=status_code,
            )
        if isinstance(exc, ValidationError):
            return LLMStructuredOutputError("结构化响应未通过 Pydantic 验证。")
        return LLMProviderError("Qwen provider 调用失败。", retryable=False)
