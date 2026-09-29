"""三个推理 Agent 与 Orchestrator 概念测试。"""

from agents.job_intelligence import JobIntelligenceAgent
from agents.match_insight import MatchInsightAgent
from agents.orchestrator import OrchestratorAgent
from agents.self_discovery import SelfDiscoveryAgent
from data.models import MatchRelationType, MatchResult, UserProfile


def test_four_agent_concepts_exist(orchestrator) -> None:
    assert isinstance(orchestrator, OrchestratorAgent)
    assert isinstance(orchestrator.engine.self_discovery_agent, SelfDiscoveryAgent)
    assert isinstance(orchestrator.engine.job_intelligence_agent, JobIntelligenceAgent)
    assert isinstance(orchestrator.engine.match_insight_agent, MatchInsightAgent)


def test_self_discovery_produces_valid_profile(paused_state) -> None:
    assert isinstance(paused_state.user_profile, UserProfile)
    assert len(paused_state.user_profile.skills) == 3
    assert len(paused_state.user_profile.evidence) >= 6


def test_job_intelligence_agent_returns_valid_records(completed_state) -> None:
    assert len(completed_state.job_intelligence) == 20
    assert all(record.evidence_ids for record in completed_state.job_intelligence)


def test_match_agent_uses_evidence_relations_without_score(completed_state) -> None:
    assert "overall_score" not in MatchResult.model_fields
    assert all(match.insights() for match in completed_state.match_results)
    product_match = next(
        item for item in completed_state.match_results if item.job_id == "job_001"
    )
    assert any(
        item.relation_type == MatchRelationType.STRONG_ALIGNMENT
        for item in product_match.alignments
    )
