"""Real Golden paths, state isolation, process exits and accident boundaries."""

import ast
import builtins
import io
import json
import os
import socket
import sqlite3
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from evaluation.boundaries import EvaluationBoundaryError, OfflineBoundary
from evaluation.models import EvaluationStatus as S, EvaluationReport, Capability
from evaluation.registry import ScenarioRegistry
from evaluation.report import markdown_report, write_reports
from evaluation.runner import EvaluationRunner, OUTPUT_ROOT, ROOT, exit_code
from evaluation.scenarios.execute import execute_scenario, relation_minimums, RELATION_MINIMUMS
from evaluation.taxonomy import FailureTaxonomy as T


@pytest.fixture(scope="module")
def complete_report():
    return EvaluationRunner().run()


@pytest.mark.parametrize("scenario_id", [item.scenario_id for item in ScenarioRegistry().all()])
def test_each_real_golden_case_satisfies_mandatory_contracts(complete_report, scenario_id):
    result = next(item for item in complete_report.scenarios if item.scenario_id == scenario_id)
    assert result.status == result.expected_status
    assert all(check.passed for check in result.checks)
    assert not result.findings


def test_complete_suite_expected_counts_and_only_fake_providers(complete_report):
    assert complete_report.summary.model_dump() == dict(total=27, **{"pass": 20}, fail=0, expected_uncertainty=7, needs_review=0)
    assert complete_report.run.llm_provider == "FakeLLMProvider"
    assert complete_report.run.embedding_provider == "FakeEmbeddingProvider"
    assert complete_report.run.mode == "offline_synthetic"
    assert complete_report.run.network_attempt_count == complete_report.run.private_access_attempt_count == 0


def test_reverse_order_and_repeated_runs_have_identical_scenario_results(complete_report):
    reverse = EvaluationRunner(ScenarioRegistry(list(reversed(ScenarioRegistry().all())))).run()
    repeated = EvaluationRunner().run()
    reference = {result.scenario_id: result.model_dump() for result in complete_report.scenarios}
    assert {result.scenario_id: result.model_dump() for result in reverse.scenarios} == reference
    assert {result.scenario_id: result.model_dump() for result in repeated.scenarios} == reference
    assert reverse.run.run_id != repeated.run.run_id
    assert not list(OUTPUT_ROOT.glob("scenario_*"))


@pytest.mark.parametrize("call", [
    lambda: socket.create_connection(("invalid.test", 443)),
    lambda: socket.getaddrinfo("invalid.test", 443),
    lambda: socket.gethostbyname("invalid.test"),
    lambda: socket.socket().connect(("127.0.0.1", 443)),
    lambda: socket.socket().connect_ex(("127.0.0.1", 443)),
    lambda: subprocess.Popen(["curl", "invalid.test"]),
    lambda: os.system("curl invalid.test"),
])
def test_network_and_subprocess_attempts_blocked_before_side_effect(call):
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=OUTPUT_ROOT) as name:
        boundary = OfflineBoundary(Path(name))
        with boundary:
            with pytest.raises(EvaluationBoundaryError):
                call()
        assert boundary.attempts == [T.NETWORK_BOUNDARY_VIOLATION]


@pytest.mark.parametrize("relative", [".env.local", ".env", "data/private/golden_case/confirmed_profile.json",
                                     "data/private/memory/orange_memory.sqlite3", "downloaded_model.onnx"])
@pytest.mark.parametrize("reader", [builtins.open, io.open, lambda path: path.read_text()])
def test_private_paths_never_opened(relative, reader):
    # Saved builtins/io references would bypass monkeypatching; resolve inside guard.
    with TemporaryDirectory(dir=OUTPUT_ROOT) as name:
        boundary = OfflineBoundary(Path(name))
        with boundary:
            guarded = builtins.open if reader is ORIGINAL_OPEN else io.open if reader is ORIGINAL_IO_OPEN else reader
            with pytest.raises(EvaluationBoundaryError):
                guarded(ROOT / relative)
        assert boundary.attempts == [T.PRIVATE_DATA_BOUNDARY_VIOLATION]


