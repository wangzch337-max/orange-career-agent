"""产品层 Orchestrator Agent；执行逻辑委托给 workflow engine。"""

from agents.base import BaseAgent
from agents.job_intelligence import JobIntelligenceAgent, public_offline_job_extraction
from agents.job_intelligence_evidence import JobEvidenceBuilder
from agents.match_insight import MatchInsightAgent
from agents.self_discovery import SelfDiscoveryAgent, public_offline_extraction
from data.models import AgentName
from tools.course_data import MockCourseDataProvider
from tools.job_data import MockJobDataProvider
from tools.report import DeterministicReportBuilder
from providers.fake import FakeLLMProvider
from workflows.engine import DeterministicWorkflowEngine
from workflows.state import WorkflowState


class OrchestratorAgent(BaseAgent):
    """Phase 1 确定性 Orchestrator 的产品层入口。"""

    name = AgentName.ORCHESTRATOR

    def __init__(self, engine: DeterministicWorkflowEngine) -> None:
        self.engine = engine

    @classmethod
    def create_default(cls) -> "OrchestratorAgent":
        """组装只依赖公开本地 fixture 的 Phase 1 默认对象图。"""

        job_provider = MockJobDataProvider()
        jobs = job_provider.load()
        evidence_builder = JobEvidenceBuilder()
        job_responses = [
            public_offline_job_extraction(job, evidence_builder.build(job))
            for job in jobs
        ]
        engine = DeterministicWorkflowEngine(
            self_discovery_agent=SelfDiscoveryAgent(
                MockCourseDataProvider(),
                FakeLLMProvider(public_offline_extraction()),
            ),
            job_intelligence_agent=JobIntelligenceAgent(
                job_provider,
                FakeLLMProvider(None, predefined_responses=job_responses),
                evidence_builder=evidence_builder,
            ),
            match_insight_agent=MatchInsightAgent(),
            report_builder=DeterministicReportBuilder(),
        )
        return cls(engine)

    def run(self, state: WorkflowState) -> WorkflowState:
        return self.engine.run_until_pause(state)

    def confirm_and_continue(self, state: WorkflowState) -> WorkflowState:
        state = self.engine.confirm_profile(state)
        return self.engine.run_until_pause(state)

    def revise_and_pause(self, state: WorkflowState, **changes: object) -> WorkflowState:
        state = self.engine.request_profile_revision(state, **changes)
        return self.engine.run_until_pause(state)
