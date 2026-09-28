"""只读取公开本地 fixture 的岗位 provider。"""

import json
from pathlib import Path
from typing import List, Optional

from pydantic import TypeAdapter, ValidationError

from data.models import JobRecord
from tools.base import JobDataProvider
from workflows.stages import FixtureLoadError


DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "fixtures"
    / "jobs"
    / "demo_jobs.json"
)


class MockJobDataProvider(JobDataProvider):
    """Phase 4 public, fictional Demo Role Archetype provider。"""

    name = "MockJobDataProvider"

    def __init__(self, fixture_path: Optional[Path] = None) -> None:
        self.fixture_path = fixture_path or DEFAULT_FIXTURE

    def load(self) -> List[JobRecord]:
        try:
            payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))
            return TypeAdapter(List[JobRecord]).validate_python(payload)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise FixtureLoadError(f"无法读取岗位 fixture: {self.fixture_path}") from exc
