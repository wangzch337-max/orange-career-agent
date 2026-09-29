"""产品层 Orchestrator Agent；执行逻辑委托给 workflow engine。"""

import json
from pathlib import Path

from agents.base import BaseAgent
from agents.job_intelligence import JobIntelligenceAgent, public_offline_job_extraction
from agents.job_intelligence_evidence import JobEvidenceBuilder
from agents.match_insight import MatchInsightAgent
from agents.match_context import MatchContextBuilder
from agents.match_insight import public_offline_match_extraction
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
        course_provider = MockCourseDataProvider()
        courses = course_provider.load()
        evidence_builder = JobEvidenceBuilder()
        job_responses = [
            public_offline_job_extraction(job, evidence_builder.build(job))
            for job in jobs
        ]
        preview_job_agent = JobIntelligenceAgent(
            job_provider,
            FakeLLMProvider(None, predefined_responses=job_responses),
            evidence_builder=evidence_builder,
        )
        intelligence = [preview_job_agent.analyze(job) for job in jobs]
        public_input_path = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "fixtures"
            / "sample_user_input.json"
        )
        public_input = json.loads(public_input_path.read_text(encoding="utf-8"))
        preview_profile = SelfDiscoveryAgent(
            course_provider,
            FakeLLMProvider(public_offline_extraction()),
        ).discover(public_input, courses).user_profile.confirm()
        match_context_builder = MatchContextBuilder()
        match_responses = [
            public_offline_match_extraction(
                match_context_builder.build(preview_profile, item)
            )
            for item in intelligence
        ]
        engine = DeterministicWorkflowEngine(
            self_discovery_agent=SelfDiscoveryAgent(
                course_provider,
                FakeLLMProvider(public_offline_extraction()),
            ),
            job_intelligence_agent=JobIntelligenceAgent(
                job_provider,
                FakeLLMProvider(None, predefined_responses=job_responses),
                evidence_builder=evidence_builder,
            ),
            match_insight_agent=MatchInsightAgent(
                FakeLLMProvider(None, predefined_responses=match_responses),
                context_builder=match_context_builder,
            ),
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
