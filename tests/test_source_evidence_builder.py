"""Deterministic SourceEvidenceBuilder tests using public synthetic data only."""

from agents.self_discovery_evidence import SourceEvidenceBuilder
from data.models import CourseRecord


def course(course_id: str = "course_a") -> CourseRecord:
    return CourseRecord(course_id=course_id, title="Synthetic AI Course", summary="公开模拟课程。")


def public_input() -> dict:
    return {
        "program": "匿名 AI 相关硕士课程",
        "career_interest": "AI 应用",
        "career_goal": "探索多个方向",
        "career_values": ["持续学习", "持续学习"],
        "project_experience": {"name": "Synthetic Prototype", "summary": "使用公开模拟数据。"},
    }


def test_builder_assigns_stable_ids() -> None:
    builder = SourceEvidenceBuilder()
    first = builder.build(public_input(), [course()])
    second = builder.build(public_input(), [course()])
    assert [item.id for item in first.source_evidence] == [item.id for item in second.source_evidence]
    assert [item.id for item in first.source_evidence][:3] == ["user_001", "course_001", "project_001"]


def test_builder_deduplicates_courses_and_repeated_values() -> None:
    bundle = SourceEvidenceBuilder().build(public_input(), [course(), course()])
    ids = [item.id for item in bundle.source_evidence]
    assert ids.count("course_001") == 1
    assert [item for item in ids if item.startswith("value_")] == ["value_001"]


def test_builder_keeps_provider_and_domain_evidence_aligned() -> None:
    bundle = SourceEvidenceBuilder().build(public_input(), [course()])
    assert [item.id for item in bundle.source_evidence] == [item.id for item in bundle.domain_evidence]


def test_absence_of_skill_evidence_does_not_create_a_weakness() -> None:
    bundle = SourceEvidenceBuilder().build(public_input(), [course()])
    assert all(not item.supports_development_area for item in bundle.source_evidence)
    assert all("SQL" not in item.text for item in bundle.source_evidence)


def test_explicit_development_area_is_marked() -> None:
    payload = public_input()
    payload["explicit_development_areas"] = ["我明确说明自己只有有限的公开演讲经验。"]
    bundle = SourceEvidenceBuilder().build(payload, [course()])
    item = next(item for item in bundle.source_evidence if item.id == "development_001")
    assert item.supports_development_area is True


def test_builder_does_not_read_private_directory(monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("builder must not read files")

    monkeypatch.setattr("pathlib.Path.read_text", forbidden)
    assert SourceEvidenceBuilder().build(public_input(), [course()]).source_evidence
