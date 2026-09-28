"""不产生新判断的确定性 Report Builder。"""

from typing import Dict, List

from data.models import CareerReport, JobIntelligenceRecord, MatchResult, UserProfile
from tools.base import ReportProvider


class DeterministicReportBuilder(ReportProvider):
    """用结构化 Phase 1 数据组装简短中文报告。"""

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
        evidence_of_fit: Dict[str, List[str]] = {}
        potential_friction: Dict[str, List[str]] = {}

        for match in matches:
            record = intelligence_by_job[match.job_id]
            actual_work[match.job_id] = [signal.label for signal in record.actual_work]
            evidence_of_fit[match.job_id] = match.evidence_of_fit
            potential_friction[match.job_id] = match.potential_friction

        gaps = [gap for match in matches for gap in match.capability_gaps]
        actions = [action for match in matches for action in match.suggested_actions]
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
            evidence_of_fit=evidence_of_fit,
            potential_friction=potential_friction,
            capability_gaps=gaps,
            suggested_actions=actions,
            workflow_summary="Phase 1 使用本地 fixture 与精确标签重合完成确定性数据流验证。",
            limitations=[
                "本报告不包含 LLM 语义推理。",
                "精确标签重合不代表真实职业适配度或就业结果。",
            ],
        )
