"""核心模型 JSON 往返测试。"""

from workflows.state import WorkflowState


def test_workflow_state_json_round_trip(completed_state) -> None:
    payload = completed_state.model_dump_json()
    restored = WorkflowState.model_validate_json(payload)
    assert restored == completed_state
    assert restored.report is not None


def test_profile_json_round_trip(paused_state) -> None:
    profile = paused_state.user_profile
    restored = type(profile).model_validate_json(profile.model_dump_json())
    assert restored == profile
