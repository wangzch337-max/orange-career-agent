"""Explicit validated selection; fixtures cannot load arbitrary executable code."""

from evaluation.models import Capability, EvaluationLayer, GoldenScenario
from evaluation.scenarios.catalogue import initial_scenarios


class ScenarioRegistry:
    def __init__(self, scenarios: list[GoldenScenario] | None = None):
        items = initial_scenarios() if scenarios is None else scenarios
        self._items = {}
        for item in items:
            scenario = GoldenScenario.model_validate(item.model_dump())
            if scenario.scenario_id in self._items:
                raise ValueError("Duplicate scenario ID")
            for ref in scenario.input_fixture_refs:
                if ref not in {
                    "evaluation/fixtures/application_input.json", "evaluation/fixtures/sparse_input.json",
                    "evaluation/fixtures/memory_cases.json", "evaluation/fixtures/guided_answers.json",
                    "data/fixtures/public_confirmed_profile.json", "data/fixtures/jobs/demo_jobs.json",
                    "data/fixtures/sample_user_input.json", "data/fixtures/sample_courses.json",
                }:
                    raise ValueError("Fixture reference is not in the synthetic/public allowlist")
            self._items[scenario.scenario_id] = scenario

    def select(self, *, scenario_ids=(), layer: EvaluationLayer | None = None,
               capability: Capability | None = None, tags=()) -> list[GoldenScenario]:
        if set(scenario_ids) - self._items.keys():
            raise ValueError("Unknown scenario ID")
        return [item.model_copy(deep=True) for item in self._items.values()
                if (not scenario_ids or item.scenario_id in scenario_ids)
                and (layer is None or item.layer == layer)
                and (capability is None or item.capability == capability)
                and set(tags).issubset(item.tags)]

    def all(self):
        return self.select()
