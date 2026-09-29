"""Small, credential-safe provider exception hierarchy."""

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple, Union

from pydantic import ValidationError


LocationPart = Union[str, int]


@dataclass(frozen=True)
class SafeValidationDiagnostic:
    """Structural validation detail that deliberately excludes raw input values."""

    stage: str
    error_code: str
    message: str
    loc: Tuple[LocationPart, ...] = ()
    error_type: Optional[str] = None
    identifier: Optional[str] = None

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "stage": self.stage,
            "error_code": self.error_code,
            "message": self.message,
        }
        if self.loc:
            payload["loc"] = ".".join(str(part) for part in self.loc)
        if self.error_type:
            payload["type"] = self.error_type
        if self.identifier:
            payload["identifier"] = self.identifier
        return payload


class LLMError(RuntimeError):
    """所有 provider 领域错误的基类。"""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        status_code: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class LLMConfigurationError(LLMError):
    """本地配置缺失或无效。"""


class LLMAuthenticationError(LLMError):
    """认证失败；错误文本不包含凭据。"""


class LLMTimeoutError(LLMError):
    """请求超时，可在有限次数内重试。"""

    def __init__(self, message: str = "Qwen 请求超时。") -> None:
        super().__init__(message, retryable=True)


class LLMRateLimitError(LLMError):
    """服务限流，可在有限次数内重试。"""

    def __init__(self, message: str = "Qwen 服务暂时限流。") -> None:
        super().__init__(message, retryable=True, status_code=429)


class LLMProviderError(LLMError):
    """其他 transport/provider 错误。"""


class LLMStructuredOutputError(LLMError):
    """严格结构化输出为空、无效或引用未知证据。"""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "STRUCTURED_OUTPUT_INVALID",
        stage: str = "structured_output",
        loc: Sequence[LocationPart] = (),
        error_type: Optional[str] = None,
        identifier: Optional[str] = None,
        diagnostics: Sequence[SafeValidationDiagnostic] = (),
    ) -> None:
        super().__init__(message, retryable=False)
        self.error_code = error_code
        self.stage = stage
        self.diagnostics = tuple(diagnostics) or (
            SafeValidationDiagnostic(
                stage=stage,
                error_code=error_code,
                message=message,
                loc=tuple(loc),
                error_type=error_type,
                identifier=identifier,
            ),
        )

    @classmethod
    def from_pydantic(
        cls,
        *,
        stage: str,
        error: ValidationError,
    ) -> "LLMStructuredOutputError":
        diagnostics = []
        for item in error.errors(
            include_url=False,
            include_context=False,
            include_input=False,
        ):
            error_type = str(item.get("type", "validation_error"))
            diagnostics.append(
                SafeValidationDiagnostic(
                    stage=stage,
                    error_code=_pydantic_error_code(error_type),
                    message=_safe_pydantic_message(error_type),
                    loc=tuple(item.get("loc", ())),
                    error_type=error_type,
                )
            )
        return cls(
            f"{stage} 未通过 Pydantic 验证。",
            error_code="PYDANTIC_VALIDATION_ERROR",
            stage=stage,
            diagnostics=diagnostics,
        )

    def safe_diagnostics(self) -> list[dict[str, object]]:
        """Return structural metadata only; never include raw model input."""

        return [item.as_dict() for item in self.diagnostics]


def _pydantic_error_code(error_type: str) -> str:
    if error_type == "duplicate_candidate_id":
        return "DUPLICATE_CANDIDATE_ID"
    if error_type == "duplicate_action_id":
        return "DUPLICATE_ACTION_ID"
    if error_type == "duplicate_identifier":
        return "DUPLICATE_IDENTIFIER"
    if error_type == "unknown_signal_reference_required":
        return "UNKNOWN_REQUIRES_SIGNAL_REFERENCE"
    if error_type == "unknown_profile_signal_id":
        return "UNKNOWN_PROFILE_SIGNAL_ID"
    if error_type == "unknown_job_signal_id":
        return "UNKNOWN_JOB_SIGNAL_ID"
    return "PYDANTIC_FIELD_INVALID"


def _safe_pydantic_message(error_type: str) -> str:
    messages = {
        "missing": "Required field is missing.",
        "enum": "Input should be a valid serialized enum value.",
        "extra_forbidden": "Unexpected field is not permitted.",
        "list_type": "Input should be a valid list.",
        "too_short": "List does not meet the minimum length.",
        "union_tag_invalid": "Input should use a supported relation discriminator.",
        "string_type": "Input should be a valid string.",
        "string_too_short": "String does not meet the minimum length.",
        "greater_than_equal": "Number is below the allowed minimum.",
        "less_than_equal": "Number is above the allowed maximum.",
        "duplicate_candidate_id": "Candidate IDs must be unique.",
        "duplicate_action_id": "Action IDs must be unique.",
        "duplicate_identifier": "IDs in this field must be unique.",
        "unknown_signal_reference_required": "Unknown requires at least one signal side.",
        "unknown_profile_signal_id": "Profile signal ID is outside the request scope.",
        "unknown_job_signal_id": "Job signal ID is outside the request scope.",
    }
    return messages.get(error_type, "Value failed a schema validation rule.")
