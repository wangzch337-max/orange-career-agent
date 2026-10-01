"""Provider-independent, evidence-first Phase 5 Match & Insight Agent."""

from __future__ import annotations

from typing import Dict, Optional

from agents.base import BaseAgent, record_agent_event
from agents.match_context import MatchContextBuilder
from agents.match_insight_assembler import MatchInsightAssembler
from agents.match_insight_models import (
    JobSignalCategory,
    MatchActionCandidate,
    MatchContext,
    MatchInsightCandidate,
    MatchInsightExtraction,
    ProfileSignalCategory,
    build_match_insight_response_model,
    validate_match_insight_candidate,
)
from data.models import (
    ActionType,
    AgentName,
    EventType,
    GoalType,
    JobIntelligenceRecord,
    MatchDimension,
    MatchRelationType,
    MatchResult,
    Severity,
    UserProfile,
)
from providers.base import LLMProvider
from providers.models import GenerationOptions, StructuredLLMResponse
from providers.prompts import (
    MATCH_INSIGHT_PROMPT_NAME,
    MATCH_INSIGHT_PROMPT_VERSION,
    build_match_insight_messages,
    load_match_insight_prompt,
)
from workflows.stages import ProfileNotConfirmedError, WorkflowStage
from workflows.state import WorkflowState
from observability.instrumentation import observe
from observability.models import DiagnosticComponent as DC


_DEPTH_GAP_JOBS = {"job_007", "job_011", "job_018"}
_HANDS_ON_JOBS = {"job_001", "job_003", "job_007", "job_008", "job_009", "job_011", "job_015", "job_016", "job_018", "job_019", "job_020"}
_CLIENT_FACING_JOBS = {"job_004", "job_017"}


def _signal_ids(
    *,
    profile_signal=None,
    job_signal=None,
) -> dict[str, list[str]]:
    return {
        "profile_signal_ids": [profile_signal.signal_id] if profile_signal else [],
        "job_signal_ids": [job_signal.signal_id] if job_signal else [],
    }


