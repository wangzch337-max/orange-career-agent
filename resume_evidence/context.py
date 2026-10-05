"""Deterministic privacy minimization. Detection is conservative, not a PII guarantee."""

from dataclasses import dataclass, field
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlsplit

from resume_intake.models import ParsedResumeDocument
from resume_intake.policy import MAX_BLOCKS, MAX_TEXT_CHARACTERS
from resume_evidence.policy import MAX_CONTEXT_CHARS, MAX_CONTEXT_JSON_CHARS, MAX_CONTEXT_BLOCKS, MAX_BLOCK_CHARS

_EMAIL = re.compile(r"[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}", re.UNICODE)
_PHONE_LABEL = re.compile(r"(?im)(?<!\w)(?:phone|mobile|tel(?:ephone)?|contact number|电话|電話|手機|手机|联系电话)[ \t]*[:：]?[ \t]*(\+?\d[\d ().-]{5,}\d)")
_PHONE = re.compile(r"(?<![\w])(?:\+\d[\d ().-]{7,}\d|1[3-9]\d{9}|\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4})(?![\w])")
_ADDRESS = re.compile(r"(?im)^[ \t]*(?:home address|residential address|住址|家庭住址|居住地址)[ \t]*[:：][^\n]*")
_ID = re.compile(r"(?im)(?:passport(?: number| no\.?)?|national id|personal id|hkid|身份证(?:号码)?|身份證(?:號碼)?|護照(?:號碼)?|护照(?:号码)?)[ \t]*[:：][ \t]*(?:[A-Z][A-Z0-9]{5,17}(?:\([0-9A-Z]\))?|\d{6,18})")
_URL = re.compile(r"(?:https?://|file://|ftp://|www\.)[^\s<>\"']+", re.I)
_PATH = re.compile(r"(?<!\w)(?:/(?:Users|home|private|tmp)/|[A-Za-z]:[\\/])[^\s<>\"']+")
_NAME_LABEL = re.compile(r"(?im)^[ \t]*(?:candidate name|full name|姓名)[ \t]*[:：][^\n]*")
_INTENT = re.compile(r"(?i)career goal|career objective|seeking|aim to|interested in|prefer|求职意向|求職意向|职业目标|職業目標|希望|意向")


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def minimize_text(text: str) -> tuple[str, bool]:
    original = text
    text = _ADDRESS.sub("[home address removed]", text)
    text = _NAME_LABEL.sub("[contact name removed]", text)
    text = _ID.sub("[personal identifier removed]", text)
    text = _EMAIL.sub("[email removed]", text)
    text = _PHONE_LABEL.sub("[phone removed]", text)
    def replace_phone(match):
        prefix = text[max(text.rfind("\n", 0, match.start()) + 1, match.start() - 60):match.start()]
        if re.search(r"revenue|profit|turnover|sales|income|budget|USD|HKD|EUR|收入|营收|營收|销售|銷售|预算|預算|[$€¥]", prefix, re.I):
            return match.group()  # A clearly labelled business metric is not contact.
        return "[phone removed]"
    text = _PHONE.sub(replace_phone, text)
    def replace_url(match):
        url = match.group().casefold()
        host = urlsplit("https://" + url if url.startswith("www.") else url).hostname or ""
        prefix = text[text.rfind("\n", 0, match.start()) + 1:match.start()]
        professional = (any(host == domain or host.endswith("." + domain) for domain in ("linkedin.com", "github.com", "behance.net", "dribbble.com")) or
                        bool(re.search(r"portfolio|professional profile|作品集|专业主页|專業主頁", prefix, re.I)))
        return "[professional profile present]" if professional else "[URL removed]"
    text = _URL.sub(replace_url, text)
    text = _PATH.sub("[local path removed]", text)
    kept = []
    for line in text.splitlines():
        remainder = re.sub(r"\[[^\]]* removed\]", "", line).strip(" :：|·,-")
        if not remainder or re.fullmatch(r"(?:email|e-mail|phone|mobile|tel|contact|passport|姓名|电话|手机)", remainder, re.I):
            continue
        kept.append(line)
    text = "\n".join(kept)
    return text.strip(), text != original


