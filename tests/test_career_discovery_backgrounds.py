"""Focused D.1 universal background evaluation, not the full release suite."""

import pytest
from career_background_evaluation.discovery import evaluate_discovery
from career_background_evaluation.scenarios import SCENARIOS


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.scenario_id)
def test_discovery_universal_background(tmp_path, scenario):
    assert evaluate_discovery(scenario, tmp_path) >= 35