ORIGINAL_OPEN, ORIGINAL_IO_OPEN = builtins.open, io.open


def test_local_db_uri_and_unsafe_db_outside_isolation_blocked():
    with TemporaryDirectory(dir=OUTPUT_ROOT) as name:
        boundary = OfflineBoundary(Path(name))
        with boundary:
            for path in (ROOT / "data/private/never_open.sqlite3", ROOT / "unused.sqlite3", "file:data/private/never_open.sqlite3"):
                with pytest.raises(EvaluationBoundaryError):
                    sqlite3.connect(path)
            assert sqlite3.connect(":memory:").execute("select 1").fetchone() == (1,)
        assert len(boundary.attempts) == 3


@pytest.mark.parametrize("provider", ["qwen", "openai", "async_openai", "local_embedding"])
def test_live_provider_and_model_constructor_never_runs(provider):
    with TemporaryDirectory(dir=OUTPUT_ROOT) as name:
        with OfflineBoundary(Path(name)) as boundary:
            from providers.qwen import QwenProvider
            from memory.embeddings import LocalEmbeddingProvider
            import openai
            constructor = {"qwen": QwenProvider, "openai": openai.OpenAI,
                "async_openai": openai.AsyncOpenAI, "local_embedding": LocalEmbeddingProvider}[provider]
            with pytest.raises(EvaluationBoundaryError):
                constructor()
        assert boundary.attempts == [T.NETWORK_BOUNDARY_VIOLATION]


def test_caught_boundary_violation_still_fails_and_collects_other_scenarios(monkeypatch):
    original = execute_scenario
    def sabotaged(scenario_id, temporary_root):
        observation = original(scenario_id, temporary_root)
        if scenario_id == "SD_001":
            try:
                socket.create_connection(("invalid.test", 443))
            except EvaluationBoundaryError:
                pass
        return observation
    monkeypatch.setattr("evaluation.runner.execute_scenario", sabotaged)
    report = EvaluationRunner().run(scenario_ids=["SD_001", "SD_002"])
    assert len(report.scenarios) == 2 and report.summary.fail == 1
    assert report.run.network_attempt_count == 1
    finding = next(item for item in report.scenarios[0].findings if item.taxonomy == T.NETWORK_BOUNDARY_VIOLATION)
    assert finding.severity.value == "BLOCKING" and exit_code(report) == 1
    fast = EvaluationRunner().run(scenario_ids=["SD_001", "SD_002"], fail_fast=True)
    assert fast.run.executed_scenario_count == 1 and fast.run.selected_scenario_count == 2


def test_private_attempt_and_exception_details_never_appear_in_reports(monkeypatch):
    sentinel = "SENSITIVE_EXCEPTION_SENTINEL"
    def private_attempt(scenario_id, temporary_root):
        try:
            (ROOT / "data/private/never_load.json").read_text()
        except EvaluationBoundaryError:
            raise RuntimeError(sentinel)
    monkeypatch.setattr("evaluation.runner.execute_scenario", private_attempt)
    report = EvaluationRunner().run(scenario_ids=["SD_001"])
    assert report.summary.fail == 1 and report.run.private_access_attempt_count == 1
    assert any(item.taxonomy == T.PRIVATE_DATA_BOUNDARY_VIOLATION for item in report.scenarios[0].findings)
    assert sentinel not in report.model_dump_json() and sentinel not in markdown_report(report)
    assert "never_load" not in report.model_dump_json()
    assert not list(OUTPUT_ROOT.glob("scenario_*"))


