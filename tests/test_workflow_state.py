"""WorkflowState 不变量测试。"""

import pytest
from pydantic import ValidationError

from data.models import UserProfile
from workflows.stages import WorkflowStage
from workflows.state import WorkflowState


def test_workflow_state_defaults() -> None:
    state = WorkflowState(session_id="session_test")
    assert state.stage == WorkflowStage.START
    assert state.profile_confirmed is False
    assert state.retry_count == 0


def test_state_rejects_confirmation_without_confirmed_profile() -> None:
    with pytest.raises(ValidationError):
        WorkflowState(
            session_id="session_test",
            user_profile=UserProfile(profile_id="profile_test"),
            profile_confirmed=True,
        )


def test_state_rejects_protected_stage_without_confirmation() -> None:
    with pytest.raises(ValidationError):
        WorkflowState(session_id="session_test", stage=WorkflowStage.JOB_INTELLIGENCE)
