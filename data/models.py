"""Phase 1 可执行领域模型。

这些模型只表达结构、provenance 与验证规则，不包含 LLM 或真实匹配策略。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator
from pydantic_core import PydanticCustomError


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


class GoalType(str, Enum):
    """目标的语义范围；项目目标不能静默变成职业偏好。"""

    CAREER_GOAL = "career_goal"
    PROJECT_GOAL = "project_goal"
    LEARNING_GOAL = "learning_goal"

    @property
    def display_name_zh(self) -> str:
        return {
            self.CAREER_GOAL: "职业目标",
            self.PROJECT_GOAL: "项目目标",
            self.LEARNING_GOAL: "学习目标",
        }[self]


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


class MatchDimension(str, Enum):
    CAPABILITY_ALIGNMENT = "capability_alignment"
    INTEREST_ALIGNMENT = "interest_alignment"
    CAREER_PREFERENCE_ALIGNMENT = "career_preference_alignment"
    VALUE_WORKSTYLE_ALIGNMENT = "value_workstyle_alignment"
    EXPERIENCE_EVIDENCE = "experience_evidence"
    GROWTH_OPPORTUNITY = "growth_opportunity"

    @property
    def display_name_zh(self) -> str:
        return {
            self.CAPABILITY_ALIGNMENT: "能力匹配",
            self.INTEREST_ALIGNMENT: "兴趣匹配",
            self.CAREER_PREFERENCE_ALIGNMENT: "职业偏好匹配",
            self.VALUE_WORKSTYLE_ALIGNMENT: "价值观 / 工作方式匹配",
            self.EXPERIENCE_EVIDENCE: "经验与证据",
            self.GROWTH_OPPORTUNITY: "成长机会",
        }[self]


class MatchRelationType(str, Enum):
    STRONG_ALIGNMENT = "strong_alignment"
    PARTIAL_ALIGNMENT = "partial_alignment"
    EVIDENCE_MISSING = "evidence_missing"
    CONFIRMED_GAP = "confirmed_gap"
    EXPERIENCE_DEPTH_GAP = "experience_depth_gap"
    PREFERENCE_ALIGNMENT = "preference_alignment"
    POTENTIAL_FRICTION = "potential_friction"
    UNKNOWN = "unknown"

    @property
    def display_name_zh(self) -> str:
        return {
            self.STRONG_ALIGNMENT: "强证据匹配",
            self.PARTIAL_ALIGNMENT: "部分匹配",
            self.EVIDENCE_MISSING: "证据不足",
            self.CONFIRMED_GAP: "已确认能力缺口",
            self.EXPERIENCE_DEPTH_GAP: "经验深度差距",
            self.PREFERENCE_ALIGNMENT: "偏好匹配",
            self.POTENTIAL_FRICTION: "潜在摩擦",
            self.UNKNOWN: "仍未知",
        }[self]


class ActionType(str, Enum):
    VERIFY_EXISTING_CAPABILITY = "verify_existing_capability"
    BUILD_PORTFOLIO_EVIDENCE = "build_portfolio_evidence"
    DEEPEN_CAPABILITY = "deepen_capability"
    GAIN_PRACTICAL_EXPERIENCE = "gain_practical_experience"
    CLARIFY_PREFERENCE = "clarify_preference"
    INVESTIGATE_JOB_UNKNOWN = "investigate_job_unknown"


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
    MATCH_INSIGHT_STARTED = "match_insight_started"
    MATCH_CONTEXT_BUILT = "match_context_built"
    MATCH_LLM_EXTRACTION_COMPLETED = "match_llm_extraction_completed"
    MATCH_EVIDENCE_VALIDATION_COMPLETED = "match_evidence_validation_completed"
    MATCH_RESULT_ASSEMBLED = "match_result_assembled"
    MATCH_ACTIONS_VALIDATED = "match_actions_validated"
    MATCH_INSIGHT_COMPLETED = "match_insight_completed"
    PROFILE_CONFIRMATION_BLOCKED_MATCH = "profile_confirmation_blocked_match"
    GRAPH_RUN_STARTED = "graph_run_started"
    GRAPH_NODE_STARTED = "graph_node_started"
    GRAPH_NODE_COMPLETED = "graph_node_completed"
    GRAPH_INTERRUPTED = "graph_interrupted"
    GRAPH_RESUMED = "graph_resumed"
    GRAPH_FAILED = "graph_failed"
    GRAPH_COMPLETED = "graph_completed"
    CHECKPOINT_CREATED = "checkpoint_created"
    CHECKPOINT_RESUMED = "checkpoint_resumed"
    MEMORY_PROFILE_SAVED = "memory_profile_saved"
    MEMORY_CANDIDATE_CREATED = "memory_candidate_created"
    MEMORY_CONFIRMED = "memory_confirmed"
    MEMORY_SUPERSEDED = "memory_superseded"
    MEMORY_ARCHIVED = "memory_archived"
    MEMORY_RETRIEVED = "memory_retrieved"
    MEMORY_SUBJECT_PURGED = "memory_subject_purged"
    MEMORY_EMBEDDING_CREATED = "memory_embedding_created"
    MEMORY_VECTOR_INDEXED = "memory_vector_indexed"
    MEMORY_VECTOR_REMOVED = "memory_vector_removed"
    MEMORY_VECTOR_INDEX_REBUILT = "memory_vector_index_rebuilt"
    MEMORY_SEMANTIC_RETRIEVED = "memory_semantic_retrieved"
    MEMORY_HYBRID_RETRIEVED = "memory_hybrid_retrieved"
    MEMORY_VECTOR_STALE_FILTERED = "memory_vector_stale_filtered"


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
    goal_type: GoalType
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
    statement_id: str = Field(min_length=1)
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
    metadata: Dict[str, JsonValue] = Field(default_factory=dict)


class JobIntelligenceSignal(DomainModel):
    signal_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: List[str] = Field(min_length=1)
    inference_type: JobSignalInferenceType


class JobUncertainty(DomainModel):
    uncertainty_id: Optional[str] = None
    topic: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    importance: Severity = Severity.MEDIUM
    evidence_ids: List[str] = Field(default_factory=list)
    unknown_due_to_missing_information: bool = True


class JobIntelligenceRecord(DomainModel):
    intelligence_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    role_title: str = Field(min_length=1)
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
        signal_ids = [item.signal_id for item in linked_items if isinstance(item, JobIntelligenceSignal)]
        uncertainty_ids = [item.uncertainty_id for item in self.uncertainties]
        if len(signal_ids) != len(set(signal_ids)):
            raise ValueError("岗位情报 signal IDs 不能重复")
        if any(value is None for value in uncertainty_ids):
            raise ValueError("权威岗位情报 uncertainty 必须包含稳定 ID")
        if len(uncertainty_ids) != len(set(uncertainty_ids)):
            raise ValueError("岗位情报 uncertainty IDs 不能重复")
        return self


class MatchEvidenceLink(DomainModel):
    profile_signal_ids: List[str] = Field(default_factory=list)
    profile_evidence_ids: List[str] = Field(default_factory=list)
    job_signal_ids: List[str] = Field(default_factory=list)
    job_evidence_ids: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_unique_ids(self) -> "MatchEvidenceLink":
        for field_name in type(self).model_fields:
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise PydanticCustomError(
                    "duplicate_identifier",
                    f"{field_name} 不能包含重复 ID",
                )
        return self


class MatchInsight(DomainModel):
    insight_id: str = Field(min_length=1)
    dimension: MatchDimension
    relation_type: MatchRelationType
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_link: MatchEvidenceLink
    needs_user_review: bool = True

    @model_validator(mode="after")
    def validate_relation_evidence(self) -> "MatchInsight":
        both_sides = {
            MatchRelationType.STRONG_ALIGNMENT,
            MatchRelationType.PARTIAL_ALIGNMENT,
            MatchRelationType.CONFIRMED_GAP,
            MatchRelationType.EXPERIENCE_DEPTH_GAP,
            MatchRelationType.PREFERENCE_ALIGNMENT,
            MatchRelationType.POTENTIAL_FRICTION,
        }
        if self.relation_type in both_sides and not (
            self.evidence_link.profile_evidence_ids
            and self.evidence_link.job_evidence_ids
        ):
            raise ValueError(f"{self.relation_type.value} 必须同时包含用户与岗位证据")
        if (
            self.relation_type == MatchRelationType.EVIDENCE_MISSING
            and not self.evidence_link.job_evidence_ids
        ):
            raise ValueError("evidence_missing 必须包含岗位证据")
        if self.relation_type == MatchRelationType.UNKNOWN and not any(
            (
                self.evidence_link.profile_signal_ids,
                self.evidence_link.profile_evidence_ids,
                self.evidence_link.job_signal_ids,
                self.evidence_link.job_evidence_ids,
            )
        ):
            raise ValueError("unknown 必须至少关联一侧的信号或证据")
        return self


class EvidenceGap(MatchInsight):
    @model_validator(mode="after")
    def require_evidence_missing(self) -> "EvidenceGap":
        if self.relation_type != MatchRelationType.EVIDENCE_MISSING:
            raise ValueError("EvidenceGap 必须使用 evidence_missing")
        return self


class ConfirmedGap(MatchInsight):
    @model_validator(mode="after")
    def require_confirmed_gap(self) -> "ConfirmedGap":
        if self.relation_type != MatchRelationType.CONFIRMED_GAP:
            raise ValueError("ConfirmedGap 必须使用 confirmed_gap")
        return self


class ExperienceDepthGap(MatchInsight):
    @model_validator(mode="after")
    def require_experience_depth_gap(self) -> "ExperienceDepthGap":
        if self.relation_type != MatchRelationType.EXPERIENCE_DEPTH_GAP:
            raise ValueError("ExperienceDepthGap 必须使用 experience_depth_gap")
        return self


class ActionItem(DomainModel):
    action_id: str = Field(min_length=1)
    action_type: ActionType
    description: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    priority: Severity = Severity.MEDIUM
    expected_evidence: str = Field(min_length=1)
    target_label: str = Field(min_length=1)
    related_insight_ids: List[str] = Field(min_length=1)

    @model_validator(mode="after")
    def ensure_unique_related_insights(self) -> "ActionItem":
        if len(self.related_insight_ids) != len(set(self.related_insight_ids)):
            raise ValueError("ActionItem related_insight_ids 不能重复")
        return self


class MatchCoverageMetrics(DomainModel):
    required_capabilities_total: int = Field(ge=0)
    required_capabilities_with_user_evidence: int = Field(ge=0)
    required_capabilities_evidence_missing: int = Field(ge=0)
    confirmed_gap_count: int = Field(ge=0)


class MatchResult(DomainModel):
    """Evidence-first Phase 5 result; deliberately has no overall score."""

    match_id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    profile_version: int = Field(ge=1)
    intelligence_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    role_title: str = Field(min_length=1)
    alignments: List[MatchInsight] = Field(default_factory=list)
    partial_alignments: List[MatchInsight] = Field(default_factory=list)
    evidence_gaps: List[EvidenceGap] = Field(default_factory=list)
    confirmed_gaps: List[ConfirmedGap] = Field(default_factory=list)
    experience_depth_gaps: List[ExperienceDepthGap] = Field(default_factory=list)
    preference_alignments: List[MatchInsight] = Field(default_factory=list)
    potential_frictions: List[MatchInsight] = Field(default_factory=list)
    unknowns: List[MatchInsight] = Field(default_factory=list)
    action_items: List[ActionItem] = Field(default_factory=list)
    coverage_metrics: MatchCoverageMetrics
    analysis_metadata: Dict[str, JsonValue] = Field(default_factory=dict)
    limitations: List[str] = Field(
        default_factory=lambda: ["这是证据关系说明，不是职业适配分数、岗位排名或录用预测。"]
    )

    def insights(self) -> List[MatchInsight]:
        return [
            *self.alignments,
            *self.partial_alignments,
            *self.evidence_gaps,
            *self.confirmed_gaps,
            *self.experience_depth_gaps,
            *self.preference_alignments,
            *self.potential_frictions,
            *self.unknowns,
        ]


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


class GraphEvent(BaseEvent):
    """Safe orchestration event; semantic Agent events remain separate."""

    workflow_id: str = Field(min_length=1)
    node_name: Optional[str] = None


class CareerReport(DomainModel):
    report_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    profile_version: int = Field(ge=1)
    user_profile_summary: str = Field(min_length=1)
    role_insights: List[MatchResult] = Field(default_factory=list)
    actual_work: Dict[str, List[str]] = Field(default_factory=dict)
    why_it_may_fit: Dict[str, List[str]] = Field(default_factory=dict)
    evidence_missing: Dict[str, List[str]] = Field(default_factory=dict)
    confirmed_gaps: Dict[str, List[str]] = Field(default_factory=dict)
    experience_depth_gaps: Dict[str, List[str]] = Field(default_factory=dict)
    potential_friction: Dict[str, List[str]] = Field(default_factory=dict)
    unknowns: Dict[str, List[str]] = Field(default_factory=dict)
    next_actions: Dict[str, List[str]] = Field(default_factory=dict)
    workflow_summary: str = Field(min_length=1)
    limitations: List[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utc_now)