def public_offline_match_extraction(context: MatchContext) -> MatchInsightExtraction:
    """Build deterministic canned candidates before FakeLLMProvider runs."""

    profile_skills = {
        item.label.casefold(): item
        for item in context.profile_signals
        if item.category == ProfileSignalCategory.SKILL
    }
    profile_development = [
        item
        for item in context.profile_signals
        if item.category == ProfileSignalCategory.DEVELOPMENT_AREA
    ]
    preferences = [
        item
        for item in context.profile_signals
        if item.category == ProfileSignalCategory.CAREER_PREFERENCE
    ]
    goals = [
        item
        for item in context.profile_signals
        if item.category == ProfileSignalCategory.GOAL
        and item.goal_type in {GoalType.CAREER_GOAL, GoalType.LEARNING_GOAL}
    ]
    requirements = [
        item
        for item in context.job_signals
        if item.category == JobSignalCategory.REQUIRED_CAPABILITY
    ]
    actual_work = [
        item for item in context.job_signals if item.category == JobSignalCategory.ACTUAL_WORK
    ]
    growth = [
        item for item in context.job_signals if item.category == JobSignalCategory.GROWTH_EXPOSURE
    ]
    frictions = [
        item for item in context.job_signals if item.category == JobSignalCategory.POTENTIAL_FRICTION
    ]
    uncertainties = [
        item for item in context.job_signals if item.category == JobSignalCategory.UNCERTAINTY
    ]

    alignments: list[MatchInsightCandidate] = []
    gaps: list[MatchInsightCandidate] = []
    friction_candidates: list[MatchInsightCandidate] = []
    unknowns: list[MatchInsightCandidate] = []
    actions: list[MatchActionCandidate] = []
    sequence = 0

    def candidate(
        relation: MatchRelationType,
        dimension: MatchDimension,
        title: str,
        description: str,
        signal_ids: dict[str, list[str]],
        confidence: float,
    ) -> MatchInsightCandidate:
        nonlocal sequence
        sequence += 1
        return validate_match_insight_candidate(
            {
                "candidate_id": f"{context.job_id}_insight_{sequence:03d}",
                "dimension": dimension,
                "relation_type": relation,
                "title": title,
                "description": description,
                "confidence": confidence,
                **signal_ids,
            }
        )

    for requirement in requirements:
        matching_skill = profile_skills.get(requirement.label.casefold())
        development = next(
            (
                item
                for item in profile_development
                if requirement.label.casefold() in item.label.casefold()
            ),
            None,
        )
        if matching_skill:
            alignments.append(
                candidate(
                    MatchRelationType.STRONG_ALIGNMENT,
                    MatchDimension.CAPABILITY_ALIGNMENT,
                    f"已有证据支持 {requirement.label}",
                    "已确认用户技能与明确岗位要求直接对应。",
                    _signal_ids(profile_signal=matching_skill, job_signal=requirement),
                    0.95,
                )
            )
        elif development:
            gaps.append(
                candidate(
                    MatchRelationType.CONFIRMED_GAP,
                    MatchDimension.CAPABILITY_ALIGNMENT,
                    f"已确认的 {requirement.label} 能力缺口",
                    "用户确认的发展领域与岗位明确要求相对应。",
                    _signal_ids(profile_signal=development, job_signal=requirement),
                    0.92,
                )
            )
        else:
            gaps.append(
                candidate(
                    MatchRelationType.EVIDENCE_MISSING,
                    MatchDimension.CAPABILITY_ALIGNMENT,
                    f"缺少验证 {requirement.label} 的画像证据",
                    "当前确认画像没有足够证据判断该岗位要求；这不代表能力较弱。",
                    _signal_ids(job_signal=requirement),
                    0.98,
                )
            )

    general_skill = next(iter(profile_skills.values()), None)
    if context.job_id in _DEPTH_GAP_JOBS and general_skill and actual_work:
        depth = candidate(
            MatchRelationType.EXPERIENCE_DEPTH_GAP,
            MatchDimension.EXPERIENCE_EVIDENCE,
            "相关基础存在，但生产范围尚未得到验证",
            "现有用户证据显示相关基础；岗位证据涉及更深的交付范围。",
            _signal_ids(profile_signal=general_skill, job_signal=actual_work[-1]),
            0.76,
        )
        gaps.append(depth)

    hands_on_preference = next(
        (item for item in preferences if "hands-on" in item.label.casefold()), None
    )
    if context.job_id in _HANDS_ON_JOBS and hands_on_preference and actual_work:
        alignments.append(
            candidate(
                MatchRelationType.PREFERENCE_ALIGNMENT,
                MatchDimension.CAREER_PREFERENCE_ALIGNMENT,
                "动手实现偏好与岗位工作相符",
                "已确认的动手实现偏好与明确岗位工作存在对应。",
                _signal_ids(profile_signal=hands_on_preference, job_signal=actual_work[0]),
                0.88,
            )
        )

    limited_client_preference = next(
        (item for item in preferences if "client-facing" in item.label.casefold()), None
    )
    if context.job_id in _CLIENT_FACING_JOBS and limited_client_preference:
        job_friction = frictions[0] if frictions else actual_work[0]
        friction_candidates.append(
            candidate(
                MatchRelationType.POTENTIAL_FRICTION,
                MatchDimension.VALUE_WORKSTYLE_ALIGNMENT,
                "客户沟通范围需要进一步确认",
                "用户明确偏好较少客户沟通，而岗位证据包含客户协作特征。",
                _signal_ids(profile_signal=limited_client_preference, job_signal=job_friction),
                0.86,
            )
        )

    if goals and growth:
        alignments.append(
            candidate(
                MatchRelationType.PARTIAL_ALIGNMENT,
                MatchDimension.GROWTH_OPPORTUNITY,
                "岗位成长暴露与已确认目标相关",
                "岗位可能提供与目标相关的经历，但不能据此推断长期职业适配。",
                _signal_ids(profile_signal=goals[0], job_signal=growth[0]),
                0.75,
            )
        )

    if uncertainties:
        unknowns.append(
            candidate(
                MatchRelationType.UNKNOWN,
                MatchDimension.EXPERIENCE_EVIDENCE,
                f"岗位信息仍未知：{uncertainties[0].label}",
                uncertainties[0].description,
                _signal_ids(job_signal=uncertainties[0]),
                1.0,
            )
        )

    first_evidence_gap = next(
        (item for item in gaps if item.relation_type == MatchRelationType.EVIDENCE_MISSING),
        None,
    )
    if first_evidence_gap:
        target = next(
            item.label
            for item in requirements
            if item.signal_id in first_evidence_gap.job_signal_ids
        )
        actions.append(
            MatchActionCandidate(
                action_id=f"{context.job_id}_action_verify_001",
                action_type=ActionType.VERIFY_EXISTING_CAPABILITY,
                description=f"检查现有课程或项目中是否已有 {target} 的可验证证据。",
                related_insight_ids=[first_evidence_gap.candidate_id],
                priority=Severity.MEDIUM,
                expected_evidence=f"一条可复查的 {target} 项目、课程或作品说明",
                rationale="证据缺失不等于能力缺失，先验证现有经历。",
                target_label=target,
            )
        )
    first_confirmed_gap = next(
        (item for item in gaps if item.relation_type == MatchRelationType.CONFIRMED_GAP),
        None,
    )
    if first_confirmed_gap:
        target = next(
            item.label
            for item in requirements
            if item.signal_id in first_confirmed_gap.job_signal_ids
        )
        actions.append(
            MatchActionCandidate(
                action_id=f"{context.job_id}_action_deepen_001",
                action_type=ActionType.DEEPEN_CAPABILITY,
                description=f"针对已确认限制深化 {target} 能力。",
                related_insight_ids=[first_confirmed_gap.candidate_id],
                priority=Severity.HIGH,
                expected_evidence=f"一个可复查的 {target} 实践产物",
                rationale="该行动只针对用户已确认的发展领域。",
                target_label=target,
            )
        )
    first_depth_gap = next(
        (item for item in gaps if item.relation_type == MatchRelationType.EXPERIENCE_DEPTH_GAP),
        None,
    )
    if first_depth_gap:
        target = next(
            item.label
            for item in actual_work
            if item.signal_id in first_depth_gap.job_signal_ids
        )
        actions.append(
            MatchActionCandidate(
                action_id=f"{context.job_id}_action_experience_001",
                action_type=ActionType.GAIN_PRACTICAL_EXPERIENCE,
                description="通过有明确范围的实践验证更深交付经验。",
                related_insight_ids=[first_depth_gap.candidate_id],
                priority=Severity.MEDIUM,
                expected_evidence="一个说明范围、约束与验证结果的实践记录",
                rationale="已有相关基础，但经验深度尚未得到证明。",
                target_label=target,
            )
        )
    if unknowns:
        actions.append(
            MatchActionCandidate(
                action_id=f"{context.job_id}_action_unknown_001",
                action_type=ActionType.INVESTIGATE_JOB_UNKNOWN,
                description=f"通过正式岗位资料核实 {uncertainties[0].label}。",
                related_insight_ids=[unknowns[0].candidate_id],
                priority=Severity.LOW,
                expected_evidence="正式岗位说明或经授权的招聘方答复",
                rationale="缺失岗位信息必须保持未知，需从正式来源核实。",
                target_label=uncertainties[0].label,
            )
        )
    if friction_candidates and limited_client_preference:
        actions.append(
            MatchActionCandidate(
                action_id=f"{context.job_id}_action_preference_001",
                action_type=ActionType.CLARIFY_PREFERENCE,
                description="确认可接受的客户沟通频率与形式。",
                related_insight_ids=[friction_candidates[0].candidate_id],
                priority=Severity.MEDIUM,
                expected_evidence="一条更具体且经用户确认的客户沟通偏好",
                rationale="潜在摩擦需要用户进一步界定偏好，而不是由系统替用户决定。",
                target_label=limited_client_preference.label,
            )
        )

    return MatchInsightExtraction(
        candidate_alignments=alignments,
        candidate_gaps=gaps,
        candidate_frictions=friction_candidates,
        candidate_unknowns=unknowns,
        candidate_actions=actions,
    )


