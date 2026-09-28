"""不可跳过的画像确认门测试。"""

import pytest

from workflows.stages import ProfileNotConfirmedError, WorkflowStage


def test_gate_blocks_job_intelligence_before_confirmation(orchestrator, paused_state) -> None:
    assert paused_state.stage == WorkflowStage.AWAITING_PROFILE_CONFIRMATION
    assert paused_state.job_intelligence == []
    with pytest.raises(ProfileNotConfirmedError):
        orchestrator.engine.transition(
            paused_state,
            WorkflowStage.JOB_INTELLIGENCE,
            "不应成功。",
        )


def test_confirmation_permits_completion(orchestrator, paused_state) -> None:
    completed = orchestrator.confirm_and_continue(paused_state)
    assert completed.stage == WorkflowStage.COMPLETED
    assert completed.profile_confirmed is True
    assert len(completed.job_intelligence) == 20


def test_revision_returns_to_self_discovery_with_next_version(orchestrator, paused_state) -> None:
    revised = orchestrator.engine.request_profile_revision(
        paused_state,
        education_summary="开发者修订的匿名摘要",
    )
    assert revised.stage == WorkflowStage.SELF_DISCOVERY
    assert revised.user_profile.version == 2
    assert revised.profile_confirmed is False
    paused_again = orchestrator.run(revised)
    assert paused_again.stage == WorkflowStage.AWAITING_PROFILE_CONFIRMATION
    assert paused_again.user_profile.version == 2
