"""Bounded session-only parse metadata; never retain rejected input or error text."""

from dataclasses import asdict, dataclass
import hashlib
import json

from pydantic import ValidationError

from clarification.policy import PROMPT_NAME, PROMPT_VERSION
from providers.errors import LLMStructuredOutputError

MAX_PARSE_ERRORS = 8
_FIELDS = frozenset({"should_ask", "selected_need_id", "question", "suggested_replies",
                     "reason_summary", "source_refs", "confidence"})
_CONSTRAINTS = {
    "missing": "required", "literal_error": "literal_membership", "enum": "enum_membership",
    "extra_forbidden": "extra_field", "bool_type": "type", "bool_parsing": "type",
    "string_type": "type", "tuple_type": "type", "list_type": "type",
    "model_type": "type", "model_attributes_type": "type", "dict_type": "type",
    "string_too_short": "length", "string_too_long": "length",
    "too_short": "cardinality", "too_long": "cardinality",
    "string_pattern_mismatch": "pattern", "value_error": "model_invariant",
    "json_invalid": "json_syntax", "json_type": "type",
}


def _path(location):
    # Extra keys and union labels can be user/provider text, not schema names.
    # Only the seven known root fields and array indices are safe to expose.
    parts = []
    for index, part in enumerate(location[:4]):
        if index == 0 and isinstance(part, str) and part in _FIELDS:
            parts.append(part)
        elif type(part) is int and 0 <= part <= 999_999:
            parts.append(part)
        else:
            parts.append("unknown_field")
    return tuple(parts)


@dataclass(frozen=True)
class ParseIssue:
    field_path: tuple[str | int, ...]
    error_type: str
    constraint_type: str
    level: str


@dataclass(frozen=True)
class ClarificationParseFailure:
    stage: str
    schema_version: str
    parser_status: str
    error_count: int
    truncated: bool
    errors: tuple[ParseIssue, ...]
    fingerprint: str

    def as_dict(self):
        """Export only the already allowlisted structural projection."""
        return asdict(self)


def parse_failure(error: ValidationError | LLMStructuredOutputError) -> ClarificationParseFailure:
    """Discard messages, ctx, inputs, IDs, stages and arbitrary location strings."""
    if isinstance(error, ValidationError):
        raw = error.errors(include_url=False, include_context=False, include_input=False)
        entries = [(item.get("loc", ()), item.get("type")) for item in raw]
    else:
        entries = [(item.loc, item.error_type) for item in error.diagnostics]
    issues = []
    for location, kind in entries[:MAX_PARSE_ERRORS]:
        path = _path(location)
        safe_type = kind if type(kind) is str and kind in _CONSTRAINTS else "validation_error"
        issues.append(ParseIssue(path, safe_type, _CONSTRAINTS.get(safe_type, "schema"),
                                 "root" if not path else "top_level" if len(path) == 1 else "nested"))
    version = f"{PROMPT_NAME}@{PROMPT_VERSION}"
    structural = {"stage": "clarification_parse", "schema_version": version,
                  "errors": [asdict(issue) for issue in issues]}
    fingerprint = hashlib.sha256(json.dumps(structural, sort_keys=True).encode()).hexdigest()[:32]
    return ClarificationParseFailure("clarification_parse", version, "rejected",
        min(len(entries), 10_000), len(entries) > MAX_PARSE_ERRORS, tuple(issues), fingerprint)
