"""只读取公开本地 fixture 的课程 provider。"""

import json
from pathlib import Path
from typing import List, Optional

from pydantic import TypeAdapter, ValidationError

from data.models import CourseRecord
from tools.base import CourseDataProvider
from workflows.stages import FixtureLoadError


DEFAULT_FIXTURE = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "sample_courses.json"


class MockCourseDataProvider(CourseDataProvider):
    """Phase 1 离线课程 fixture provider。"""

    name = "MockCourseDataProvider"

    def __init__(self, fixture_path: Optional[Path] = None) -> None:
        self.fixture_path = fixture_path or DEFAULT_FIXTURE

    def load(self) -> List[CourseRecord]:
        try:
            payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))
            return TypeAdapter(List[CourseRecord]).validate_python(payload)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise FixtureLoadError(f"无法读取课程 fixture: {self.fixture_path}") from exc
