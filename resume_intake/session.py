"""One ephemeral attachment per active conversation; no canonical store access."""

from dataclasses import dataclass, field
from uuid import uuid4
from typing import Callable

from resume_intake.models import ResumeEvent, ResumeParseResult, ResumeParseStatus, UploadedResume
from resume_intake.parser import parse_resume
from resume_intake.policy import MAX_EVENTS, MAX_UPLOAD_BYTES, display_filename, file_type


@dataclass
class ResumeSessionState:
    owner_scope_id: str = field(repr=False)
    thread_id: str | None = field(default=None, repr=False)
    display_name: str = field(default="", repr=False)
    file_type: str = "unknown"
    size_bytes: int = 0
    result: ResumeParseResult | None = field(default=None, repr=False)
    pending: UploadedResume | None = field(default=None, repr=False)
    events: list[ResumeEvent] = field(default_factory=list)
    revision: int = 0
    on_clear: Callable[[], None] | None = field(default=None, repr=False)

    def _event(self, name: str, status: ResumeParseStatus) -> None:
        document = self.result.document if self.result else None
        self.events.append(ResumeEvent(
            name, self.file_type, min(self.size_bytes, MAX_UPLOAD_BYTES + 1), status,
            document.page_count or 0 if document else 0, len(document.blocks) if document else 0,
            self.result.elapsed_ms if self.result else 0,
        ))
        del self.events[:-MAX_EVENTS]

    def bind(self, owner_scope_id: str, thread_id: str) -> None:
        if owner_scope_id != self.owner_scope_id:
            raise ValueError("RESUME_SCOPE_MISMATCH")
        if thread_id != self.thread_id:
            self.clear()
            self.thread_id = thread_id

    def select(self, owner_scope_id: str, thread_id: str, name: str, data: bytes) -> None:
        if owner_scope_id != self.owner_scope_id or thread_id != self.thread_id:
            raise ValueError("RESUME_SCOPE_MISMATCH")
        self.clear()
        self.display_name, self.file_type, self.size_bytes = display_filename(name), file_type(name), len(data)
        self.pending = UploadedResume(str(uuid4()), self.display_name, self.file_type, self.size_bytes, data)
        self.result = ResumeParseResult(ResumeParseStatus.SELECTED)
        self._event("resume_upload_selected", self.result.status)

    def parse_pending(self) -> ResumeParseResult | None:
        if self.pending is None:
            return self.result
        upload, revision = self.pending, self.revision
        self.result = ResumeParseResult(ResumeParseStatus.READING)
        self._event("resume_parse_started", self.result.status)
        try:
            parsed = parse_resume(upload)
            if revision != self.revision:
                return None  # Cleared/switch/deleted state cannot be reinstalled.
            self.result = parsed
            self._event("resume_parse_completed" if parsed.status == ResumeParseStatus.READY else "resume_parse_failed", parsed.status)
            return parsed
        finally:
            if revision == self.revision:
                self.pending = None
                self._event("resume_ephemeral_cleanup_completed", self.result.status)

    def clear(self) -> None:
        self.revision += 1
        self.pending = None
        self.result = None
        self.display_name, self.file_type, self.size_bytes = "", "unknown", 0
        self.events.clear()
        if self.on_clear is not None:
            self.on_clear()
