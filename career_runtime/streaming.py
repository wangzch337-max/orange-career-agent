"""Provider-independent streaming contract and real Qwen chunk adapter."""

from abc import abstractmethod
from dataclasses import dataclass, field
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Sequence, Type

from pydantic import BaseModel

from providers.base import LLMProvider
from providers.errors import LLMConfigurationError, LLMStructuredOutputError
from providers.models import GenerationOptions, LLMMessage, LLMUsage, StructuredLLMResponse
from providers.qwen import QwenProvider
from career_runtime.diagnostics import ProviderAttempt
from career_runtime.models import Plan, ResponseEnvelope, StreamMetrics, length_bucket
from career_runtime.cancellation import CancellationRequested
from career_runtime.finalization import MAX_WIRE_CHARACTERS, finalize_wire
from career_runtime.response_budget import HARD_VISIBLE_CHARACTERS, MAX_STREAM_CHUNKS, MAX_JSON_HEADER_CHARACTERS
from observability.events import diagnostic_span
from observability.models import DiagnosticComponent as DC


@dataclass(frozen=True)
class StreamDelta:
    content: str


@dataclass(frozen=True)
class StreamComplete:
    response: StructuredLLMResponse
    metrics: StreamMetrics = field(default_factory=lambda: StreamMetrics(transport_completed=True,
        provider_finish_category="normal_stop", envelope_complete=True, core_valid=True, optional_metadata_valid=True))


class ResponseStreamError(LLMStructuredOutputError):
    def __init__(self, reason):
        super().__init__("Response stream did not safely complete.")
        self.reason = reason


_GENERATION_SCOPE = ContextVar("orange_provider_generation", default=None)


class StreamingLLMProvider(LLMProvider):
    @property
    def _turn_control(self):
        binding = _GENERATION_SCOPE.get()
        return binding[1] if binding is not None and binding[0] is self else None

    @contextmanager
    def cancellation_scope(self, control):
        token = _GENERATION_SCOPE.set((self, control))
        self._bind_generation(control)
        try:
            yield
        finally:
            _GENERATION_SCOPE.reset(token)

    def _bind_generation(self, control):
        pass

    @abstractmethod
    def stream_structured(self, messages: Sequence[LLMMessage], response_model: Type[BaseModel],
                          options: GenerationOptions, *, prompt_name: str, prompt_version: str
                          ) -> Iterator[StreamDelta | StreamComplete]:
        """Yield real transport deltas then exactly one validated completion."""


