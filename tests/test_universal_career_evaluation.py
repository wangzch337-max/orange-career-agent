"""Reusable deterministic cross-background evaluation through actual upload C.1–C.4."""

import pytest

from career_background_evaluation.harness import evaluate_scenario
from career_background_evaluation.scenarios import SCENARIOS


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.scenario_id)
def test_universal_career_background(tmp_path, scenario):
    assert evaluate_scenario(scenario, tmp_path) >= 50


def test_real_pdf_upload_path_is_also_e2e(tmp_path):
    assert evaluate_scenario(SCENARIOS[3], tmp_path, kind="pdf") >= 50


def test_suite_coverage_is_formal_and_stable():
    assert len(SCENARIOS) == 17
    assert len({s.scenario_id for s in SCENARIOS}) == 17
    tags = {tag for s in SCENARIOS for tag in s.tags}
    assert {"student", "experienced", "switcher", "audit", "finance", "manufacturing", "marketing", "design", "zero_projects", "work_heavy", "education", "limited_education", "clear_goal", "unknown_goal", "uncertainty", "cross_industry", "healthcare", "consulting"} <= tags
