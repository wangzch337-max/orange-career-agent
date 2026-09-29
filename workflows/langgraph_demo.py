"""Public offline LangGraph Demo with memory or private SQLite checkpoints."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from workflows.langgraph_checkpoint import (
    DEFAULT_SQLITE_CHECKPOINT_PATH,
    create_memory_checkpointer,
    sqlite_checkpointer,
)
from workflows.langgraph_runtime import (
    DEFAULT_SELECTED_JOB_IDS,
    build_public_offline_dependencies,
)
from workflows.langgraph_state import ProfileReviewAction, ProfileReviewDecision
from workflows.langgraph_workflow import (
    OrangeGraphRunner,
    build_orange_graph,
    create_initial_graph_state,
)


def _safe_summary(state: dict[str, object]) -> dict[str, object]:
    return {
        "workflow_id": state["workflow_id"],
        "workflow_status": state["workflow_status"],
        "selected_job_count": len(state["selected_job_ids"]),
        "profile_version": (
            state["profile"].get("version") if state.get("profile") else None
        ),
        "self_discovery_call_count": state["self_discovery_call_count"],
        "job_intelligence_count": len(state["job_intelligence"]),
        "match_result_count": len(state["match_results"]),
        "report_created": state["report"] is not None,
        "checkpoint_mode": state["checkpoint_mode"],
    }


def run_memory_demo(
    *,
    selected_job_ids: Sequence[str] = DEFAULT_SELECTED_JOB_IDS,
) -> tuple[dict[str, object], dict[str, object]]:
    dependencies = build_public_offline_dependencies(selected_job_ids)
    graph = build_orange_graph(
        dependencies=dependencies,
        checkpointer=create_memory_checkpointer(),
    )
    runner = OrangeGraphRunner(graph)
    paused = runner.start(
        create_initial_graph_state(
            selected_job_ids=selected_job_ids,
            checkpoint_mode="memory",
        )
    )
    completed = runner.resume(
        paused["workflow_id"],
        ProfileReviewDecision(action=ProfileReviewAction.CONFIRM),
    )
    return paused, completed


def start_sqlite_demo(
    *,
    workflow_id: str | None = None,
    path: Path = DEFAULT_SQLITE_CHECKPOINT_PATH,
    selected_job_ids: Sequence[str] = DEFAULT_SELECTED_JOB_IDS,
) -> dict[str, object]:
    dependencies = build_public_offline_dependencies(selected_job_ids)
    with sqlite_checkpointer(path) as saver:
        graph = build_orange_graph(dependencies=dependencies, checkpointer=saver)
        return OrangeGraphRunner(graph).start(
            create_initial_graph_state(
                selected_job_ids=selected_job_ids,
                checkpoint_mode="sqlite",
                workflow_id=workflow_id,
            )
        )


def resume_sqlite_demo(
    workflow_id: str,
    *,
    path: Path = DEFAULT_SQLITE_CHECKPOINT_PATH,
    selected_job_ids: Sequence[str] = DEFAULT_SELECTED_JOB_IDS,
) -> dict[str, object]:
    dependencies = build_public_offline_dependencies(selected_job_ids)
    with sqlite_checkpointer(path) as saver:
        graph = build_orange_graph(dependencies=dependencies, checkpointer=saver)
        return OrangeGraphRunner(graph).resume(
            workflow_id,
            ProfileReviewDecision(action=ProfileReviewAction.CONFIRM),
        )


def run_sqlite_restart_demo(
    *,
    path: Path = DEFAULT_SQLITE_CHECKPOINT_PATH,
    selected_job_ids: Sequence[str] = DEFAULT_SELECTED_JOB_IDS,
) -> tuple[dict[str, object], dict[str, object]]:
    paused = start_sqlite_demo(path=path, selected_job_ids=selected_job_ids)
    # start_sqlite_demo has closed its connection and discarded its graph runner.
    completed = resume_sqlite_demo(
        paused["workflow_id"],
        path=path,
        selected_job_ids=selected_job_ids,
    )
    return paused, completed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checkpoint",
        choices=("memory", "sqlite"),
        default="memory",
    )
    parser.add_argument(
        "--sqlite-action",
        choices=("start", "resume", "restart-demo"),
        default="restart-demo",
    )
    parser.add_argument("--workflow-id")
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        default=DEFAULT_SQLITE_CHECKPOINT_PATH,
    )
    args = parser.parse_args()

    if args.checkpoint == "memory":
        paused, completed = run_memory_demo()
        print(json.dumps({"paused": _safe_summary(paused), "completed": _safe_summary(completed)}, ensure_ascii=False, indent=2))
        return

    if args.sqlite_action == "start":
        paused = start_sqlite_demo(
            workflow_id=args.workflow_id,
            path=args.sqlite_path,
        )
        print(json.dumps({"paused": _safe_summary(paused)}, ensure_ascii=False, indent=2))
        return
    if args.sqlite_action == "resume":
        if not args.workflow_id:
            parser.error("--workflow-id is required for --sqlite-action resume")
        completed = resume_sqlite_demo(args.workflow_id, path=args.sqlite_path)
        print(json.dumps({"completed": _safe_summary(completed)}, ensure_ascii=False, indent=2))
        return
    paused, completed = run_sqlite_restart_demo(path=args.sqlite_path)
    print(json.dumps({"paused": _safe_summary(paused), "completed": _safe_summary(completed)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
