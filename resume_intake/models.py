"""Source blocks are not ResumeEvidence, career preferences or Profile fields."""

from dataclasses import dataclass, field
from enum import Enum


class ResumeParseStatus(str, Enum):
    SELECTED = "selected"
    READING = "reading"
    READY = "ready"
    UNSUPPORTED = "unsupported"
    TOO_LARGE = "too_large"
    ENCRYPTED = "encrypted"
    SCAN_OR_IMAGE_ONLY = "scan_or_image_only"
    PARSE_FAILED = "parse_failed"


@dataclass(frozen=True)
class UploadedResume:
    source_id: str
    display_name: str = field(repr=False)
    file_type: str
    size_bytes: int
    data: bytes = field(repr=False)


@dataclass(frozen=True)
class ParsedResumeBlock:
    block_id: str
    source_id: str
    source_type: str
    location: str
    kind: str
    text: str = field(repr=False)
    page_number: int | None = None


@dataclass(frozen=True)
class ParsedResumeDocument:
    source_id: str
    source_type: str
    blocks: tuple[ParsedResumeBlock, ...] = field(repr=False)
    page_count: int | None = None


@dataclass(frozen=True)
class ResumeParseResult:
    status: ResumeParseStatus
    error_code: str | None = None
    document: ParsedResumeDocument | None = field(default=None, repr=False)
    elapsed_ms: float = 0


@dataclass(frozen=True)
class ResumeEvent:
    """Closed structural event: deliberately no filename, IDs or text slots."""

    event: str
    file_type: str
    size_bytes: int
    status: ResumeParseStatus
    page_count: int = 0
    block_count: int = 0
    elapsed_ms: float = 0
