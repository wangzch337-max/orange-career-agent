"""Structured extraction, deterministic assembly, agent, and safety boundary tests."""

import ast
import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from agents.job_intelligence import JobIntelligenceAgent, public_offline_job_extraction
from agents.job_intelligence_assembler import JobIntelligenceAssembler
from agents.job_intelligence_demo import run_offline_demo
from agents.job_intelligence_evidence import JobEvidenceBuilder
from agents.job_intelligence_models import JobExtractionSignal, JobIntelligenceExtraction
from data.models import JobSignalInferenceType, JobUncertainty
from providers.base import LLMProvider
from providers.errors import LLMStructuredOutputError
from providers.fake import FakeLLMProvider
from providers.prompts import load_job_intelligence_prompt
from tools.job_data import MockJobDataProvider


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def job_and_bundle():
    job = MockJobDataProvider().load()[0]
    return job, JobEvidenceBuilder().build(job)


def test_extraction_schema_contains_all_nine_categories(job_and_bundle) -> None:
    job, bundle = job_and_bundle
    extraction = public_offline_job_extraction(job, bundle)
    assert all(extraction.signal_counts().values())


@pytest.mark.parametrize(
    "field_name",
    [
        "actual_work", "required_capabilities", "preferred_capabilities",
        "technology_signals", "work_style_signals", "collaboration_context",
        "growth_exposure", "potential_friction",
    ],
)
def test_every_job_signal_category_requires_evidence(field_name) -> None:
    with pytest.raises(ValidationError):
        JobIntelligenceExtraction.model_validate(
            {
                field_name: [{
                    "label": "signal", "description": "description", "confidence": 0.8,
                    "evidence_ids": [], "inference_type": "explicit_job_fact",
                }]
            }
        )


def test_signal_confidence_is_strictly_bounded() -> None:
    with pytest.raises(ValidationError):
        JobExtractionSignal(
            label="x", description="x", confidence=1.01,
            evidence_ids=["ev_1"], inference_type="explicit_job_fact",
        )


def test_duplicate_signal_evidence_ids_are_rejected() -> None:
    with pytest.raises(ValidationError):
        JobExtractionSignal(
            label="x", description="x", confidence=0.8,
            evidence_ids=["ev_1", "ev_1"], inference_type="explicit_job_fact",
        )


def test_unknown_evidence_id_is_rejected(job_and_bundle) -> None:
    job, bundle = job_and_bundle
    extraction = public_offline_job_extraction(job, bundle)
    extraction.actual_work[0].evidence_ids = ["unknown_evidence"]
    with pytest.raises(LLMStructuredOutputError):
        extraction.validate_evidence_ids(bundle.source_evidence)


def test_job_uncertainty_contract_preserves_missing_information() -> None:
    item = JobUncertainty(topic="salary", reason="Not supplied.")
    assert item.unknown_due_to_missing_information is True
    assert item.evidence_ids == []


def test_missing_salary_promotion_and_work_life_stay_unknown(job_and_bundle) -> None:
    job, bundle = job_and_bundle
    topics = {item.topic for item in public_offline_job_extraction(job, bundle).job_uncertainties}
    assert {"salary", "promotion_path", "work_life_balance"}.issubset(topics)


def test_explicit_fact_and_inference_types_are_both_preserved(job_and_bundle) -> None:
    job, bundle = job_and_bundle
    extraction = public_offline_job_extraction(job, bundle)
    assert extraction.actual_work[0].inference_type == JobSignalInferenceType.EXPLICIT_JOB_FACT
    assert extraction.growth_exposure[0].inference_type == JobSignalInferenceType.EVIDENCE_SUPPORTED_JOB_INFERENCE


def test_assembler_preserves_signals_links_confidence_and_type(job_and_bundle) -> None:
    job, bundle = job_and_bundle
    extraction = public_offline_job_extraction(job, bundle)
    record = JobIntelligenceAssembler().assemble(
        job=job, extraction=extraction, evidence=bundle, analysis_metadata={"provider": "fake"}
    )
    assert record.actual_work[0].model_dump(exclude={"signal_id"}) == extraction.actual_work[0].model_dump()
    assert record.growth_exposure[0].confidence == extraction.growth_exposure[0].confidence
    assert record.growth_exposure[0].inference_type == extraction.growth_exposure[0].inference_type
    assert set(record.evidence_ids) == {
        evidence_id
        for item in [*extraction.signals(), *extraction.job_uncertainties]
        for evidence_id in item.evidence_ids
    }


def test_assembler_does_not_invent_signals_or_technologies(job_and_bundle) -> None:
    job, bundle = job_and_bundle
    extraction = JobIntelligenceExtraction()
    record = JobIntelligenceAssembler().assemble(
        job=job, extraction=extraction, evidence=bundle, analysis_metadata={}
    )
    assert record.actual_work == []
    assert record.technology_signals == []
    assert record.evidence_ids == []


def test_agent_depends_on_llm_provider_and_not_qwen_directly() -> None:
    source = (ROOT / "agents" / "job_intelligence.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "providers.base" in imported
    assert "providers.qwen" not in imported
    assert issubclass(FakeLLMProvider, LLMProvider)


def test_agent_runs_standalone_without_user_profile(job_and_bundle) -> None:
    job, bundle = job_and_bundle
    fake = FakeLLMProvider(public_offline_job_extraction(job, bundle))
    record = JobIntelligenceAgent(MockJobDataProvider(), fake).analyze(job)
    assert record.job_id == job.job_id
    assert fake.call_count == 1


def test_job_intelligence_never_creates_fit_ranking_or_recommendation_fields() -> None:
    forbidden = {"fit_score", "match_score", "ranking", "recommendation", "best_role"}
    assert forbidden.isdisjoint(JobIntelligenceExtraction.model_fields)
    from data.models import JobIntelligenceRecord
    assert forbidden.isdisjoint(JobIntelligenceRecord.model_fields)


def test_fake_provider_sequence_supports_all_twenty_roles() -> None:
    results = run_offline_demo()
    assert len(results) == 20
    assert all(record.job_id == job.job_id for job, record, _ in results)
    assert all(response.provider == "fake" for _, _, response in results)


def test_prompt_loads_as_job_intelligence_v1_and_contains_safety_rules() -> None:
    prompt = load_job_intelligence_prompt()
    assert "job_intelligence@v1" in prompt
    assert "不得编造" in prompt
    assert "不计算适配度" in prompt


def test_previous_prompt_bytes_are_unchanged() -> None:
    expected = {
        "profile_signal_extraction_v1.md": "4021dc9feb9441720e92325ca70f58deac5d7fcfb12690655c56a30512727192",
        "self_discovery_v1.md": "27ce461b5c1a6b1f062f24f04dfa42aaa90e0d00803d41d579b2ba475134eacb",
    }
    for name, digest in expected.items():
        payload = (ROOT / "config" / "prompts" / name).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == digest


def test_offline_technology_signals_are_present_in_supplied_evidence() -> None:
    for job, record, _ in run_offline_demo():
        evidence_texts = {item.statement for item in record.evidence}
        assert all(signal.label in evidence_texts for signal in record.technology_signals), job.job_id
