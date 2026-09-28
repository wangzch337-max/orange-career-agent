"""三个推理 Agent stub 与 Orchestrator 概念测试。"""

from agents.job_intelligence import JobIntelligenceAgent
from agents.match_insight import MatchInsightAgent
from agents.orchestrator import OrchestratorAgent
from agents.self_discovery import SelfDiscoveryAgent
from data.models import MatchMethod, MatchResult, UserProfile


def test_four_agent_concepts_exist(orchestrator) -> None:
    assert isinstance(orchestrator, OrchestratorAgent)
    assert isinstance(orchestrator.engine.self_discovery_agent, SelfDiscoveryAgent)
    assert isinstance(orchestrator.engine.job_intelligence_agent, JobIntelligenceAgent)
    assert isinstance(orchestrator.engine.match_insight_agent, MatchInsightAgent)


def test_self_discovery_produces_valid_profile(paused_state) -> None:
    assert isinstance(paused_state.user_profile, UserProfile)
    assert len(paused_state.user_profile.skills) == 3
    assert len(paused_state.user_profile.evidence) >= 6


def test_job_intelligence_stub_returns_valid_records(completed_state) -> None:
    assert len(completed_state.job_intelligence) == 3
    assert all(record.evidence_ids for record in completed_state.job_intelligence)


def test_match_stub_uses_exact_overlap_without_score(completed_state) -> None:
    assert "overall_score" not in MatchResult.model_fields
    assert all(
        dimension.method == MatchMethod.EXACT_OVERLAP
        for match in completed_state.match_results
        for dimension in match.dimensions
    )
    product_match = next(
        item for item in completed_state.match_results if item.job_id == "job_ai_product_intern"
    )
    assert product_match.dimensions[0].matched_items == [
        "AI Product Thinking",
        "Artificial Intelligence",
    ]
