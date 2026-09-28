"""基础 Pydantic model 验证。"""

import pytest
from pydantic import ValidationError

from data.models import EmploymentType, EvidenceItem, EvidenceSourceType, JobRecord


def test_evidence_confidence_accepts_bounds() -> None:
    for value in (0.0, 1.0):
        item = EvidenceItem(
            id=f"ev_{value}",
            source_type=EvidenceSourceType.SYSTEM_FIXTURE,
            source_name="test",
            statement="公开测试证据",
            confidence=value,
        )
        assert item.confidence == value


@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_evidence_confidence_rejects_out_of_range(value: float) -> None:
    with pytest.raises(ValidationError):
        EvidenceItem(
            id="ev_invalid",
            source_type=EvidenceSourceType.SYSTEM_FIXTURE,
            source_name="test",
            statement="公开测试证据",
            confidence=value,
        )


def test_evidence_source_type_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        EvidenceItem(
            id="ev_invalid_source",
            source_type="personal_guess",
            source_name="test",
            statement="测试",
            confidence=0.5,
        )


def test_job_record_validates_required_fields() -> None:
    record = JobRecord(
        job_id="job_test",
        title="Demo Intern",
        organization="Fictional Studio",
        location="Hong Kong",
        region="hong_kong",
        employment_type=EmploymentType.INTERNSHIP,
        description="虚构岗位。",
        source="phase_1_fixture",
    )
    assert record.source_url is None
    with pytest.raises(ValidationError):
        JobRecord(
            job_id="job_test",
            title="",
            organization="Fictional Studio",
            location="Hong Kong",
            region="hong_kong",
            employment_type=EmploymentType.INTERNSHIP,
            description="虚构岗位。",
            source="phase_1_fixture",
        )
