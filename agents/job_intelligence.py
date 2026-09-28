"""Phase 1 确定性 Job Intelligence Agent stub。"""

from typing import List

from agents.base import BaseAgent, record_agent_event, record_tool_event
from data.models import (
    AgentName,
    EvidenceItem,
    EvidenceSourceType,
    EventType,
    JobIntelligenceRecord,
)
from tools.base import JobDataProvider
from workflows.stages import ProfileNotConfirmedError, WorkflowStage
from workflows.state import WorkflowState


def _metadata_list(metadata: dict, key: str) -> List[str]:
    value = metadata.get(key, [])
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


class JobIntelligenceAgent(BaseAgent):
    """把三条 fixture 岗位逐字段映射成结构化岗位情报。"""

    name = AgentName.JOB_INTELLIGENCE

    def __init__(self, job_provider: JobDataProvider) -> None:
        self.job_provider = job_provider

    def run(self, state: WorkflowState) -> WorkflowState:
        if state.stage != WorkflowStage.JOB_INTELLIGENCE:
            raise ValueError("Job Intelligence Agent 只能在 job_intelligence 阶段运行")
        if not state.profile_confirmed:
            raise ProfileNotConfirmedError("用户画像未确认，不能执行岗位情报阶段")

        state = record_agent_event(
            state,
            self.name,
            EventType.AGENT_STARTED,
            "开始读取 Phase 1 虚构岗位 fixture。",
        )
        state = record_tool_event(
            state,
            self.job_provider.name,
            EventType.TOOL_CALLED,
            "读取公开的本地岗位 fixture。",
        )
        jobs = self.job_provider.load()
        state = record_tool_event(
            state,
            self.job_provider.name,
            EventType.TOOL_COMPLETED,
            "岗位 fixture 读取完成。",
            {"record_count": len(jobs)},
        )

        records: List[JobIntelligenceRecord] = []
        for job in jobs:
            evidence_id = f"ev_job_{job.job_id}"
            evidence = EvidenceItem(
                id=evidence_id,
                source_type=EvidenceSourceType.JOB_DESCRIPTION,
                source_name=f"{job.organization} / {job.title}",
                statement=job.description,
                confidence=1.0,
                metadata={"fixture": True, "job_id": job.job_id},
            )
            records.append(
                JobIntelligenceRecord(
                    intelligence_id=f"intelligence_{job.job_id}",
                    job_id=job.job_id,
                    canonical_role=job.title,
                    actual_work=_metadata_list(job.metadata, "actual_work"),
                    required_capabilities=job.requirements,
                    preferred_capabilities=[
                        skill for skill in job.skills if skill not in job.requirements
                    ],
                    work_style=_metadata_list(job.metadata, "work_style"),
                    career_path=_metadata_list(job.metadata, "career_path"),
                    advantages=_metadata_list(job.metadata, "advantages"),
                    potential_drawbacks=_metadata_list(job.metadata, "potential_drawbacks"),
                    evidence=[evidence],
                    evidence_ids=[evidence_id],
                )
            )

        state = state.validated_copy(job_records=jobs, job_intelligence=records)
        return record_agent_event(
            state,
            self.name,
            EventType.AGENT_COMPLETED,
            f"已从 {len(records)} 条虚构岗位记录生成结构化岗位情报。",
            [item for record in records for item in record.evidence_ids],
        )
