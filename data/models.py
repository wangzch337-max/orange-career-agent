"""Phase 1 可执行领域模型。

这些模型只表达结构、provenance 与验证规则，不包含 LLM 或真实匹配策略。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


def utc_now() -> datetime:
    """返回带时区的 UTC 时间。"""

    return datetime.now(timezone.utc)


class DomainModel(BaseModel):
    """所有领域模型的严格基础配置。"""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class EvidenceSourceType(str, Enum):
    """证据来源；推断不能冒充明确事实。"""

    EXPLICIT_USER_INPUT = "explicit_user_input"
    COURSE = "course"
    PROJECT = "project"
    CONVERSATION = "conversation"
    JOB_DESCRIPTION = "job_description"
    MODEL_INFERENCE = "model_inference"
    SYSTEM_FIXTURE = "system_fixture"


class ProfileStatus(str, Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"


class SignalStrength(str, Enum):
    WEAK = "weak"
    MEDIUM = "medium"
    STRONG = "strong"


class GoalHorizon(str, Enum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class GoalStatus(str, Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    PAUSED = "paused"


class EmploymentType(str, Enum):
    INTERNSHIP = "internship"
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"


class MatchMethod(str, Enum):
    """Phase 1 仅允许精确标签重合。"""

    EXACT_OVERLAP = "exact_overlap"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EventType(str, Enum):
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    TOOL_CALLED = "tool_called"
    TOOL_COMPLETED = "tool_completed"
    ROUTING_DECISION = "routing_decision"
    VALIDATION_FAILED = "validation_failed"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"


class AgentName(str, Enum):
    SELF_DISCOVERY = "Self-Discovery Agent"
    JOB_INTELLIGENCE = "Job Intelligence Agent"
    MATCH_INSIGHT = "Match & Insight Agent"
    ORCHESTRATOR = "Orchestrator Agent"


class EvidenceItem(DomainModel):
    """一个稳定、可定位且可公开展示的证据单元。"""

    id: str = Field(min_length=1, description="工作流或 fixture 内的稳定证据 ID")
    source_type: EvidenceSourceType
    source_name: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: Dict[str, JsonValue] = Field(default_factory=dict)

    @property
    def evidence_id(self) -> str:
        """兼容概念契约中的 evidence_id 命名。"""

        return self.id


class EvidenceLinkedModel(DomainModel):
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: List[str] = Field(default_factory=list)
    source_type: EvidenceSourceType
    confirmed_by_user: bool = False


class CandidateSkill(EvidenceLinkedModel):
    skill_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    level: Optional[str] = None

    @property
    def name(self) -> str:
        return self.label


class InterestSignal(EvidenceLinkedModel):
    interest_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    strength: SignalStrength = SignalStrength.MEDIUM


class ValueSignal(EvidenceLinkedModel):
    value_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    importance: Optional[int] = Field(default=None, ge=1, le=5)


class Goal(DomainModel):
    goal_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    horizon: GoalHorizon = GoalHorizon.SHORT
    status: GoalStatus = GoalStatus.DRAFT
    success_signal: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)
    source_type: EvidenceSourceType = EvidenceSourceType.EXPLICIT_USER_INPUT
    confirmed_by_user: bool = False


class EvidenceBackedStatement(EvidenceLinkedModel):
    text: str = Field(min_length=1)


class UserProfile(DomainModel):
    """可修订、可确认且保留证据引用的用户画像。"""

    profile_id: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)
    status: ProfileStatus = ProfileStatus.DRAFT
    education_summary: Optional[str] = None
    skills: List[CandidateSkill] = Field(default_factory=list)
    interests: List[InterestSignal] = Field(default_factory=list)
    values: List[ValueSignal] = Field(default_factory=list)
    goals: List[Goal] = Field(default_factory=list)
    strengths: List[EvidenceBackedStatement] = Field(default_factory=list)
    development_areas: List[EvidenceBackedStatement] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)
    confirmed: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    confirmed_at: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_evidence_links(self) -> "UserProfile":
        available_ids = {item.id for item in self.evidence}
        referenced_ids = set()
        linked_items = [
            *self.skills,
            *self.interests,
            *self.values,
            *self.goals,
            *self.strengths,
            *self.development_areas,
        ]
        for item in linked_items:
            referenced_ids.update(item.evidence_ids)
        missing = referenced_ids - available_ids
        if missing:
            raise ValueError(f"画像引用了不存在的 evidence IDs: {sorted(missing)}")
        if self.confirmed != (self.status == ProfileStatus.CONFIRMED):
            raise ValueError("confirmed 与 status 必须保持一致")
        if self.confirmed and self.confirmed_at is None:
            raise ValueError("已确认画像必须包含 confirmed_at")
        if not self.confirmed and self.confirmed_at is not None:
            raise ValueError("未确认画像不能包含 confirmed_at")
        return self

    def create_revision(self, **changes: object) -> "UserProfile":
        """返回下一版本，不改变当前对象的历史含义。"""

        protected = {"profile_id", "version", "created_at", "confirmed", "confirmed_at", "status"}
        invalid = protected.intersection(changes)
        if invalid:
            raise ValueError(f"修订不能覆盖受保护字段: {sorted(invalid)}")
        revision_data = self.model_dump()
        revision_data.update(changes)
        revision_data.update(
            version=self.version + 1,
            status=ProfileStatus.DRAFT,
            confirmed=False,
            confirmed_at=None,
            updated_at=utc_now(),
        )
        return UserProfile.model_validate(revision_data)

    def confirm(self) -> "UserProfile":
        """返回同一版本的已确认副本，原草案保持不变。"""

        now = utc_now()
        data = self.model_dump()
        for field_name in (
            "skills",
            "interests",
            "values",
            "goals",
            "strengths",
            "development_areas",
        ):
            data[field_name] = [
                {**item, "confirmed_by_user": True} for item in data[field_name]
            ]
        data.update(
            status=ProfileStatus.CONFIRMED,
            confirmed=True,
            confirmed_at=now,
            updated_at=now,
        )
        return UserProfile.model_validate(data)


class CourseRecord(DomainModel):
    course_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    tags: List[str] = Field(default_factory=list)
    source: str = "phase_1_fixture"


class JobRecord(DomainModel):
    job_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    organization: str = Field(min_length=1)
    location: str = Field(min_length=1)
    region: str = Field(min_length=1)
    employment_type: EmploymentType
    description: str = Field(min_length=1)
    requirements: List[str] = Field(default_factory=list)
    source: str = Field(min_length=1)
    source_url: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    language: List[str] = Field(default_factory=list)
    metadata: Dict[str, JsonValue] = Field(default_factory=dict)


class JobIntelligenceRecord(DomainModel):
    intelligence_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    canonical_role: str = Field(min_length=1)
    actual_work: List[str] = Field(default_factory=list)
    required_capabilities: List[str] = Field(default_factory=list)
    preferred_capabilities: List[str] = Field(default_factory=list)
    work_style: List[str] = Field(default_factory=list)
    career_path: List[str] = Field(default_factory=list)
    advantages: List[str] = Field(default_factory=list)
    potential_drawbacks: List[str] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_evidence_links(self) -> "JobIntelligenceRecord":
        available_ids = {item.id for item in self.evidence}
        missing = set(self.evidence_ids) - available_ids
        if missing:
            raise ValueError(f"岗位情报引用了不存在的 evidence IDs: {sorted(missing)}")
        return self


class MatchDimension(DomainModel):
    name: str = Field(min_length=1)
    method: MatchMethod = MatchMethod.EXACT_OVERLAP
    summary: str = Field(min_length=1)
    matched_items: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)


class GapItem(DomainModel):
    gap_id: str = Field(min_length=1)
    capability: str = Field(min_length=1)
    current_evidence_ids: List[str] = Field(default_factory=list)
    required_evidence_ids: List[str] = Field(default_factory=list)
    severity: Severity = Severity.MEDIUM
    interpretation: str = Field(min_length=1)


class ActionItem(DomainModel):
    action_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    priority: Severity = Severity.MEDIUM
    time_horizon: Optional[str] = None
    success_criteria: str = Field(min_length=1)
    related_gap_ids: List[str] = Field(default_factory=list)


class MatchResult(DomainModel):
    """Phase 1 exact-overlap 数据流结果；不包含真实质量分数。"""

    match_id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    profile_version: int = Field(ge=1)
    intelligence_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    role_title: str = Field(min_length=1)
    dimensions: List[MatchDimension] = Field(default_factory=list)
    why_it_may_fit: List[str] = Field(default_factory=list)
    evidence_of_fit: List[str] = Field(default_factory=list)
    potential_friction: List[str] = Field(default_factory=list)
    capability_gaps: List[GapItem] = Field(default_factory=list)
    suggested_actions: List[ActionItem] = Field(default_factory=list)
    limitations: List[str] = Field(
        default_factory=lambda: ["Phase 1 仅使用精确标签重合验证数据流，不代表真实职业适配度。"]
    )


class BaseEvent(DomainModel):
    event_id: str = Field(min_length=1)
    timestamp: datetime = Field(default_factory=utc_now)
    event_type: EventType
    component: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    safe_metadata: Dict[str, JsonValue] = Field(default_factory=dict)
    duration_ms: Optional[int] = Field(default=None, ge=0)


class AgentEvent(BaseEvent):
    agent_name: AgentName
    evidence_ids: List[str] = Field(default_factory=list)


class ToolEvent(BaseEvent):
    tool_name: str = Field(min_length=1)
    error_code: Optional[str] = None


class CareerReport(DomainModel):
    report_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    profile_version: int = Field(ge=1)
    user_profile_summary: str = Field(min_length=1)
    role_insights: List[MatchResult] = Field(default_factory=list)
    actual_work: Dict[str, List[str]] = Field(default_factory=dict)
    evidence_of_fit: Dict[str, List[str]] = Field(default_factory=dict)
    potential_friction: Dict[str, List[str]] = Field(default_factory=dict)
    capability_gaps: List[GapItem] = Field(default_factory=list)
    suggested_actions: List[ActionItem] = Field(default_factory=list)
    workflow_summary: str = Field(min_length=1)
    limitations: List[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utc_now)