class MatchInsightAgent(BaseAgent):
    name = AgentName.MATCH_INSIGHT

    def __init__(
        self,
        llm_provider: LLMProvider,
        *,
        context_builder: Optional[MatchContextBuilder] = None,
        assembler: Optional[MatchInsightAssembler] = None,
        generation_options: Optional[GenerationOptions] = None,
    ) -> None:
        self.llm_provider = llm_provider
        self.context_builder = context_builder or MatchContextBuilder()
        self.assembler = assembler or MatchInsightAssembler()
        self.generation_options = generation_options or GenerationOptions(
            model="fake-match-insight-v1",
            max_output_tokens=4096,
            max_retries=0,
        )

    @observe(DC.MATCH_INSIGHT, "match_run")
    def analyze_with_details(
        self,
        profile: UserProfile,
        intelligence: JobIntelligenceRecord,
    ) -> tuple[MatchResult, StructuredLLMResponse, MatchContext]:
        if not profile.confirmed:
            raise ProfileNotConfirmedError("Match & Insight 只接受已确认 UserProfile")
        context = self.context_builder.build(profile, intelligence)
        response_model = build_match_insight_response_model(context)
        response = self.llm_provider.generate_structured(
            build_match_insight_messages(load_match_insight_prompt(), context),
            response_model,
            self.generation_options,
            prompt_name=MATCH_INSIGHT_PROMPT_NAME,
            prompt_version=MATCH_INSIGHT_PROMPT_VERSION,
        )
        response.data.validate_context(context)
        metadata: Dict[str, object] = response.safe_metadata()
        metadata.update(
            relation_counts=response.data.relation_counts(),
            action_count=len(response.data.candidate_actions),
        )
        return (
            self.assembler.assemble(
                profile=profile,
                context=context,
                extraction=response.data,
                analysis_metadata=metadata,
            ),
            response,
            context,
        )

    def analyze(
        self,
        profile: UserProfile,
        intelligence: JobIntelligenceRecord,
    ) -> MatchResult:
        result, _, _ = self.analyze_with_details(profile, intelligence)
        return result

    def run(self, state: WorkflowState) -> WorkflowState:
        if state.stage != WorkflowStage.MATCH_INSIGHT:
            raise ValueError("Match & Insight Agent 只能在 match_insight 阶段运行")
        if not state.profile_confirmed or state.user_profile is None or not state.user_profile.confirmed:
            raise ProfileNotConfirmedError("用户画像未确认，不能执行 Match & Insight")
        state = record_agent_event(
            state,
            self.name,
            EventType.MATCH_INSIGHT_STARTED,
            "开始执行 evidence-first Match & Insight。",
            safe_metadata={
                "profile_id": state.user_profile.profile_id,
                "profile_version": state.user_profile.version,
                "job_count": len(state.job_intelligence),
            },
        )
        results = []
        relation_totals: Dict[str, int] = {}
        action_count = 0
        context_signal_count = 0
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "latency_ms": 0, "retry_count": 0}
        provider = None
        model = None
        for intelligence in state.job_intelligence:
            result, response, context = self.analyze_with_details(
                state.user_profile, intelligence
            )
            results.append(result)
            context_signal_count += len(context.profile_signals) + len(context.job_signals)
            provider = response.provider
            model = response.model
            for name, count in response.data.relation_counts().items():
                relation_totals[name] = relation_totals.get(name, 0) + count
            action_count += len(result.action_items)
            for name in ("input_tokens", "output_tokens", "total_tokens"):
                value = getattr(response.usage, name)
                if value is not None:
                    usage[name] += value
            usage["latency_ms"] += response.latency_ms
            usage["retry_count"] += response.retry_count
        safe = {
            "profile_id": state.user_profile.profile_id,
            "profile_version": state.user_profile.version,
            "job_count": len(results),
            "relation_counts": relation_totals,
            "action_count": action_count,
            "provider": provider,
            "model": model,
            "prompt_name": MATCH_INSIGHT_PROMPT_NAME,
            "prompt_version": MATCH_INSIGHT_PROMPT_VERSION,
            **usage,
        }
        state = record_agent_event(state, self.name, EventType.MATCH_CONTEXT_BUILT, "最小化 MatchContext 已建立。", safe_metadata={"job_count": len(results), "context_signal_count": context_signal_count})
        state = record_agent_event(state, self.name, EventType.MATCH_LLM_EXTRACTION_COMPLETED, "结构化证据关系候选已生成。", safe_metadata=safe)
        state = record_agent_event(state, self.name, EventType.MATCH_EVIDENCE_VALIDATION_COMPLETED, "用户与岗位 evidence links 已通过确定性校验。", safe_metadata={"relation_counts": relation_totals})
        state = state.validated_copy(match_results=results)
        state = record_agent_event(state, self.name, EventType.MATCH_RESULT_ASSEMBLED, "确定性 MatchInsightAssembler 已生成 MatchResult。", safe_metadata={"result_count": len(results), "relation_counts": relation_totals})
        state = record_agent_event(state, self.name, EventType.MATCH_ACTIONS_VALIDATED, "所有 ActionItem 均已关联验证过的问题。", safe_metadata={"action_count": action_count})
        return record_agent_event(state, self.name, EventType.MATCH_INSIGHT_COMPLETED, f"完成 {len(results)} 条独立岗位证据关系分析；未计算总分或排名。", safe_metadata=safe)
