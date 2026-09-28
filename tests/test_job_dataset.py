"""Public-safety and taxonomy checks for the 20 fictional role archetypes."""

import re
from collections import Counter

import pytest
from pydantic import ValidationError

from data.models import JobRecord, Region, RoleFamily
from tools.job_data import MockJobDataProvider


EXPECTED_TITLES = {
    "AI Product Intern",
    "Associate AI Product Manager",
    "Technical Product Manager — AI",
    "AI Solutions Consultant",
    "Business Analyst — AI/Digital",
    "Innovation Analyst",
    "AI Application Engineer",
    "LLM Application Engineer",
    "AI Agent Engineer",
    "AI Automation / Workflow Engineer",
    "Machine Learning Engineer",
    "Data Scientist",
    "Data Analyst",
    "BI Analyst",
    "Computer Vision Engineer",
    "NLP Engineer",
    "AI Solutions Engineer",
    "MLOps / AI Platform Engineer",
    "Applied AI Research Assistant",
    "AI Research Intern",
}


@pytest.fixture(scope="module")
def jobs():
    return MockJobDataProvider().load()


def test_role_family_enum_has_the_six_phase_4_families() -> None:
    assert set(RoleFamily) == {
        RoleFamily.PRODUCT_BUSINESS,
        RoleFamily.AI_APPLICATION_AGENT,
        RoleFamily.ML_DATA,
        RoleFamily.SPECIALIZED_AI_ENGINEERING,
        RoleFamily.SOLUTION_PLATFORM,
        RoleFamily.RESEARCH,
    }
    assert RoleFamily.RESEARCH.display_name_zh == "AI研究"


def test_invalid_role_family_is_rejected(jobs) -> None:
    payload = jobs[0].model_dump()
    payload["role_family"] = "universal_career_ontology"
    with pytest.raises(ValidationError):
        JobRecord.model_validate(payload)


def test_demo_dataset_contains_exactly_the_twenty_requested_roles(jobs) -> None:
    assert len(jobs) == 20
    assert {job.title for job in jobs} == EXPECTED_TITLES
    assert len({job.job_id for job in jobs}) == 20
    assert all(job.title.strip() for job in jobs)


def test_demo_role_family_distribution(jobs) -> None:
    assert Counter(job.role_family for job in jobs) == {
        RoleFamily.PRODUCT_BUSINESS: 6,
        RoleFamily.AI_APPLICATION_AGENT: 4,
        RoleFamily.ML_DATA: 4,
        RoleFamily.SPECIALIZED_AI_ENGINEERING: 2,
        RoleFamily.SOLUTION_PLATFORM: 2,
        RoleFamily.RESEARCH: 2,
    }


def test_demo_region_and_city_distribution(jobs) -> None:
    assert Counter(job.region for job in jobs) == {
        Region.MAINLAND_CHINA: 12,
        Region.HONG_KONG: 3,
        Region.MACAU: 1,
        Region.TAIWAN: 4,
    }
    assert {job.city for job in jobs} == {
        "Beijing", "Shanghai", "Shenzhen", "Hangzhou", "Guangzhou",
        "Chengdu", "Hong Kong", "Macau", "Taipei", "Hsinchu",
    }


def test_all_organizations_are_explicitly_fictional_and_public_safe(jobs) -> None:
    assert all("Demo" in job.organization for job in jobs)
    assert all(job.metadata.get("fictional") is True for job in jobs)
    assert all(job.source_type.value == "system_fixture" for job in jobs)
    assert all(job.source_url is None for job in jobs)


def test_demo_dataset_contains_no_recruiter_contact_information(jobs) -> None:
    text = "\n".join(job.model_dump_json() for job in jobs)
    assert not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    assert not re.search(r"\b(?:recruiter|phone|wechat|whatsapp|contact person)\b", text, re.I)
    assert not re.search(r"https?://", text)
