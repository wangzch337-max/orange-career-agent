"""单次确定性运行的显式 Shared State。"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import Field, JsonValue, model_validator

from data.models import (
    AgentEvent,
    CareerReport,
    CourseRecord,
    DomainModel,
    JobIntelligenceRecord,
    JobRecord,
    MatchResult,
    ToolEvent,
    UserProfile,
    utc_now,
)
from workflows.stages import WorkflowStage


class WorkflowState(DomainModel):
    session_id: str = Field(min_length=1)
    stage: WorkflowStage = WorkflowStage.START
    user_input: Dict[str, JsonValue] = Field(default_factory=dict)
    course_records: List[CourseRecord] = Field(default_factory=list)
    user_profile: Optional[UserProfile] = None
    profile_confirmed: bool = False
    job_records: List[JobRecord] = Field(default_factory=list)
    job_intelligence: List[JobIntelligenceRecord] = Field(default_factory=list)
    match_results: List[MatchResult] = Field(default_factory=list)
    report: Optional[CareerReport] = None
    agent_events: List[AgentEvent] = Field(default_factory=list)
    tool_events: List[ToolEvent] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    retry_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_confirmation_invariant(self) -> "WorkflowState":
        if self.profile_confirmed:
            if self.user_profile is None or not self.user_profile.confirmed:
                raise ValueError("profile_confirmed=true 需要已确认的 UserProfile")
        protected_stages = {
            WorkflowStage.JOB_INTELLIGENCE,
            WorkflowStage.MATCH_INSIGHT,
            WorkflowStage.REPORT,
            WorkflowStage.COMPLETED,
        }
        if self.stage in protected_stages and not self.profile_confirmed:
            raise ValueError("画像未确认时不能进入岗位分析及后续阶段")
        return self

    def validated_copy(self, **updates: object) -> "WorkflowState":
        """通过完整 Pydantic 校验创建新状态，避免静默污染 Shared State。"""

        data = self.model_dump()
        data.update(updates)
        data["updated_at"] = utc_now()
        return WorkflowState.model_validate(data)