class StreamingQwenProvider(QwenProvider, StreamingLLMProvider):
    """Reuse the existing structured adapter and sanitized transport/error policy.

    Streaming never retries: reconnecting after visible output could duplicate it.
    Raw JSON is bounded transient memory, not a diagnostic or persisted response.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attempts: list[ProviderAttempt] = []
        self.last_stream_metrics = StreamMetrics()

    def _bind_generation(self, control):
        control.provider_metrics[0] = StreamMetrics()
        self._latest_attempts = control.provider_attempts
        self._latest_metrics = control.provider_metrics

    @property
    def attempts(self):
        control = self._turn_control
        return control.provider_attempts if control else self._latest_attempts

    @attempts.setter
    def attempts(self, value):
        self._latest_attempts = value

    @property
    def last_stream_metrics(self):
        control = self._turn_control
        return (control.provider_metrics if control else self._latest_metrics)[0]

    @last_stream_metrics.setter
    def last_stream_metrics(self, value):
        control = self._turn_control
        if control:
            control.provider_metrics[0] = value
        else:
            self._latest_metrics = [value]

    def generate_structured(self, messages, response_model, options, *, prompt_name, prompt_version):
        if response_model is not Plan:
            return super().generate_structured(messages, response_model, options,
                prompt_name=prompt_name, prompt_version=prompt_version)
        if options.thinking_enabled:
            raise LLMConfigurationError("Orange 规划必须关闭 thinking。")
        client = self._client or self._create_client(options)
        control = getattr(self, "_turn_control", None)
        owned_client = self._client is None
        detach = control.attach_close(getattr(client, "close", None)) if control and owned_client else lambda: None
        started = self._clock()
        for retry in range(options.max_retries+1):
            attempt_started, usage, succeeded = self._clock(), LLMUsage(), False
            called = retrying = False
            with diagnostic_span(DC.PROVIDER, "provider_call") as statistics:
                try:
                    if control:
                        control.checkpoint()
                    called = True
                    completion = client.chat.completions.parse(model=options.model,
                        messages=[message.model_dump(mode="json") for message in messages], response_format=Plan,
                        temperature=options.temperature, max_tokens=options.max_output_tokens,
                        extra_body={"enable_thinking": False})
                    usage = self._normalize_usage(getattr(completion, "usage", None))
                    if control:
                        control.checkpoint()
                    choices = getattr(completion, "choices", None)
                    if not choices:
                        raise LLMStructuredOutputError("规划响应为空。", stage="Plan", error_type="empty_response")
                    if getattr(choices[0].message, "refusal", None):
                        raise LLMStructuredOutputError("规划响应被拒绝。", stage="Plan", error_type="provider_refusal")
                    if getattr(choices[0].message, "parsed", None) is None:
                        raise LLMStructuredOutputError("规划没有结构化结果。", stage="Plan", error_type="missing_structured_output")
                    data = self._extract_parsed(completion, Plan)
                    succeeded = True
                    statistics.update(counts={"provider_call_count": 1}, safe_metadata={"provider": "qwen", "model_id": options.model, "retry_count": retry})
                    return StructuredLLMResponse(data=data, provider=self.name, model=options.model,
                        usage=usage, latency_ms=max(0, round((self._clock()-started)*1000)),
                        prompt_name=prompt_name, prompt_version=prompt_version, thinking_enabled=False, retry_count=retry)
                except Exception as exc:
                    if control:
                        control.checkpoint()
                    import json
                    if isinstance(exc, json.JSONDecodeError):
                        mapped = LLMStructuredOutputError("规划 JSON 无效。", stage="Plan", error_type="json_invalid")
                    else:
                        mapped = self._map_exception(exc, validation_stage="Plan")
                    if mapped.retryable and retry < options.max_retries:
                        retrying = True
                        self._sleep(min(0.25 * (2**retry), 1.0))
                        continue
                    raise mapped from None
                finally:
                    if called:
                        self.attempts.append(ProviderAttempt(prompt_name=prompt_name, status="cancelled" if control and control.requested else "succeeded" if succeeded else "failed",
                            latency_ms=max(0, round((self._clock()-attempt_started)*1000)), provider_retry_count=retry,
                            **usage.model_dump()))
                    if not retrying or (control and control.requested):
                        detach()
                        if owned_client and callable(getattr(client, "close", None)):
                            try:
                                client.close()
                            except Exception:
                                pass  # Cleanup failure is never raw provider output.

    def stream_structured(self, messages, response_model, options, *, prompt_name, prompt_version):
        if options.thinking_enabled:
            raise LLMConfigurationError("Orange 流式答复必须关闭 thinking。")
        client = self._client or self._create_client(options)
        started = self._clock()
        stream = None
        control = getattr(self, "_turn_control", None)
        owned_client = self._client is None
        detach_client = control.attach_close(getattr(client, "close", None)) if control and owned_client else lambda: None
        detach_stream = lambda: None
        called, succeeded, usage = False, False, LLMUsage()
        metrics = StreamMetrics()
        projection = VisibleJSONStream()
        self.last_stream_metrics = metrics
        with diagnostic_span(DC.PROVIDER, "provider_call") as statistics:
            try:
                if control:
                    control.checkpoint()
                called = True
                stream = client.chat.completions.create(
                    model=options.model,
                    messages=[message.model_dump(mode="json") for message in messages],
                    response_format={"type": "json_schema", "json_schema": {
                        "name": response_model.__name__, "strict": True,
                        "schema": response_model.model_json_schema()}},
                    temperature=options.temperature, max_tokens=options.max_output_tokens,
                    extra_body={"enable_thinking": False},
                    stream=True, stream_options={"include_usage": True},
                )
                if control:
                    detach_stream = control.attach_close(getattr(stream, "close", None))
                    control.checkpoint()
                parts, size, usage, finished = [], 0, LLMUsage(), False
                for chunk in stream:
                    if control:
                        control.checkpoint()
                    if metrics.stream_chunk_count >= MAX_STREAM_CHUNKS:
                        raise ResponseStreamError("invalid_core")
                    metrics = metrics.model_copy(update={"stream_chunk_count": metrics.stream_chunk_count+1})
                    if getattr(chunk, "usage", None) is not None:
                        usage = self._normalize_usage(chunk.usage)
                    for choice in getattr(chunk, "choices", []):
                        if getattr(choice, "index", 0) != 0 or finished:
                            raise ResponseStreamError("transport_incomplete")
                        if getattr(choice.delta, "refusal", None):
                            metrics = metrics.model_copy(update={"provider_finish_category": "refused"})
                            raise ResponseStreamError("invalid_core")
                        # Intentionally never read reasoning_content/reasoning fields.
                        content = getattr(choice.delta, "content", None)
                        if content:
                            size += len(content)
                            if size > MAX_WIRE_CHARACTERS:
                                raise ResponseStreamError("invalid_core")
                            parts.append(content)
                            try:
                                projection.feed(content)
                            except ValueError:
                                metrics = metrics.model_copy(update={"visible_length_bucket": length_bucket(len(projection.visible))})
                                raise ResponseStreamError("invalid_core") from None
                            metrics = metrics.model_copy(update={"visible_length_bucket": length_bucket(len(projection.visible))})
                            self.last_stream_metrics = metrics
                            yield StreamDelta(content)
                        reason = getattr(choice, "finish_reason", None)
                        if reason is not None:
                            metrics = metrics.model_copy(update={"provider_finish_category": {
                                "stop": "normal_stop", "length": "output_limit", "content_filter": "filtered"}.get(reason, "unexpected"),
                                "output_limit_reached": reason == "length"})
                            finished = True
                metrics = metrics.model_copy(update={"transport_completed": True})
                if control:
                    control.checkpoint()
                if not finished:
                    metrics = metrics.model_copy(update={"provider_finish_category": "missing"})
                    raise ResponseStreamError("transport_incomplete")
                if metrics.provider_finish_category != "normal_stop":
                    raise ResponseStreamError("output_limit" if metrics.output_limit_reached else "transport_incomplete")
                if response_model is ResponseEnvelope:
                    try:
                        data, envelope, optional, tail = finalize_wire("".join(parts))
                    except ValueError:
                        raise ResponseStreamError("invalid_core") from None
                    metrics = metrics.model_copy(update={"envelope_complete": envelope, "core_valid": True,
                        "optional_metadata_valid": optional, "degraded_optional_metadata": not optional,
                        "metadata_tail_present": tail})
                else:
                    data = response_model.model_validate_json("".join(parts))
                response = StructuredLLMResponse(
                    data=data, provider=self.name, model=options.model, usage=usage,
                    latency_ms=max(0, round((self._clock() - started) * 1000)),
                    prompt_name=prompt_name, prompt_version=prompt_version,
                    thinking_enabled=False, retry_count=0,
                )
                statistics.update(counts={"provider_call_count": 1, **{
                    key: getattr(usage, key) for key in ("input_tokens", "output_tokens", "total_tokens")
                    if getattr(usage, key) is not None}},
                    safe_metadata={"provider": "qwen", "model_id": options.model, "retry_count": 0})
                # Close BEFORE completion; cleanup alone cannot erase a validated answer.
                try:
                    stream.close()
                except Exception:
                    metrics = metrics.model_copy(update={"close_failed": True})
                stream = None
                succeeded = True
                self.last_stream_metrics = metrics
                yield StreamComplete(response, metrics)
            except Exception as exc:
                if control and control.requested:
                    metrics = metrics.model_copy(update={"provider_finish_category": "cancelled", "cancellation_requested": True})
                    raise CancellationRequested() from None
                if metrics.provider_finish_category == "pending":
                    metrics = metrics.model_copy(update={"provider_finish_category": "interrupted"})
                raise self._map_exception(exc, validation_stage=response_model.__name__) from None
            finally:
                try:
                    if stream is not None:
                        try:
                            stream.close()
                        except Exception:
                            metrics = metrics.model_copy(update={"close_failed": True})
                finally:
                    detach_stream()
                    detach_client()
                    if owned_client and callable(getattr(client, "close", None)):
                        try:
                            client.close()
                        except Exception:
                            metrics = metrics.model_copy(update={"close_failed": True})
                    self.last_stream_metrics = metrics
                    if called:
                        self.attempts.append(ProviderAttempt(prompt_name=prompt_name, status="cancelled" if control and control.requested else "succeeded" if succeeded else "failed",
                            latency_ms=max(0, round((self._clock()-started)*1000)), provider_retry_count=0,
                            **usage.model_dump()))


class VisibleJSONStream:
    """Incremental JSON-string projection, not simulated typing of a full answer.

    Only first-property visible_response may be projected. Partial unicode escape
    sequences are held until complete; every other JSON property stays invisible.
    """

    def __init__(self):
        self.buffer = ""
        self.visible = ""
        self.position = 0
        self.started = False
        self.text_complete = False
        self.high_surrogate = None

    def feed(self, delta: str) -> str:
        import json
        import re
        self.buffer += delta
        if len(self.buffer) > MAX_WIRE_CHARACTERS:
            raise ValueError("Stream exceeds budget.")
        if not self.started:
            start = re.match(r'^\s*\{\s*"visible_response"\s*:\s*"', self.buffer)
            if start is not None:
                self.position, self.started = start.end(), True
        if not self.started:
            # Wait only while the header is incomplete, never expose another key.
            header = re.sub(r'\s+', '', self.buffer)
            if len(self.buffer) > MAX_JSON_HEADER_CHARACTERS or not '{"visible_response":"'.startswith(header):
                raise ValueError("Visible response must be first.")
            return ""
        if self.text_complete:
            return ""
        fresh = []
        while self.position < len(self.buffer):
            char = self.buffer[self.position]
            if char == '"':
                if self.high_surrogate is not None:
                    raise ValueError("Unpaired Unicode surrogate.")
                self.text_complete = True
                self.position += 1
                break
            if char == "\\":
                width = 6 if self.buffer[self.position:self.position+2] == "\\u" else 2
                if self.position + width > len(self.buffer):
                    break
                char = json.loads('"' + self.buffer[self.position:self.position+width] + '"')
            else:
                width = 1
                if ord(char) < 32:
                    raise ValueError("Unescaped JSON control character.")
            self.position += width
            code = ord(char)
            if self.high_surrogate is not None:
                if not 0xDC00 <= code <= 0xDFFF:
                    raise ValueError("Unpaired Unicode surrogate.")
                char = chr(0x10000 + ((self.high_surrogate-0xD800)<<10) + code-0xDC00)
                self.high_surrogate = None
            elif 0xD800 <= code <= 0xDBFF:
                self.high_surrogate = code
                continue
            elif 0xDC00 <= code <= 0xDFFF:
                raise ValueError("Unpaired Unicode surrogate.")
            fresh.append(char)
        text = "".join(fresh)
        self.visible += text
        if len(self.visible) > HARD_VISIBLE_CHARACTERS:
            raise ValueError("Visible response exceeds budget.")
        return text
