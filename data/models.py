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


class InferenceType(str, Enum):
    """区分用户明确事实与基于证据形成、仍待确认的推断。"""

    EXPLICIT_FACT = "explicit_fact"
    EVIDENCE_SUPPORTED_INFERENCE = "evidence_supported_inference"


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


class RoleFamily(str, Enum):
    """Phase 4 Demo 岗位的轻量角色分类。"""

    PRODUCT_BUSINESS = "product_business"
    AI_APPLICATION_AGENT = "ai_application_agent"
    ML_DATA = "ml_data"
    SPECIALIZED_AI_ENGINEERING = "specialized_ai_engineering"
    SOLUTION_PLATFORM = "solution_platform"
    RESEARCH = "research"

    @property
    def display_name_zh(self) -> str:
        return {
            self.PRODUCT_BUSINESS: "产品与商业",
            self.AI_APPLICATION_AGENT: "AI应用与Agent",
            self.ML_DATA: "机器学习与数据",
            self.SPECIALIZED_AI_ENGINEERING: "专项AI工程",
            self.SOLUTION_PLATFORM: "AI解决方案与平台",
            self.RESEARCH: "AI研究",
        }[self]


class Region(str, Enum):
    """仅用于岗位地理筛选的功能性区域字段。"""

    MAINLAND_CHINA = "mainland_china"
    HONG_KONG = "hong_kong"
    MACAU = "macau"
    TAIWAN = "taiwan"


class JobSignalInferenceType(str, Enum):
    """区分岗位原文事实与证据支持的岗位解释。"""

    EXPLICIT_JOB_FACT = "explicit_job_fact"
    EVIDENCE_SUPPORTED_JOB_INFERENCE = "evidence_supported_job_inference"


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
    SOURCE_EVIDENCE_BUILT = "source_evidence_built"
    LLM_EXTRACTION_COMPLETED = "llm_extraction_completed"
    EVIDENCE_VALIDATION_COMPLETED = "evidence_validation_completed"
    PROFILE_ASSEMBLED = "profile_assembled"
    PROFILE_CONFIRMATION_REQUIRED = "profile_confirmation_required"
    CLARIFICATION_QUESTIONS_CREATED = "clarification_questions_created"
    JOB_INTELLIGENCE_STARTED = "job_intelligence_started"
    JOB_EVIDENCE_BUILT = "job_evidence_built"
    JOB_LLM_EXTRACTION_COMPLETED = "job_llm_extraction_completed"
    JOB_EVIDENCE_VALIDATION_COMPLETED = "job_evidence_validation_completed"
    JOB_INTELLIGENCE_ASSEMBLED = "job_intelligence_assembled"
    JOB_UNCERTAINTIES_IDENTIFIED = "job_uncertainties_identified"
    JOB_INTELLIGENCE_COMPLETED = "job_intelligence_completed"


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
    inference_type: InferenceType = InferenceType.EXPLICIT_FACT
    needs_confirmation: bool = True
    confirmed_by_user: bool = False


class CandidateSkill(EvidenceLinkedModel):
    skill_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: Optional[str] = None
    level: Optional[str] = None

    @property
    def name(self) -> str:
        return self.label


class InterestSignal(EvidenceLinkedModel):
    interest_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: Optional[str] = None
    strength: SignalStrength = SignalStrength.MEDIUM


class ValueSignal(EvidenceLinkedModel):
    value_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: Optional[str] = None
    importance: Optional[int] = Field(default=None, ge=1, le=5)


class Goal(DomainModel):
    goal_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: Optional[str] = None
    horizon: GoalHorizon = GoalHorizon.SHORT
    status: GoalStatus = GoalStatus.DRAFT
    success_signal: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_type: EvidenceSourceType = EvidenceSourceType.EXPLICIT_USER_INPUT
    inference_type: InferenceType = InferenceType.EXPLICIT_FACT
    needs_confirmation: bool = True
    confirmed_by_user: bool = False


class EvidenceBackedStatement(EvidenceLinkedModel):
    text: str = Field(min_length=1)


class CareerPreference(EvidenceLinkedModel):
    preference_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: Optional[str] = None


class ProfileUncertainty(DomainModel):
    topic: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    evidence_ids: List[str] = Field(default_factory=list)
    importance: Severity = Severity.MEDIUM
    needs_user_input: bool = True


class ClarificationQuestion(DomainModel):
    question_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    priority: Severity = Severity.MEDIUM
    related_evidence_ids: List[str] = Field(default_factory=list)


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
    career_preferences: List[CareerPreference] = Field(default_factory=list)
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
            *self.career_preferences,
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
            "career_preferences",
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
    role_family: RoleFamily
    organization: str = Field(min_length=1)
    city: str = Field(min_length=1)
    region: Region
    employment_type: EmploymentType
    description: str = Field(min_length=1)
    responsibilities: List[str] = Field(default_factory=list)
    requirements: List[str] = Field(default_factory=list)
    preferred_qualifications: List[str] = Field(default_factory=list)
    technology_tags: List[str] = Field(default_factory=list)
    language_requirements: List[str] = Field(default_factory=list)
    source_type: EvidenceSourceType = EvidenceSourceType.SYSTEM_FIXTURE
    source_name: str = Field(min_length=1)
    source_url: Optional[str] = None
    # Phase 1 exact-overlap compatibility only; Phase 5 will replace this stub input.
    skills: List[str] = Field(default_factory=list)
    metadata: Dict[str, JsonValue] = Field(default_factory=dict)


class JobIntelligenceSignal(DomainModel):
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: List[str] = Field(min_length=1)
    inference_type: JobSignalInferenceType


class JobUncertainty(DomainModel):
    topic: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    importance: Severity = Severity.MEDIUM
    evidence_ids: List[str] = Field(default_factory=list)
    unknown_due_to_missing_information: bool = True


class JobIntelligenceRecord(DomainModel):
    intelligence_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    role_family: RoleFamily
    actual_work: List[JobIntelligenceSignal] = Field(default_factory=list)
    required_capabilities: List[JobIntelligenceSignal] = Field(default_factory=list)
    preferred_capabilities: List[JobIntelligenceSignal] = Field(default_factory=list)
    technology_signals: List[JobIntelligenceSignal] = Field(default_factory=list)
    work_style: List[JobIntelligenceSignal] = Field(default_factory=list)
    collaboration_context: List[JobIntelligenceSignal] = Field(default_factory=list)
    growth_exposure: List[JobIntelligenceSignal] = Field(default_factory=list)
    potential_friction: List[JobIntelligenceSignal] = Field(default_factory=list)
    uncertainties: List[JobUncertainty] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    analysis_metadata: Dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_evidence_links(self) -> "JobIntelligenceRecord":
        available_ids = {item.id for item in self.evidence}
        linked_items = [
            *self.actual_work,
            *self.required_capabilities,
            *self.preferred_capabilities,
            *self.technology_signals,
            *self.work_style,
            *self.collaboration_context,
            *self.growth_exposure,
            *self.potential_friction,
            *self.uncertainties,
        ]
        referenced_ids = {evidence_id for item in linked_items for evidence_id in item.evidence_ids}
        missing = (set(self.evidence_ids) | referenced_ids) - available_ids
        if missing:
            raise ValueError(f"岗位情报引用了不存在的 evidence IDs: {sorted(missing)}")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("岗位情报 evidence_ids 不能重复")
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
