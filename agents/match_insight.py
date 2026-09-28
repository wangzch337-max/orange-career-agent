"""Phase 1 精确标签重合 Match & Insight Agent stub。"""

from typing import Dict, List, Set

from agents.base import BaseAgent, record_agent_event
from data.models import (
    ActionItem,
    AgentName,
    EventType,
    GapItem,
    MatchDimension,
    MatchMethod,
    MatchResult,
    Severity,
)
from workflows.stages import ProfileNotConfirmedError, WorkflowStage
from workflows.state import WorkflowState


class MatchInsightAgent(BaseAgent):
    """只验证数据流，不提供真实职业适配评分。"""

    name = AgentName.MATCH_INSIGHT

    def run(self, state: WorkflowState) -> WorkflowState:
        if state.stage != WorkflowStage.MATCH_INSIGHT:
            raise ValueError("Match & Insight Agent 只能在 match_insight 阶段运行")
        if not state.profile_confirmed or state.user_profile is None:
            raise ProfileNotConfirmedError("用户画像未确认，不能执行匹配阶段")

        state = record_agent_event(
            state,
            self.name,
            EventType.AGENT_STARTED,
            "开始执行 Phase 1 精确技能标签重合。",
        )
        profile = state.user_profile
        job_by_id = {job.job_id: job for job in state.job_records}
        user_skills = {skill.label.casefold(): skill for skill in profile.skills}
        matches: List[MatchResult] = []

        for intelligence in state.job_intelligence:
            job = job_by_id[intelligence.job_id]
            job_skills = {skill.casefold(): skill for skill in job.skills}
            overlap_keys: Set[str] = set(user_skills).intersection(job_skills)
            overlap_labels = sorted(job_skills[key] for key in overlap_keys)
            fit_evidence = sorted(
                {
                    evidence_id
                    for key in overlap_keys
                    for evidence_id in user_skills[key].evidence_ids
                }
            )
            fit_evidence.extend(
                evidence_id
                for evidence_id in intelligence.evidence_ids
                if overlap_labels and evidence_id not in fit_evidence
            )

            gaps = self._build_gaps(job.job_id, job.skills, user_skills, intelligence.evidence_ids)
            actions = self._build_actions(job.job_id, gaps)
            why_fit = (
                [f"公开 fixture 中存在精确技能标签重合：{', '.join(overlap_labels)}。"]
                if overlap_labels
                else []
            )
            friction = (
                [f"fixture 提示的潜在摩擦：{intelligence.potential_drawbacks[0]}"]
                if intelligence.potential_drawbacks
                else []
            )
            matches.append(
                MatchResult(
                    match_id=f"match_{job.job_id}",
                    profile_id=profile.profile_id,
                    profile_version=profile.version,
                    intelligence_id=intelligence.intelligence_id,
                    job_id=job.job_id,
                    role_title=job.title,
                    dimensions=[
                        MatchDimension(
                            name="skills",
                            method=MatchMethod.EXACT_OVERLAP,
                            summary=(
                                f"找到 {len(overlap_labels)} 个精确重合标签。"
                                if overlap_labels
                                else "未找到精确重合标签；这表示证据不足，不等于不适合。"
                            ),
                            matched_items=overlap_labels,
                            evidence_ids=fit_evidence,
                        )
                    ],
                    why_it_may_fit=why_fit,
                    evidence_of_fit=fit_evidence,
                    potential_friction=friction,
                    capability_gaps=gaps,
                    suggested_actions=actions,
                )
            )

        state = state.validated_copy(match_results=matches)
        return record_agent_event(
            state,
            self.name,
            EventType.AGENT_COMPLETED,
            f"完成 {len(matches)} 条 exact-overlap Demo 结果；未计算权重或总分。",
            sorted({item for match in matches for item in match.evidence_of_fit}),
        )

    @staticmethod
    def _build_gaps(
        job_id: str,
        job_skills: List[str],
        user_skills: Dict[str, object],
        required_evidence_ids: List[str],
    ) -> List[GapItem]:
        gaps = []
        for index, skill in enumerate(job_skills, start=1):
            if skill.casefold() in user_skills:
                continue
            gaps.append(
                GapItem(
                    gap_id=f"gap_{job_id}_{index:02d}",
                    capability=skill,
                    required_evidence_ids=required_evidence_ids,
                    severity=Severity.MEDIUM,
                    interpretation=f"当前公开 fixture 尚无 {skill} 的直接证据。",
                )
            )
        return gaps

    @staticmethod
    def _build_actions(job_id: str, gaps: List[GapItem]) -> List[ActionItem]:
        if not gaps:
            return []
        first_gap = gaps[0]
        return [
            ActionItem(
                action_id=f"action_{job_id}_01",
                description=f"完成一个可展示的 {first_gap.capability} 小练习。",
                rationale="为目前缺少直接证据的能力补充作品集证据。",
                priority=Severity.MEDIUM,
                time_horizon="2 周",
                success_criteria="形成一个可复查的公开-safe 产物与简短说明。",
                related_gap_ids=[first_gap.gap_id],
            )
        ]
