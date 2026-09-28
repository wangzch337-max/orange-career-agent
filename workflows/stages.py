"""工作流阶段、允许边和领域异常。"""

from enum import Enum
from typing import Dict, FrozenSet


class WorkflowStage(str, Enum):
    START = "start"
    SELF_DISCOVERY = "self_discovery"
    AWAITING_PROFILE_CONFIRMATION = "awaiting_profile_confirmation"
    JOB_INTELLIGENCE = "job_intelligence"
    MATCH_INSIGHT = "match_insight"
    REPORT = "report"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowError(RuntimeError):
    """工作流领域错误基类。"""


class InvalidWorkflowTransition(WorkflowError):
    """目标阶段不属于显式允许边。"""


class ProfileNotConfirmedError(WorkflowError):
    """尝试在画像未确认时进入岗位情报阶段。"""


class FixtureLoadError(WorkflowError):
    """公开 fixture 不存在或不符合 schema。"""


VALID_TRANSITIONS: Dict[WorkflowStage, FrozenSet[WorkflowStage]] = {
    WorkflowStage.START: frozenset({WorkflowStage.SELF_DISCOVERY, WorkflowStage.FAILED}),
    WorkflowStage.SELF_DISCOVERY: frozenset(
        {WorkflowStage.AWAITING_PROFILE_CONFIRMATION, WorkflowStage.FAILED}
    ),
    WorkflowStage.AWAITING_PROFILE_CONFIRMATION: frozenset(
        {WorkflowStage.SELF_DISCOVERY, WorkflowStage.JOB_INTELLIGENCE, WorkflowStage.FAILED}
    ),
    WorkflowStage.JOB_INTELLIGENCE: frozenset(
        {WorkflowStage.MATCH_INSIGHT, WorkflowStage.FAILED}
    ),
    WorkflowStage.MATCH_INSIGHT: frozenset({WorkflowStage.REPORT, WorkflowStage.FAILED}),
    WorkflowStage.REPORT: frozenset({WorkflowStage.COMPLETED, WorkflowStage.FAILED}),
    WorkflowStage.COMPLETED: frozenset({WorkflowStage.FAILED}),
    WorkflowStage.FAILED: frozenset(),
}


def ensure_transition_allowed(current: WorkflowStage, target: WorkflowStage) -> None:
    """校验一条显式状态边。"""

    if target not in VALID_TRANSITIONS[current]:
        raise InvalidWorkflowTransition(f"不允许从 {current.value} 转移到 {target.value}")
