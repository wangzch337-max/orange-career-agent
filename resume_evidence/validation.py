"""Layered, finite lexical grounding; not a semantic judge or verification of truth."""

import json
import re

from resume_evidence.context import ProviderResumeContext, normalize, explicit_intent, minimize_text
from resume_evidence.models import ResumeEvidenceExtraction, WorkExperienceEvidence, ProjectEvidence


class ResumeValidationError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


_QUALIFIER = re.compile(
    r"\b(?:no|none|not|never|without|may|might|observed|shadowed|assisted|supported|participated|contributed)\b"
    r"|\blearning to\b|没有|沒有|未曾|尚未|不具备|不具備|缺乏|无|無|协助|協助|观摩|觀摩"
)
# Closed grammatical forms, not stemming, synonyms or a career ontology.
_VERB_FORMS = (
    ("prepare", "prepared", "preparing"), ("perform", "performed", "performing"),
    ("reconcile", "reconciled", "reconciling"), ("review", "reviewed", "reviewing"),
    ("coordinate", "coordinated", "coordinating"), ("conduct", "conducted", "conducting"),
    ("document", "documented", "documenting"), ("collaborate", "collaborated", "collaborating"),
    ("use", "used", "using"), ("train", "trained", "training"),
    ("map", "mapped", "mapping"), ("develop", "developed", "developing"),
    ("test", "tested", "testing"), ("design", "designed", "designing"),
    ("analyze", "analyzed", "analyzing"), ("process", "processed", "processing"),
)
_VERBS = {form: forms[0] for forms in _VERB_FORMS for form in forms}
_PLURALS = {word + "s": word for word in (
    "account", "paper", "reconciliation", "audit", "client", "record", "team",
    "interview", "tolerance", "report", "review", "event", "colleague", "finding", "schedule",
)}
# A finite quantity boundary, not a universal quantity parser/converter. Units,
# magnitude/currency/sign/comparison markers are part of the fact, not punctuation.
_QUANTITY_PATTERN = (
    r"(?<![0-9a-z_.])(?:[<>]=?|[≤≥])?\s*[+−-]?\s*"
    r"(?:(?:hk\$|us\$|[$€¥£]|usd|hkd|eur|gbp)\s*)?[+−-]?\s*"
    r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
    r"(?:\s*(?:%|[x×](?!\w)|[kmb](?!\w)))?"
    r"(?:\s*(?:years?|months?|days?|hours?|people|persons?|dollars?|percent|percentage points?|年|人|倍)(?!\w))?"
    r"(?:[+−](?!\d))?"
)
_QUANTITY = re.compile(_QUANTITY_PATTERN)
_TOKENS = re.compile(_QUANTITY_PATTERN + r"|\d+(?:\.\d+)?|[^\W\d_]+(?:[-'][^\W\d_]+)*|[%$€¥£<>≤≥+=/−–\-]")
_SEPARATORS = re.compile(r"[\n;；·]+|\s+and\s+")
_LABEL_VALUE = re.compile(
    r"^(?:project ownership|ownership|leadership responsibility|responsibility level|"
    r"proficiency|availability|languages?|certifications?|qualifications?|"
    r"role(?: title)?|organization|degree|major|field|tools?|skills?|education|"
    r"语言|語言|证书|證書|熟练度|熟練度|项目所有权|項目所有權|可用性)\s*:\s*\S"
)
_POST_QUALIFIER = re.compile(
    r"^\s*[:=(]?\s*(?:\b(?:none|no|not|without|only)\b|"
    r"under supervision\b|with (?:supervision|assistance)\b|没有|沒有|无|無)"
)


def _material_span_preserved(line: str, start: int, end: int) -> bool:
    """An extractive substring cannot cut a quantity or label/value/qualifier."""
    for quantity in _QUANTITY.finditer(line):
        # Regex spacing before an atom isn't itself a material symbol.
        left = quantity.start() + len(quantity.group()) - len(quantity.group().lstrip())
        right = quantity.end()
        if max(start, left) < min(end, right) and not (start <= left and end >= right):
            return False
    if _LABEL_VALUE.match(line):
        colon = line.index(":")
        if start < colon and end <= colon:
            return False
    return _POST_QUALIFIER.search(line[end:]) is None


def _lines_normalized(text: str) -> str:
    # Split before normalizing whitespace: a paragraph may contain several facts.
    return "\n".join(normalize(line) for line in text.splitlines())


def _supported(value: str, quote: str) -> bool:
    value = normalize(value)
    # Preserve negation/participation/modal scope; never borrow an isolated word
    # inside a different word, or strip a material qualifier from its predicate.
    pattern = re.escape(value)
    if value[:1].isascii() and value[:1].isalnum():
        pattern = r"(?<![\w-])" + pattern
    if value[-1:].isascii() and value[-1:].isalnum():
        pattern += r"(?![\w-])"
    for line in quote.splitlines():
        line = normalize(line)
        for match in re.finditer(pattern, line):
            if (_QUALIFIER.search(line[:match.start()]) is None and
                    _material_span_preserved(line, match.start(), match.end())):
                return True
    return False


