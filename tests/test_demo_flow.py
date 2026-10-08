"""端到端 Demo、安全与离线约束测试。"""

import ast
import json
import re
import socket
from pathlib import Path

from workflows.demo import run_demo_to_completion, run_demo_until_confirmation
from workflows.stages import WorkflowStage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = PROJECT_ROOT / "data" / "fixtures"


def test_demo_stops_before_confirmation() -> None:
    paused = run_demo_until_confirmation()
    assert paused.stage == WorkflowStage.AWAITING_PROFILE_CONFIRMATION
    assert paused.profile_confirmed is False
    assert paused.job_records == []
    assert paused.job_intelligence == []
    assert paused.match_results == []
    assert paused.report is None


def test_demo_completes_after_confirmation() -> None:
    completed = run_demo_to_completion(run_demo_until_confirmation())
    assert completed.stage == WorkflowStage.COMPLETED
    assert completed.report is not None


def test_demo_requires_no_network(monkeypatch) -> None:
    def blocked(*args, **kwargs):
        raise AssertionError("Phase 1 测试禁止网络访问")

    monkeypatch.setattr(socket, "create_connection", blocked)
    completed = run_demo_to_completion(run_demo_until_confirmation())
    assert completed.stage == WorkflowStage.COMPLETED


def test_fixtures_have_exact_record_counts_and_no_obvious_identifiers() -> None:
    courses = json.loads((FIXTURE_DIR / "sample_courses.json").read_text(encoding="utf-8"))
    jobs = json.loads((FIXTURE_DIR / "jobs" / "demo_jobs.json").read_text(encoding="utf-8"))
    assert len(courses) == 3
    assert len(jobs) == 20

    combined = "\n".join(path.read_text(encoding="utf-8") for path in FIXTURE_DIR.rglob("*.json"))
    assert not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", combined)
    assert not re.search(r"\b(?:student[_ -]?id|phone|email|address)\b", combined, re.IGNORECASE)
    assert not re.search(r"\b[569]\d{7}\b", combined)


def test_python_imports_exclude_unapproved_frameworks() -> None:
    forbidden_roots = {
        "langchain",
        "chromadb",
        "qwen",
        "deepseek",
    }
    imported_roots = set()
    for path in PROJECT_ROOT.rglob("*.py"):
        if ".venv" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".")[0])
    assert imported_roots.isdisjoint(forbidden_roots)

    # Phase 7.5 permits Streamlit only in the presentation adapter and its tests.
    streamlit_importers = []
    for path in PROJECT_ROOT.rglob("*.py"):
        if ".venv" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        roots = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        roots.update(
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        if "streamlit" in roots:
            streamlit_importers.append(path.relative_to(PROJECT_ROOT).parts[0])
    assert set(streamlit_importers).issubset({"ui", "tests"})


def test_langgraph_imports_are_confined_to_phase_6_workflow_modules() -> None:
    importers = []
    for path in PROJECT_ROOT.rglob("*.py"):
        if ".venv" in path.parts or "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
        if "langgraph" in roots:
            importers.append(path.relative_to(PROJECT_ROOT).as_posix())
    assert set(importers) == {
        "workflows/langgraph_checkpoint.py",
        "workflows/langgraph_workflow.py",
        "storage/checkpoint.py",  # Exact owner-bound adapter, not a new graph/Agent.
    }


def test_openai_transport_import_is_confined_to_qwen_provider() -> None:
    importers = []
    for path in PROJECT_ROOT.rglob("*.py"):
        if ".venv" in path.parts or "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            roots = []
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots = [node.module.split(".")[0]]
            if "openai" in roots:
                importers.append(path.relative_to(PROJECT_ROOT).as_posix())
    assert set(importers) == {"providers/qwen.py"}
