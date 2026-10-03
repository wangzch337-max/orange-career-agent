"""Validate sealed core before degrading the sole optional suggestion tail.

No output repair, continuation, second semantic answer or provider call occurs.
Raw wire JSON stays transient. Ownership/proposal validation remains in engine.
"""

import json
import re

from career_runtime.models import ResponseCore, ResponseEnvelope
from ui.conversation_store import _content

MAX_WIRE_CHARACTERS = 160000  # Includes worst-case escaped Unicode, not just prose.


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate response field.")
        result[key] = value
    return result


def _sealed_core(raw):
    """Fallback ONLY after all ordered required fields are completely decoded."""
    decoder = json.JSONDecoder(object_pairs_hook=_unique_object)
    opening = re.match(r"\s*\{\s*", raw)
    if opening is None:
        raise ValueError("Incomplete core.")
    position, core = opening.end(), {}
    for index, field in enumerate(ResponseCore.model_fields):
        if index:
            match = re.match(r"\s*,\s*", raw[position:])
            if match is None:
                raise ValueError("Incomplete core.")
            position += match.end()
        key, position = decoder.raw_decode(raw, position)
        if key != field:
            raise ValueError("Required response order.")
        match = re.match(r"\s*:\s*", raw[position:])
        if match is None:
            raise ValueError("Incomplete core.")
        position += match.end()
        core[field], position = decoder.raw_decode(raw, position)
    if not re.match(r'^\s*,\s*"suggestions"\s*:', raw[position:]):
        raise ValueError("Not an optional tail.")
    return core


def finalize_wire(raw):
    """Called ONLY after SDK iterator exhausts with finish_reason=stop."""
    if len(raw) > MAX_WIRE_CHARACTERS:
        raise ValueError("Response exceeds wire bound.")
    complete = True
    try:
        payload = json.loads(raw, object_pairs_hook=_unique_object)
    except json.JSONDecodeError:
        payload, complete = _sealed_core(raw), False
    if not isinstance(payload, dict) or set(payload) - set(ResponseEnvelope.model_fields):
        raise ValueError("Unexpected response field.")
    core = ResponseCore.model_validate({key: value for key, value in payload.items() if key != "suggestions"})
    validate_core_text(core.visible_response)
    valid_optional = complete and "suggestions" in payload
    suggestions = payload.get("suggestions", [])
    try:
        if not valid_optional or type(suggestions) is not list or any(type(item) is not str for item in suggestions):
            raise ValueError("Optional suggestion collection.")
        result = ResponseEnvelope(**core.model_dump(), suggestions=suggestions)
        for item in suggestions:
            _content(item)
    except ValueError:
        result = ResponseEnvelope(**core.model_dump(), suggestions=[])
        valid_optional = False
    return result, complete, valid_optional, '"suggestions"' in raw


def validate_core_text(text):
    _content(text)
    text.encode("utf-8", errors="strict")


def degrade_suggestions(answer, *, policy, past):
    """Deterministic all-or-nothing optional degradation; no core alteration."""
    try:
        checked = ResponseEnvelope.model_validate(answer.model_dump())
        for item in checked.suggestions:
            _content(item)
        if (policy == "none" and checked.suggestions) or set(checked.suggestions) & past:
            raise ValueError("Optional suggestion policy.")
        return checked, False
    except ValueError:
        core = ResponseCore.model_validate({key: getattr(answer, key) for key in ResponseCore.model_fields})
        return ResponseEnvelope(**core.model_dump(), suggestions=[]), True
