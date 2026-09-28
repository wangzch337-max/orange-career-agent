"""Provider boundary models and the deliberately small Phase 2 extraction schema."""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Dict, Generic, List, Literal, Optional, Sequence, Set, TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from providers.errors import LLMConfigurationError, LLMStructuredOutputError


class ProviderModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"


class LLMMessage(ProviderModel):
    role: MessageRole
    content: str = Field(min_length=1)


class GenerationOptions(ProviderModel):
    model: str = "qwen3.8-flash"
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=800, ge=1, le=4096)
    thinking_enabled: bool = False
    timeout_seconds: float = Field(default=30.0, gt=0.0, le=120.0)
    max_retries: int = Field(default=2, ge=0, le=3)


class LLMUsage(ProviderModel):
    input_tokens: Optional[int] = Field(default=None, ge=0)
    output_tokens: Optional[int] = Field(default=None, ge=0)
    total_tokens: Optional[int] = Field(default=None, ge=0)


class RequestStatus(str, Enum):
    SUCCEEDED = "succeeded"


StructuredT = TypeVar("StructuredT", bound=BaseModel)


class StructuredLLMResponse(ProviderModel, Generic[StructuredT]):
    data: StructuredT
    provider: str
    model: str
    usage: LLMUsage = Field(default_factory=LLMUsage)
    latency_ms: int = Field(ge=0)
    prompt_name: str
    prompt_version: str
    request_status: RequestStatus = RequestStatus.SUCCEEDED
    request_id: Optional[str] = None
    thinking_enabled: bool = False
    retry_count: int = Field(default=0, ge=0)

    def safe_metadata(self) -> Dict[str, object]:
        """Return observability fields that contain no prompt or credentials."""

        return {
            "provider": self.provider,
            "model": self.model,
            "prompt_name": self.prompt_name,
            "prompt_version": self.prompt_version,
            "thinking_enabled": self.thinking_enabled,
            "input_tokens": self.usage.input_tokens,
            "output_tokens": self.usage.output_tokens,
            "total_tokens": self.usage.total_tokens,
            "latency_ms": self.latency_ms,
            "status": self.request_status.value,
            "retry_count": self.retry_count,
        }


class SourceEvidence(ProviderModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class ProfileSignalInput(ProviderModel):
    source_evidence: List[SourceEvidence] = Field(min_length=1)

    @model_validator(mode="after")
    def ensure_unique_ids(self) -> "ProfileSignalInput":
        ids = [item.id for item in self.source_evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("Source evidence IDs 必须唯一。")
        return self


class ExtractedSignal(ProviderModel):
    label: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: List[str] = Field(min_length=1)


class ExtractedSkill(ExtractedSignal):
    pass


class ExtractedInterest(ExtractedSignal):
    pass


class ExtractedGoal(ExtractedSignal):
    pass


class ProfileSignalExtraction(ProviderModel):
    """Phase 2 semantic extraction output; deliberately not a UserProfile."""

    candidate_skills: List[ExtractedSkill] = Field(default_factory=list)
    interest_signals: List[ExtractedInterest] = Field(default_factory=list)
    goal_signals: List[ExtractedGoal] = Field(default_factory=list)

    def validate_evidence_ids(
        self,
        source_evidence: Sequence[SourceEvidence],
    ) -> "ProfileSignalExtraction":
        allowed_ids: Set[str] = {item.id for item in source_evidence}
        returned_ids = {
            evidence_id
            for signal in [
                *self.candidate_skills,
                *self.interest_signals,
                *self.goal_signals,
            ]
            for evidence_id in signal.evidence_ids
        }
        unknown_ids = returned_ids - allowed_ids
        if unknown_ids:
            raise LLMStructuredOutputError(
                f"结构化输出引用了未知 evidence IDs: {sorted(unknown_ids)}"
            )
        return self


class LLMSettings(ProviderModel):
    """Secrets remain wrapped; only safe_summary may enter observability."""

    provider: str = "qwen"
    model: str = "qwen3.8-flash"
    api_key: Optional[SecretStr] = None
    base_url: Optional[SecretStr] = None

    def require_live_qwen(self) -> "LLMSettings":
        if self.provider != "qwen":
            raise LLMConfigurationError("Phase 2 live provider 必须为 qwen。")
        if self.model != "qwen3.8-flash":
            raise LLMConfigurationError("Phase 2 live model 必须为 qwen3.8-flash。")
        if self.api_key is None or not self.api_key.get_secret_value().strip():
            raise LLMConfigurationError("本地 Qwen API key 尚未配置。")
        if self.base_url is None or not self.base_url.get_secret_value().strip():
            raise LLMConfigurationError("本地 Qwen base URL 尚未配置。")
        if not self.base_url.get_secret_value().startswith("https://"):
            raise LLMConfigurationError("Qwen base URL 必须使用 HTTPS。")
        return self

    def safe_summary(self) -> Dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "api_key_configured": bool(
                self.api_key and self.api_key.get_secret_value().strip()
            ),
            "base_url_configured": bool(
                self.base_url and self.base_url.get_secret_value().strip()
            ),
        }


def load_llm_settings(repository_root: Path) -> LLMSettings:
    """Load only repository-local .env.local; shell environment wins."""

    local_env = repository_root / ".env.local"
    if local_env.is_file():
        load_dotenv(dotenv_path=local_env, override=False)
    return LLMSettings(
        provider=os.getenv("ORANGE_LLM_PROVIDER", "qwen"),
        model=os.getenv("ORANGE_LLM_MODEL", "qwen3.8-flash"),
        api_key=SecretStr(value) if (value := os.getenv("DASHSCOPE_API_KEY")) else None,
        base_url=SecretStr(value) if (value := os.getenv("DASHSCOPE_BASE_URL")) else None,
    )
