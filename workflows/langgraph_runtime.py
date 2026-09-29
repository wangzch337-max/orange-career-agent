"""Public, network-free dependency assembly for the Phase 6 graph."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

from agents.job_intelligence import JobIntelligenceAgent, public_offline_job_extraction
from agents.job_intelligence_evidence import JobEvidenceBuilder
from agents.match_context import MatchContextBuilder
from agents.match_insight import MatchInsightAgent, public_offline_match_extraction
from agents.self_discovery import SelfDiscoveryAgent, public_offline_extraction
from providers.fake import FakeLLMProvider
from tools.course_data import MockCourseDataProvider
from tools.job_data import MockJobDataProvider
from tools.report import DeterministicReportBuilder
from workflows.langgraph_workflow import OrangeGraphDependencies


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_INPUT_PATH = PROJECT_ROOT / "data" / "fixtures" / "sample_user_input.json"
DEFAULT_SELECTED_JOB_IDS = ("job_001", "job_007", "job_013")


def load_public_self_discovery_input() -> dict[str, object]:
    return json.loads(PUBLIC_INPUT_PATH.read_text(encoding="utf-8"))


def build_public_offline_dependencies(
    selected_job_ids: Sequence[str] = DEFAULT_SELECTED_JOB_IDS,
) -> OrangeGraphDependencies:
    """Build only FakeLLMProvider-backed Agents for public offline execution."""

    course_provider = MockCourseDataProvider()
    job_provider = MockJobDataProvider()
    jobs_by_id = {item.job_id: item for item in job_provider.load()}
    try:
        selected_jobs = [jobs_by_id[job_id] for job_id in selected_job_ids]
    except KeyError as exc:
        raise ValueError(f"Unknown public Demo job ID: {exc.args[0]}") from exc

    evidence_builder = JobEvidenceBuilder()
    job_responses = [
        public_offline_job_extraction(job, evidence_builder.build(job))
        for job in selected_jobs
    ]
    preview_job_agent = JobIntelligenceAgent(
        job_provider,
        FakeLLMProvider(None, predefined_responses=job_responses),
        evidence_builder=evidence_builder,
    )
    intelligence = [preview_job_agent.analyze(job) for job in selected_jobs]

    public_input = load_public_self_discovery_input()
    preview_profile = SelfDiscoveryAgent(
        course_provider,
        FakeLLMProvider(public_offline_extraction()),
    ).discover(public_input, course_provider.load()).user_profile.confirm()
    context_builder = MatchContextBuilder()
    match_responses = [
        public_offline_match_extraction(context_builder.build(preview_profile, item))
        for item in intelligence
    ]

    # Repeated deterministic response cycles allow isolated test threads to share
    # one compiled public graph without any fallback to network or another provider.
    response_cycles = 32
    return OrangeGraphDependencies(
        self_discovery_agent=SelfDiscoveryAgent(
            course_provider,
            FakeLLMProvider(public_offline_extraction()),
        ),
        job_intelligence_agent=JobIntelligenceAgent(
            job_provider,
            FakeLLMProvider(
                None,
                predefined_responses=job_responses * response_cycles,
            ),
            evidence_builder=evidence_builder,
        ),
        match_insight_agent=MatchInsightAgent(
            FakeLLMProvider(
                None,
                predefined_responses=match_responses * response_cycles,
            ),
            context_builder=context_builder,
        ),
        report_builder=DeterministicReportBuilder(),
        self_discovery_input=public_input,
    )