def test_safe_serialization_counts_and_failures_first_report(complete_report):
    assert EvaluationReport.model_validate_json(complete_report.model_dump_json()) == complete_report
    markdown = markdown_report(complete_report)
    assert markdown.index("FAIL / NEEDS_REVIEW") < markdown.index("全部场景与检查")
    assert "EXPECTED_UNCERTAINTY" in markdown and "FakeLLMProvider" in markdown
    assert "observations" not in complete_report.model_dump()
    for scenario in complete_report.scenarios:
        assert scenario.scenario_id in markdown
        for check in scenario.checks:
            assert check.check_id in markdown
    with TemporaryDirectory(dir=OUTPUT_ROOT) as name:
        paths = write_reports(complete_report, Path(name))
        assert EvaluationReport.model_validate_json(paths[0].read_text()) == complete_report
        assert paths[1].read_text() == markdown
    with pytest.raises(ValueError):
        write_reports(complete_report, ROOT / "data/private")


def test_needs_review_exit_is_explicit_optional_strict_mode(complete_report):
    review = complete_report.model_copy(deep=True)
    review.summary.needs_review = 1
    assert exit_code(review) == 0 and exit_code(review, strict_review=True) == 1
    assert exit_code(complete_report) == 0


@pytest.mark.parametrize("args,expected_count", [
    (["--scenario", "SD_001"], 1), (["--capability", "memory"], 5),
    (["--layer", "end_to_end_journey"], 4), (["--tag", "uncertainty"], 7),
])
def test_cli_selects_runs_and_returns_useful_exit(args, expected_count, capsys):
    from evaluation.run import main
    with TemporaryDirectory(dir=OUTPUT_ROOT) as name:
        assert main([*args, "--output", name]) == 0
        report = EvaluationReport.model_validate_json((Path(name) / "report.json").read_text())
        assert report.summary.total == expected_count
    assert "network_attempts=0" in capsys.readouterr().out


@pytest.mark.parametrize("args", [["--scenario", "MI_999"], ["--tag", "no_such_tag"]])
def test_cli_invalid_empty_selection_returns_two(args, capsys):
    from evaluation.run import main
    assert main(args) == 2
    assert "invalid" in capsys.readouterr().out


def test_module_cli_process_has_no_live_option():
    result = subprocess.run([str(ROOT / ".venv/bin/python"), "-m", "evaluation.run", "--help"],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0 and "--scenario" in result.stdout
    assert "--live" not in result.stdout


@pytest.mark.parametrize("relation,categories,job_categories,limit", [
    ("strong_alignment", ["career_preference"], ["required_capability"], False),
    ("confirmed_gap", ["skill"], ["required_capability"], False),
    ("confirmed_gap", ["development_area"], ["required_capability"], False),
    ("experience_depth_gap", [], ["actual_work"], False),
    ("preference_alignment", ["skill"], ["actual_work"], False),
    ("potential_friction", ["skill"], ["actual_work"], False),
    ("evidence_missing", ["skill"], ["required_capability"], False),
    ("unknown", ["skill"], ["required_capability"], False),
])
def test_independent_relation_minimum_matrix_detects_invalid_substitutions(relation, categories, job_categories, limit):
    assert not relation_minimums([dict(relation=relation, profile_categories=categories,
        job_categories=job_categories, explicit_limit=limit, profile_uncertain=False)])
    assert len(RELATION_MINIMUMS) == 8


def test_evaluation_logic_stays_outside_production_and_no_judge_imports():
    for directory in ("agents", "workflows", "ui", "memory", "tools"):
        for path in (ROOT / directory).glob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert not node.module.startswith("evaluation")
    for path in (ROOT / "evaluation").rglob("*.py"):
        source = path.read_text().casefold()
        assert "llm_as_judge" not in source and "generate_text(" not in source


def test_generated_outputs_and_existing_private_boundaries_are_git_ignored():
    result = subprocess.run(["git", "check-ignore", "artifacts/evaluation/report.json", ".env.local", ".venv",
        "data/private/golden_case/confirmed_profile.json", "data/private/memory/orange_memory.sqlite3"], cwd=ROOT,
        capture_output=True, text=True)
    assert result.returncode == 0 and len(result.stdout.splitlines()) == 5
    tracked = subprocess.check_output(["git", "ls-files", "data/private", "artifacts/evaluation", ".env.local"], cwd=ROOT)
    assert not tracked.strip()