def validate_document(document: ParsedResumeDocument) -> None:
    if not isinstance(document, ParsedResumeDocument) or not document.blocks or len(document.blocks) > MAX_BLOCKS:
        raise ValueError("CONTEXT_BUILD_FAILED")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", document.source_id) or document.source_type not in ("pdf", "docx"):
        raise ValueError("CONTEXT_BUILD_FAILED")
    ids = set()
    characters = 0
    for block in document.blocks:
        if (block.source_id != document.source_id or block.source_type != document.source_type or
                not re.fullmatch(re.escape(document.source_id) + r":block:[1-9][0-9]{0,4}", block.block_id) or block.block_id in ids):
            raise ValueError("CONTEXT_BUILD_FAILED")
        ids.add(block.block_id)
        characters += len(block.text)
    if characters > MAX_TEXT_CHARACTERS:
        raise ValueError("CONTEXT_BUILD_FAILED")


def content_fingerprint(document: ParsedResumeDocument) -> str:
    validate_document(document)
    digest = hashlib.sha256()
    # Length-prefixed encodings prevent ambiguous concatenation; no filename.
    for value in (document.source_id, document.source_type,
                  *(value for block in document.blocks for value in (block.block_id, block.location, str(block.page_number), block.text))):
        data = value.encode("utf-8")
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


@dataclass(frozen=True)
class ProviderResumeBlock:
    block_id: str
    text: str = field(repr=False)
    truncated: bool = False


@dataclass(frozen=True)
class ProviderResumeContext:
    source_id: str
    fingerprint: str = field(repr=False)
    blocks: tuple[ProviderResumeBlock, ...] = field(repr=False)
    input_block_count: int
    redacted_block_count: int
    partial: bool

    def payload(self) -> dict:
        return {"source_id": self.source_id, "partial": self.partial,
                "blocks": [{"block_id": block.block_id, "text": block.text} for block in self.blocks]}

    def serialized(self) -> str:
        return json.dumps(self.payload(), ensure_ascii=False, separators=(",", ":"))


class ProviderResumeContextBuilder:
    def build(self, document: ParsedResumeDocument) -> ProviderResumeContext:
        fingerprint = content_fingerprint(document)
        selected, chars, redacted = [], 0, 0
        partial = False
        for block in document.blocks:
            cleaned, changed = minimize_text(block.text)
            redacted += int(changed)
            meaningful = re.sub(r"\[[^\]]* removed\]", "", cleaned).strip()
            if not meaningful:
                partial = True
                continue
            if len(selected) >= MAX_CONTEXT_BLOCKS or chars >= MAX_CONTEXT_CHARS:
                partial = True
                continue
            text = cleaned[:min(MAX_BLOCK_CHARS, MAX_CONTEXT_CHARS - chars)]
            candidate = ProviderResumeBlock(block.block_id, text, len(text) < len(cleaned))
            provisional = ProviderResumeContext(document.source_id, fingerprint, tuple([*selected, candidate]), len(document.blocks), redacted, False)
            if len(provisional.serialized()) > MAX_CONTEXT_JSON_CHARS:
                partial = True
                continue
            selected.append(candidate)
            chars += len(text)
            partial |= candidate.truncated
        if not selected:
            raise ValueError("CONTEXT_BUILD_FAILED")
        return ProviderResumeContext(document.source_id, fingerprint, tuple(selected), len(document.blocks), redacted, partial)


def validate_bound_context(context: ProviderResumeContext, document: ParsedResumeDocument) -> None:
    """Bind the selected, sanitized prefixes to the actual authorized document."""
    if context.source_id != document.source_id or context.fingerprint != content_fingerprint(document):
        raise ValueError("CONTEXT_BUILD_FAILED")
    actual = {block.block_id: block for block in document.blocks}
    if (not context.blocks or len(context.blocks) > MAX_CONTEXT_BLOCKS or
            context.input_block_count != len(actual) or len({block.block_id for block in context.blocks}) != len(context.blocks) or
            sum(len(block.text) for block in context.blocks) > MAX_CONTEXT_CHARS or
            len(context.serialized()) > MAX_CONTEXT_JSON_CHARS):
        raise ValueError("CONTEXT_BUILD_FAILED")
    partial = len(context.blocks) != len(actual)
    for block in context.blocks:
        if block.block_id not in actual or not 0 < len(block.text) <= MAX_BLOCK_CHARS:
            raise ValueError("CONTEXT_BUILD_FAILED")
        cleaned, _ = minimize_text(actual[block.block_id].text)
        if block.text != cleaned[:len(block.text)] or block.truncated != (len(block.text) < len(cleaned)):
            raise ValueError("CONTEXT_BUILD_FAILED")
        partial |= block.truncated
    if partial and not context.partial:
        raise ValueError("CONTEXT_BUILD_FAILED")


def explicit_intent(text: str) -> bool:
    return bool(_INTENT.search(text))
