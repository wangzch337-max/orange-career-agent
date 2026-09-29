"""Small versioned prompt loader; no registry framework."""

import json
from pathlib import Path
from typing import Sequence

from pydantic import BaseModel

from providers.models import LLMMessage, MessageRole, SourceEvidence


PROMPT_NAME = "profile_signal_extraction"
PROMPT_VERSION = "v1"
PROMPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "prompts"
    / "profile_signal_extraction_v1.md"
)

SELF_DISCOVERY_PROMPT_NAME = "self_discovery"
SELF_DISCOVERY_PROMPT_VERSION = "v2"
SELF_DISCOVERY_PROMPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "prompts"
    / "self_discovery_v2.md"
)

JOB_INTELLIGENCE_PROMPT_NAME = "job_intelligence"
JOB_INTELLIGENCE_PROMPT_VERSION = "v1"
JOB_INTELLIGENCE_PROMPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "prompts"
    / "job_intelligence_v1.md"
)

MATCH_INSIGHT_PROMPT_NAME = "match_insight"
MATCH_INSIGHT_PROMPT_VERSION = "v5"
MATCH_INSIGHT_PROMPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "prompts"
    / "match_insight_v5.md"
)


def load_profile_signal_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def load_self_discovery_prompt() -> str:
    return SELF_DISCOVERY_PROMPT_PATH.read_text(encoding="utf-8").strip()


def load_job_intelligence_prompt() -> str:
    return JOB_INTELLIGENCE_PROMPT_PATH.read_text(encoding="utf-8").strip()


def load_match_insight_prompt() -> str:
    return MATCH_INSIGHT_PROMPT_PATH.read_text(encoding="utf-8").strip()


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


def build_self_discovery_messages(
    prompt: str,
    source_evidence: Sequence[BaseModel],
) -> list[LLMMessage]:
    return [
        LLMMessage(role=MessageRole.SYSTEM, content=prompt),
        LLMMessage(
            role=MessageRole.USER,
            content=json.dumps(
                {"source_evidence": [item.model_dump(mode="json") for item in source_evidence]},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        ),
    ]


def build_job_intelligence_messages(
    prompt: str,
    job_evidence: Sequence[BaseModel],
) -> list[LLMMessage]:
    return [
        LLMMessage(role=MessageRole.SYSTEM, content=prompt),
        LLMMessage(
            role=MessageRole.USER,
            content=json.dumps(
                {"job_evidence": [item.model_dump(mode="json") for item in job_evidence]},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        ),
    ]


def build_match_insight_messages(
    prompt: str,
    match_context: BaseModel,
) -> list[LLMMessage]:
    return [
        LLMMessage(role=MessageRole.SYSTEM, content=prompt),
        LLMMessage(
            role=MessageRole.USER,
            content=json.dumps(
                {"match_context": match_context.model_dump(mode="json")},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        ),
    ]
