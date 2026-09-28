"""Small versioned prompt loader; no registry framework."""

import json
from pathlib import Path
from typing import Sequence

from providers.models import LLMMessage, MessageRole, SourceEvidence


PROMPT_NAME = "profile_signal_extraction"
PROMPT_VERSION = "v1"
PROMPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "prompts"
    / "profile_signal_extraction_v1.md"
)


def load_profile_signal_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def build_profile_signal_messages(
    prompt: str,
    source_evidence: Sequence[SourceEvidence],
) -> list[LLMMessage]:
    evidence_payload = [item.model_dump() for item in source_evidence]
    return [
        LLMMessage(role=MessageRole.SYSTEM, content=prompt),
        LLMMessage(
            role=MessageRole.USER,
            content=json.dumps(
                {"source_evidence": evidence_payload},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        ),
    ]
