"""Document-bound consent and candidates, ephemeral and independent of chat consent."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from time import perf_counter
from typing import Callable, Literal

from providers.base import LLMProvider
from providers.errors import LLMStructuredOutputError
from resume_intake.models import ResumeParseStatus
from resume_evidence.context import ProviderResumeContextBuilder, content_fingerprint, validate_bound_context
from resume_evidence.models import ResumeEvidenceBundle
from resume_evidence.policy import CONSENT_VERSION, MAX_ANALYSIS_EVENTS
from resume_evidence.service import ResumeEvidenceExtractor, ResumeUsage
from resume_evidence.validation import ResumeValidationError


class ResumeAnalysisStatus(str, Enum):
    CONSENT_REQUIRED = "CONSENT_REQUIRED"
    ANALYZING = "ANALYZING"
    READY = "READY"
    CONTEXT_BUILD_FAILED = "CONTEXT_BUILD_FAILED"
    PROVIDER_FAILED = "PROVIDER_FAILED"
    INVALID_STRUCTURED_OUTPUT = "INVALID_STRUCTURED_OUTPUT"
    INVALID_SOURCE_REFERENCE = "INVALID_SOURCE_REFERENCE"
    EVIDENCE_VALIDATION_FAILED = "EVIDENCE_VALIDATION_FAILED"


@dataclass(frozen=True)
class ResumeConsent:
    owner_scope_id: str = field(repr=False)
    thread_id: str = field(repr=False)
    source_id: str
    fingerprint: str = field(repr=False)
    version: str = CONSENT_VERSION


@dataclass(frozen=True)
class ResumeAnalysisEvent:
    event: Literal["resume_ai_consent_granted", "resume_ai_consent_revoked", "resume_context_built",
                   "resume_analysis_started", "resume_analysis_completed", "resume_analysis_failed",
                   "resume_evidence_validated"]
    status: ResumeAnalysisStatus
    source_id: str | None = None
    input_block_count: int = 0
    context_chars: int = 0
    evidence_count: int = 0
    category_counts: tuple[tuple[str, int], ...] = ()
    partial: bool = False
    latency_ms: int = 0


def _qwen_provider() -> LLMProvider:
    # Lazy existing transport, only after separate consent and explicit analysis.
    from providers.models import load_llm_settings
    from providers.qwen import QwenProvider
    return QwenProvider.from_settings(load_llm_settings(Path(__file__).resolve().parents[1]))


class ResumeAnalysisSession:
    def __init__(self, owner_scope_id: str, intake, *, provider_factory: Callable[[], LLMProvider] | None = None):
        self.owner_scope_id = owner_scope_id
        self.intake = intake
        self.provider_factory = provider_factory or _qwen_provider
        self.builder = ProviderResumeContextBuilder()
        self.extractor = ResumeEvidenceExtractor()
        self.generation = 0
        self.consent: ResumeConsent | None = None
        self.bundle: ResumeEvidenceBundle | None = None
        self.usage: ResumeUsage | None = None
        self.events: list[ResumeAnalysisEvent] = []
        self.status = ResumeAnalysisStatus.CONSENT_REQUIRED
        self.used = False
        self.on_invalidate: Callable[[], None] | None = None

    def _identity(self) -> ResumeConsent | None:
        state = self.intake
        if (state.owner_scope_id != self.owner_scope_id or not state.thread_id or state.result is None or
                state.result.status != ResumeParseStatus.READY or state.result.document is None):
            return None
        document = state.result.document
        return ResumeConsent(self.owner_scope_id, state.thread_id, document.source_id, content_fingerprint(document))

    def _event(self, name: str, **metadata) -> None:
        self.events.append(ResumeAnalysisEvent(name, self.status,
            self.consent.source_id if self.consent else None, **metadata))
        del self.events[:-MAX_ANALYSIS_EVENTS]

    def invalidate(self) -> None:
        self.generation += 1
        self.consent, self.bundle, self.usage = None, None, None
        self.used = False
        self.status = ResumeAnalysisStatus.CONSENT_REQUIRED
        self.events.clear()
        if self.on_invalidate is not None:
            self.on_invalidate()

    @property
    def has_consent(self) -> bool:
        try:
            valid = self.consent is not None and self.consent == self._identity()
        except Exception:
            valid = False
        if self.consent is not None and not valid:
            self.invalidate()
        return valid

    def grant(self, *, owner_scope_id: str, thread_id: str, source_id: str, fingerprint: str) -> bool:
        try:
            requested = ResumeConsent(owner_scope_id, thread_id, source_id, fingerprint)
            if requested != self._identity():
                return False
        except Exception:
            return False
        self.invalidate()
        self.consent = requested
        self._event("resume_ai_consent_granted")
        return True

    def revoke(self) -> None:
        self.invalidate()
        self._event("resume_ai_consent_revoked")

    def grant_current(self) -> bool:
        """Only the UI's explicit consent action invokes this, never parse/render."""
        try:
            identity = self._identity()
            return identity is not None and self.grant(owner_scope_id=identity.owner_scope_id,
                thread_id=identity.thread_id, source_id=identity.source_id, fingerprint=identity.fingerprint)
        except Exception:
            return False

    def analyze(self) -> ResumeAnalysisStatus:
        if not self.has_consent:
            self.status = ResumeAnalysisStatus.CONSENT_REQUIRED
            return self.status
        if self.used:
            return self.status  # Rerun/double submit never makes a second call.
        self.used = True
        binding, generation = self.consent, self.generation
        self.bundle, self.usage = None, None
        started = perf_counter()
        try:
            context = self.builder.build(self.intake.result.document)
            validate_bound_context(context, self.intake.result.document)
            if context.fingerprint != binding.fingerprint or context.source_id != binding.source_id:
                raise ValueError("CONTEXT_BUILD_FAILED")
        except Exception:
            if generation != self.generation or not self.has_consent or self.consent != binding:
                return self.status
            self.status = ResumeAnalysisStatus.CONTEXT_BUILD_FAILED
            self._event("resume_analysis_failed")
            return self.status
        if generation != self.generation or not self.has_consent or self.consent != binding:
            return self.status
        self._event("resume_context_built", input_block_count=context.input_block_count,
                    context_chars=len(context.serialized()), partial=context.partial)
        try:
            provider = self.provider_factory()
            if generation != self.generation or not self.has_consent or self.consent != binding:
                return self.status
            self.status = ResumeAnalysisStatus.ANALYZING
            self._event("resume_analysis_started")
            extraction, usage = self.extractor.extract(provider, context)
            if generation != self.generation or not self.has_consent or self.consent != binding:
                return self.status  # Late output after replace/revoke cannot publish.
            self.bundle = ResumeEvidenceBundle(**extraction.model_dump(), source_id=binding.source_id,
                content_fingerprint=binding.fingerprint, owner_scope_id=binding.owner_scope_id,
                thread_id=binding.thread_id, context_partial=context.partial)
            self.usage = usage
            self.status = ResumeAnalysisStatus.READY
            counts = tuple(self.bundle.category_counts().items())
            self._event("resume_evidence_validated", evidence_count=len(self.bundle.items), category_counts=counts,
                        partial=context.partial)
            self._event("resume_analysis_completed", evidence_count=len(self.bundle.items),
                        latency_ms=min(120_000, round((perf_counter() - started) * 1000)))
        except Exception as error:
            if generation != self.generation or not self.has_consent:
                return self.status
            if isinstance(error, ResumeValidationError):
                self.status = ResumeAnalysisStatus(error.code)
            elif isinstance(error, LLMStructuredOutputError):
                self.status = ResumeAnalysisStatus.INVALID_STRUCTURED_OUTPUT
            else:
                self.status = ResumeAnalysisStatus.PROVIDER_FAILED
            self.bundle, self.usage = None, None
            self._event("resume_analysis_failed")
        return self.status