def _tokens(text: str, *, inflect=False) -> tuple[str, ...]:
    tokens = tuple(re.sub(r"\s+", "", token) if _QUANTITY.fullmatch(token) else token
                   for token in _TOKENS.findall(normalize(text)))
    if not inflect:
        return tokens
    result = tuple(_PLURALS.get(token, token) for token in tokens)
    # Only a predicate at the beginning; don't change titles/names or arbitrary
    # interior words such as a product named "Prepared".
    return (_VERBS.get(result[0], result[0]), *result[1:]) if result else ()


def _units(text: str) -> tuple[str, ...]:
    # Split conjunctions only where the right side starts another known action.
    # Object phrases ("CAD and quality checks") keep their internal ordering.
    actions = "|".join(_VERBS)
    return tuple(part.strip() for part in re.split(
        rf"[\n;；·]+|\s+and\s+(?=(?:{actions})\b)", _lines_normalized(text)) if part.strip())


def _variants(text: str, *, inflect: bool, neutral_wrapper: bool) -> set[tuple[str, ...]]:
    result = {_tokens(text)}
    if not inflect or _QUALIFIER.search(normalize(text)):
        return result
    tokens = _tokens(text, inflect=True)
    result.add(tokens)
    # "Experience with <task/tool>" may represent performed/used, never
    # supported/participated -> independently owned, or a proficiency upgrade.
    if neutral_wrapper and tokens and tokens[0] in {"perform", "use"}:
        result.add(tokens[1:])
    # One closed nominal form preserves participants, context and their order:
    # collaborated with X during Y -> X collaboration during Y [work].
    if tokens[:2] == ("collaborate", "with") and "during" in tokens[2:]:
        boundary = tokens.index("during", 2)
        nominal = (*tokens[2:boundary], "collaboration", *tokens[boundary:])
        result.update((nominal, (*nominal, "work")))
    return result


def _normalized_supported(value: str, facts: list[tuple[str, bool]]) -> bool:
    """Exact whole fact phrases, finite inflections, neutral wrapper/juxtaposition.

    No bags of words, overlap threshold, arbitrary stopwords, translation,
    argument reordering, synonyms, causal connectors or inference acceptance.
    """
    value = _lines_normalized(value)
    wrapper = re.match(r"^experience(?: with| in)?\s+", value)
    neutral_wrapper = wrapper is not None
    if wrapper:
        value = value[wrapper.end():]
    if not value or not any(char.isalpha() for char in value):
        return False
    supported = set()
    for fact, inflect in facts:
        for unit in _units(fact):
            # Complete qualified facts may retain surface punctuation changes,
            # but _variants permits no inflection/deletion of their qualifiers.
            supported.update(_variants(unit, inflect=inflect, neutral_wrapper=neutral_wrapper))
    def matches(part):
        raw, canonical = _tokens(part), _tokens(part, inflect=True)
        return bool(raw) and (raw in supported or canonical in supported)
    if matches(value):
        return True
    parts = tuple(part.strip() for part in _SEPARATORS.split(value) if part.strip())
    return len(parts) > 1 and all(matches(part) for part in parts)


def _source_units(text: str) -> tuple[str, ...]:
    """Same finite boundaries as diagnostics; retain source spelling/materials."""
    actions = "|".join(_VERBS)
    return tuple(part.strip() for part in re.split(
        rf"[\n;；·]+|\s+and\s+(?=(?:{actions})\b)", text, flags=re.I) if part.strip())


def _generic_representation(claim, quotes, supported) -> str:
    """Provider text selects facts, never supplies their canonical wording.

    An unsupported selector fails closed, even with a valid source/excerpt.
    This reuses the finite B.1/B.1a diagnostic contract, not paraphrase AI.
    """
    units = tuple(dict.fromkeys(unit for quote in quotes for unit in _source_units(quote) if supported(unit)))
    selected = [unit for unit in units if _supported(claim, unit) and supported(claim)]
    if not selected:
        facts = [(unit, True) for unit in units]
        if not _normalized_supported(claim, facts):
            raise ResumeValidationError("EVIDENCE_VALIDATION_FAILED")
        value = _lines_normalized(claim)
        wrapper = re.match(r"^experience(?: with| in)?\s+", value)
        prefix = wrapper.group() if wrapper else ""
        value = value[wrapper.end():] if wrapper else value
        parts = (value, *[part.strip() for part in _SEPARATORS.split(value) if part.strip()])
        selected = [unit for unit in units if any(
            _normalized_supported(prefix + part, [(unit, True)]) for part in parts)]
    rendered = " · ".join(selected)
    from resume_evidence.policy import MAX_CLAIM_CHARS
    if not rendered or len(rendered) > MAX_CLAIM_CHARS:
        # Never truncate a qualifier/unit to fit the compatibility field.
        raise ResumeValidationError("EVIDENCE_VALIDATION_FAILED")
    return rendered


