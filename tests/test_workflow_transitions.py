"""显式工作流边测试。"""

import pytest

from workflows.stages import InvalidWorkflowTransition, WorkflowStage


def test_valid_start_transition(orchestrator) -> None:
    state = orchestrator.engine.create_state("session_test")
    state = orchestrator.engine.transition(
        state,
        WorkflowStage.SELF_DISCOVERY,
        "测试合法路由。",
    )
    assert state.stage == WorkflowStage.SELF_DISCOVERY


def test_invalid_transition_is_rejected(orchestrator) -> None:
    state = orchestrator.engine.create_state("session_test")
    with pytest.raises(InvalidWorkflowTransition):
        orchestrator.engine.transition(state, WorkflowStage.REPORT, "测试非法跳转。")


def test_terminal_failure_is_supported(orchestrator) -> None:
    state = orchestrator.engine.create_state("session_test")
    failed = orchestrator.engine.fail(state, "公开安全测试错误")
    assert failed.stage == WorkflowStage.FAILED
    assert failed.errors == ["公开安全测试错误"]
