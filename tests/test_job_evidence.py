"""Deterministic JobEvidenceBuilder behavior."""

from agents.job_intelligence_evidence import JobEvidenceBuilder
from agents.job_intelligence_models import JobEvidenceCategory, JobSourceEvidence
from tools.job_data import MockJobDataProvider


def test_job_source_evidence_contract() -> None:
    item = JobSourceEvidence(
        id="job_001_resp_001",
        job_id="job_001",
        category=JobEvidenceCategory.RESPONSIBILITY,
        text="Analyze requirements.",
        source_type="system_fixture",
    )
    assert item.category == JobEvidenceCategory.RESPONSIBILITY


def test_builder_assigns_stable_deterministic_ids() -> None:
    job = MockJobDataProvider().load()[0]
    builder = JobEvidenceBuilder()
    first = builder.build(job)
    second = builder.build(job)
    assert first == second
    assert first.source_evidence[0].id == "job_001_title_001"
    assert [item.id for item in first.source_evidence if item.category == JobEvidenceCategory.RESPONSIBILITY] == [
        "job_001_resp_001", "job_001_resp_002"
    ]


def test_builder_deduplicates_repeated_evidence() -> None:
    job = MockJobDataProvider().load()[0].model_copy(
        update={"responsibilities": ["Repeat this.", " repeat   this. ", "Keep this."]}
    )
    bundle = JobEvidenceBuilder().build(job)
    responsibilities = [
        item for item in bundle.source_evidence
        if item.category == JobEvidenceCategory.RESPONSIBILITY
    ]
    assert [item.text for item in responsibilities] == ["Repeat this.", "Keep this."]
    assert [item.id for item in responsibilities] == ["job_001_resp_001", "job_001_resp_002"]


def test_builder_uses_only_structured_job_values() -> None:
    job = MockJobDataProvider().load()[0]
    bundle = JobEvidenceBuilder().build(job)
    texts = {item.text for item in bundle.source_evidence}
    assert set(job.responsibilities).issubset(texts)
    assert set(job.requirements).issubset(texts)
    assert all(item.job_id == job.job_id for item in bundle.source_evidence)