def validate_extraction(extraction: ResumeEvidenceExtraction, context: ProviderResumeContext) -> ResumeEvidenceExtraction:
    """Admit canonical source-backed facts; discard typed provider description."""
    return _validate(extraction, context, provider_diagnostic=False)


def validate_model_claims(extraction: ResumeEvidenceExtraction, context: ProviderResumeContext) -> ResumeEvidenceExtraction:
    """B.1/B.1a diagnostics ONLY. Never an admission path or downstream input.

    Keeps the finite model-output safety tests without treating arbitrary
    provider paraphrase equivalence as canonical typed fact authority.
    """
    return _validate(extraction, context, provider_diagnostic=True)


def _validate(extraction, context, *, provider_diagnostic):
    visible = {block.block_id: block.text for block in context.blocks}
    accepted, by_id, seen = [], {}, set()
    for item in extraction.items:
        refs = item.source_block_ids
        if len(set(refs)) != len(refs) or not set(refs) <= visible.keys():
            raise ResumeValidationError("INVALID_SOURCE_REFERENCE")
        if {quote.block_id for quote in item.source_quotes} != set(refs):
            raise ResumeValidationError("INVALID_SOURCE_REFERENCE")
        for quote in item.source_quotes:
            if normalize(quote.excerpt) not in normalize(visible[quote.block_id]):
                raise ResumeValidationError("EVIDENCE_VALIDATION_FAILED")
        quotes = tuple(quote.excerpt for quote in item.source_quotes)
        # Excerpts are untrusted until bound above; also check original block
        # scope so cropping away "not"/"supported" cannot manufacture ownership.
        def supported(value):
            return any(_supported(value, quote.excerpt) and _supported(value, visible[quote.block_id])
                       for quote in item.source_quotes)
        fields = []
        facts = []
        if isinstance(item, WorkExperienceEvidence):
            fields += [value for value in (item.role_title, item.organization, item.time_range) if value is not None]
            facts += [(value, False) for value in fields]  # Identity/date fields never inflected.
            fields += [*item.responsibilities, *item.achievements, *item.domain_signals, *item.tools, *item.business_metrics]
            facts += [(value, True) for value in (*item.responsibilities, *item.achievements, *item.domain_signals, *item.tools, *item.business_metrics)]
        elif isinstance(item, ProjectEvidence):
            fields += ([item.project_name] if item.project_name else []) + [*item.responsibilities, *item.achievements]
            facts += ([(item.project_name, False)] if item.project_name else [])
            facts += [(value, True) for value in (*item.responsibilities, *item.achievements)]
        if any(not supported(value) for value in fields):
            raise ResumeValidationError("EVIDENCE_VALIDATION_FAILED")
        if not facts:
            facts = [(unit, True) for quote in quotes for unit in _units(quote) if supported(unit)]
        if provider_diagnostic:
            if not supported(item.normalized_claim) and not _normalized_supported(item.normalized_claim, facts):
                raise ResumeValidationError("EVIDENCE_VALIDATION_FAILED")
        else:
            canonical = item.canonical_label if fields else _generic_representation(item.normalized_claim, quotes, supported)
            # Replace, not repair, model words. Every surviving typed fact has
            # already passed independent source/quote/material validation.
            item = item.model_copy(update={"normalized_claim": canonical})
        # Even a quoted redaction placeholder may not become a contact claim.
        if any(minimize_text(value)[1] or "removed]" in value or "已移除" in value for value in [item.normalized_claim, *fields]):
            raise ResumeValidationError("EVIDENCE_VALIDATION_FAILED")
        if item.claim_type == "explicit_career_statement" and not any(
                normalize(item.normalized_claim) in normalize(line) and explicit_intent(line)
                for quote in item.source_quotes for line in quote.excerpt.splitlines()):
            raise ResumeValidationError("EVIDENCE_VALIDATION_FAILED")
        if item.claim_type != "reported_fact" and isinstance(item, (WorkExperienceEvidence, ProjectEvidence)):
            raise ResumeValidationError("EVIDENCE_VALIDATION_FAILED")
        data = item.model_dump(mode="json", exclude={"evidence_id"})
        if not provider_diagnostic:
            data["normalized_claim"] = item.canonical_label
        key = json.dumps(data, ensure_ascii=False, sort_keys=True)
        if item.evidence_id in by_id and by_id[item.evidence_id] != key:
            raise ResumeValidationError("EVIDENCE_VALIDATION_FAILED")
        by_id[item.evidence_id] = key
        if key not in seen:
            seen.add(key)
            accepted.append(item)
    uncertainties = []
    for item in extraction.uncertainties:
        if len(set(item.source_block_ids)) != len(item.source_block_ids) or not set(item.source_block_ids) <= visible.keys():
            raise ResumeValidationError("INVALID_SOURCE_REFERENCE")
        if item not in uncertainties:
            uncertainties.append(item)
    return ResumeEvidenceExtraction(items=tuple(accepted), uncertainties=tuple(uncertainties))
