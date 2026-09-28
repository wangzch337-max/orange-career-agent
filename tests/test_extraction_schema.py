"""ProfileSignalExtraction and evidence grounding tests."""

import pytest
from pydantic import ValidationError

from providers.errors import LLMStructuredOutputError
from providers.models import (
    ExtractedGoal,
    ExtractedSkill,
    ProfileSignalExtraction,
    ProfileSignalInput,
    SourceEvidence,
)


def test_signal_confidence_bounds() -> None:
    ExtractedSkill(label="AI", confidence=0.0, evidence_ids=["source_001"])
    ExtractedSkill(label="AI", confidence=1.0, evidence_ids=["source_001"])
    with pytest.raises(ValidationError):
        ExtractedSkill(label="AI", confidence=1.01, evidence_ids=["source_001"])


def test_evidence_id_validation_succeeds() -> None:
    sources = [SourceEvidence(id="source_001", text="公开模拟证据")]
    extraction = ProfileSignalExtraction(
        candidate_skills=[
            ExtractedSkill(label="AI", confidence=0.8, evidence_ids=["source_001"])
        ]
    )
    assert extraction.validate_evidence_ids(sources) is extraction


def test_invented_evidence_id_is_rejected() -> None:
    sources = [SourceEvidence(id="source_001", text="公开模拟证据")]
    extraction = ProfileSignalExtraction(
        goal_signals=[
            ExtractedGoal(label="Explore AI", confidence=0.7, evidence_ids=["invented_999"])
        ]
    )
    with pytest.raises(LLMStructuredOutputError, match="未知 evidence IDs"):
        extraction.validate_evidence_ids(sources)


def test_source_ids_must_be_unique() -> None:
    with pytest.raises(ValidationError, match="必须唯一"):
        ProfileSignalInput(
            source_evidence=[
                SourceEvidence(id="same", text="a"),
                SourceEvidence(id="same", text="b"),
            ]
        )


def test_signal_requires_at_least_one_evidence_id() -> None:
    with pytest.raises(ValidationError):
        ExtractedSkill(label="AI", confidence=0.8, evidence_ids=[])
