"""Isolated deterministic execution and honest status derivation."""

import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from evaluation.boundaries import OfflineBoundary
from evaluation.checks import derive_status, evaluate_check
from evaluation.models import (EvaluationReport, EvaluationStatus, EvaluationSummary,
                               RequiredExpectation, RunMetadata, ScenarioResult)
from evaluation.registry import ScenarioRegistry
from evaluation.scenarios.execute import execute_scenario
from evaluation.taxonomy import FailureTaxonomy as T


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "artifacts" / "evaluation"


class EvaluationRunner:
    """Single-threaded runner; global accident guards must not be used concurrently."""

    def __init__(self, registry: ScenarioRegistry | None = None):
        self.registry = registry or ScenarioRegistry()

    def run(self, *, scenario_ids=(), layer=None, capability=None, tags=(), fail_fast=False):
        scenarios = self.registry.select(scenario_ids=scenario_ids, layer=layer, capability=capability, tags=tags)
        if not scenarios:
            raise ValueError("Selection contains no scenarios")
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        results = []
        network_attempts = private_attempts = 0
        for scenario in scenarios:
            with TemporaryDirectory(prefix="scenario_", dir=OUTPUT_ROOT) as name:
                boundary = OfflineBoundary(Path(name))
                observation = {}
                error = False
                with boundary:
                    try:
                        observation = execute_scenario(scenario.scenario_id, Path(name))
                    except Exception:
                        # Exception text/locals may contain sensitive data; do not serialize them.
                        error = True
                network_count = boundary.attempts.count(T.NETWORK_BOUNDARY_VIOLATION)
                private_count = boundary.attempts.count(T.PRIVATE_DATA_BOUNDARY_VIOLATION)
                network_attempts += network_count
                private_attempts += private_count
                observation.update(network_attempts=network_count, private_attempts=private_count,
                                   execution_completed=not error)
                guards = [
                    RequiredExpectation(check_id="zero_network", path="network_attempts", expected=0,
                        summary="默认 Golden Suite 禁止任何网络调用", taxonomy=T.NETWORK_BOUNDARY_VIOLATION, source_component="runner"),
                    RequiredExpectation(check_id="zero_private_access", path="private_attempts", expected=0,
                        summary="禁止加载私有数据、配置或模型文件", taxonomy=T.PRIVATE_DATA_BOUNDARY_VIOLATION, source_component="runner"),
                    RequiredExpectation(check_id="execution_completed", path="execution_completed", expected=True,
                        summary="生产适配器须完整执行；异常仅保留安全类别", taxonomy=T.CROSS_COMPONENT_INVARIANT_BREAK, source_component="runner"),
                ]
                checks = [evaluate_check(scenario.scenario_id, check, observation) for check in [*scenario.checks, *guards]]
                status = derive_status(scenario, checks)
                results.append(ScenarioResult(scenario_id=scenario.scenario_id, title=scenario.title,
                    layer=scenario.layer, capability=scenario.capability, expected_status=scenario.expected_status,
                    status=status, checks=checks, findings=[check.failure for check in checks if check.failure]))
            if fail_fast and status == EvaluationStatus.FAIL:
                break
        counts = {status: sum(result.status == status for result in results) for status in EvaluationStatus}
        try:
            commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            commit = None
        return EvaluationReport(run=RunMetadata(run_id=f"eval_{uuid4().hex}",
            timestamp=datetime.now(timezone.utc).isoformat(), git_commit=commit,
            python_version=platform.python_version(), selected_scenario_count=len(scenarios), executed_scenario_count=len(results),
            selected_tags=list(tags), network_attempt_count=network_attempts, private_access_attempt_count=private_attempts),
            summary=EvaluationSummary(total=len(results), pass_count=counts[EvaluationStatus.PASS], fail=counts[EvaluationStatus.FAIL],
                expected_uncertainty=counts[EvaluationStatus.EXPECTED_UNCERTAINTY], needs_review=counts[EvaluationStatus.NEEDS_REVIEW]),
            scenarios=results)


def exit_code(report: EvaluationReport, *, strict_review=False):
    return int(bool(report.summary.fail or (strict_review and report.summary.needs_review)))
