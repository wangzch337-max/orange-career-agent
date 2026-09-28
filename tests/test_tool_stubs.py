"""本地 provider 与 Report Builder 测试。"""

from data.models import CareerReport
from tools.course_data import MockCourseDataProvider
from tools.job_data import MockJobDataProvider


def test_course_provider_loads_exactly_three_records() -> None:
    courses = MockCourseDataProvider().load()
    assert len(courses) == 3
    assert len({course.course_id for course in courses}) == 3


def test_job_provider_loads_exactly_three_records() -> None:
    jobs = MockJobDataProvider().load()
    assert len(jobs) == 3
    assert len({job.job_id for job in jobs}) == 3


def test_career_report_is_generated(completed_state) -> None:
    assert isinstance(completed_state.report, CareerReport)
    assert len(completed_state.report.role_insights) == 3
    assert "精确标签重合" in completed_state.report.workflow_summary
