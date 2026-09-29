"""不产生新判断的确定性 Report Builder。"""

from typing import Dict, List

from data.models import CareerReport, JobIntelligenceRecord, MatchResult, UserProfile
from tools.base import ReportProvider


class DeterministicReportBuilder(ReportProvider):
    """用已验证 Phase 5 关系组装中文优先报告，不产生新判断。"""

    name = "DeterministicReportBuilder"

    def build(
        self,
        workflow_id: str,
        profile: UserProfile,
        intelligence: List[JobIntelligenceRecord],
        matches: List[MatchResult],
    ) -> CareerReport:
        intelligence_by_job = {item.job_id: item for item in intelligence}
        actual_work: Dict[str, List[str]] = {}
        why_it_may_fit: Dict[str, List[str]] = {}
        evidence_missing: Dict[str, List[str]] = {}
        confirmed_gaps: Dict[str, List[str]] = {}
        experience_depth_gaps: Dict[str, List[str]] = {}
        potential_friction: Dict[str, List[str]] = {}
        unknowns: Dict[str, List[str]] = {}
        next_actions: Dict[str, List[str]] = {}

        for match in matches:
            record = intelligence_by_job[match.job_id]
            actual_work[match.job_id] = [signal.label for signal in record.actual_work]
            why_it_may_fit[match.job_id] = [
                item.title
                for item in [
                    *match.alignments,
                    *match.partial_alignments,
                    *match.preference_alignments,
                ]
            ]
            evidence_missing[match.job_id] = [item.title for item in match.evidence_gaps]
            confirmed_gaps[match.job_id] = [item.title for item in match.confirmed_gaps]
            experience_depth_gaps[match.job_id] = [
                item.title for item in match.experience_depth_gaps
            ]
            potential_friction[match.job_id] = [
                item.title for item in match.potential_frictions
            ]
            unknowns[match.job_id] = [item.title for item in match.unknowns]
            next_actions[match.job_id] = [
                item.description for item in match.action_items
            ]
        return CareerReport(
            report_id=f"report_{workflow_id}",
            workflow_id=workflow_id,
            profile_id=profile.profile_id,
            profile_version=profile.version,
            user_profile_summary=(
                f"已确认 UserProfile v{profile.version}，包含 {len(profile.skills)} 个候选技能信号。"
            ),
            role_insights=matches,
            actual_work=actual_work,
            why_it_may_fit=why_it_may_fit,
            evidence_missing=evidence_missing,
            confirmed_gaps=confirmed_gaps,
            experience_depth_gaps=experience_depth_gaps,
            potential_friction=potential_friction,
            unknowns=unknowns,
            next_actions=next_actions,
            workflow_summary="Phase 5 以双向证据关系生成独立岗位洞察；未计算总体分或岗位排名。",
            limitations=[
                "关系 confidence 只表示该条证据关系的支持强度，不是职业适配概率。",
                "报告不包含总体匹配分、岗位排名、最佳角色结论或就业预测。",
            ],
        )
