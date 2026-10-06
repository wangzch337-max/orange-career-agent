"""Public synthetic inputs reused from the frozen universal-career harness."""

from career_background_evaluation.harness import CareerHarness
from career_background_evaluation.scenarios import SCENARIOS
from career_discovery.demo import proposal_from_payload


def prepared(root, scenario=SCENARIOS[3]):
    harness = CareerHarness(root, scenario)
    harness.prepare()
    harness.resolve_all()
    harness.confirm(memory=True)
    return harness
