"""Memory and SQLite checkpoint behavior using only public fixtures."""

from __future__ import annotations

import subprocess
from pathlib import Path

from workflows.langgraph_checkpoint import DEFAULT_SQLITE_CHECKPOINT_PATH
from workflows.langgraph_demo import run_memory_demo, run_sqlite_restart_demo
from workflows.langgraph_state import GraphWorkflowStatus


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_memory_demo_pauses_and_resumes_offline() -> None:
    paused, completed = run_memory_demo()
    assert paused["workflow_status"] == GraphWorkflowStatus.WAITING_FOR_HUMAN.value
    assert completed["workflow_status"] == GraphWorkflowStatus.COMPLETED.value
    assert paused["workflow_id"] == completed["workflow_id"]
    assert completed["self_discovery_call_count"] == 1


def test_sqlite_restart_recreates_runner_and_does_not_rerun_self_discovery(tmp_path) -> None:
    database = tmp_path / "orange_workflow.sqlite3"
    paused, completed = run_sqlite_restart_demo(path=database)
    assert database.exists()
    assert paused["workflow_status"] == GraphWorkflowStatus.WAITING_FOR_HUMAN.value
    assert completed["workflow_status"] == GraphWorkflowStatus.COMPLETED.value
    assert paused["workflow_id"] == completed["workflow_id"]
    assert paused["self_discovery_call_count"] == 1
    assert completed["self_discovery_call_count"] == 1


def test_default_sqlite_path_is_private_and_git_ignored() -> None:
    relative = DEFAULT_SQLITE_CHECKPOINT_PATH.relative_to(PROJECT_ROOT)
    assert relative.as_posix() == "data/private/runtime/orange_workflow.sqlite3"
    result = subprocess.run(
        ["git", "check-ignore", "-q", relative.as_posix()],
        cwd=PROJECT_ROOT,
        check=False,
    )
    assert result.returncode == 0
