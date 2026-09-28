"""Small, credential-safe provider exception hierarchy."""

from typing import Optional


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
