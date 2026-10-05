"""Versioned prompt in the existing config/prompts layout; no prompt registry."""

from pathlib import Path

from resume_evidence.policy import PROMPT_NAME, PROMPT_VERSION

PROMPT_PATH = Path(__file__).resolve().parents[1] / "config/prompts/resume_evidence_v1.md"


def load_resume_evidence_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip()
