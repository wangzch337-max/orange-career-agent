"""Phase 3 agent, workflow, observability, and offline demo integration."""

from pathlib import Path

from agents.self_discovery import SelfDiscoveryAgent, public_offline_extraction
from agents.self_discovery_demo import main as demo_main, print_safe_summary, run_demo
from data.models import EventType
from providers.base import LLMProvider
from providers.fake import FakeLLMProvider
from providers.models import GenerationOptions
from providers.prompts import SELF_DISCOVERY_PROMPT_NAME, SELF_DISCOVERY_PROMPT_VERSION
from tools.course_data import MockCourseDataProvider
from workflows.demo import load_user_input, run_demo_to_completion, run_demo_until_confirmation
from workflows.stages import WorkflowStage


def test_agent_requires_explicit_llm_provider_dependency() -> None:
    provider = FakeLLMProvider(public_offline_extraction())
    agent = SelfDiscoveryAgent(MockCourseDataProvider(), provider)
    assert isinstance(agent.llm_provider, LLMProvider)
    assert agent.llm_provider is provider


def test_fake_provider_integration_uses_self_discovery_prompt() -> None:
    provider = FakeLLMProvider(public_offline_extraction())
    agent = SelfDiscoveryAgent(MockCourseDataProvider(), provider)
    result = agent.discover(load_user_input(), MockCourseDataProvider().load())
    assert provider.call_count == 1
    assert result.extraction_metadata["prompt_name"] == SELF_DISCOVERY_PROMPT_NAME
    assert result.extraction_metadata["prompt_version"] == SELF_DISCOVERY_PROMPT_VERSION


def test_workflow_enters_real_agent_and_stops_for_confirmation() -> None:
    state = run_demo_until_confirmation()
    assert state.stage == WorkflowStage.AWAITING_PROFILE_CONFIRMATION
    assert state.user_profile is not None
    assert state.user_profile.confirmed is False
    assert any(event.event_type == EventType.LLM_EXTRACTION_COMPLETED for event in state.agent_events)


def test_job_intelligence_cannot_run_before_confirmation() -> None:
    state = run_demo_until_confirmation()
    assert state.job_intelligence == []
    assert state.match_results == []


def test_profile_confirmation_still_allows_completion() -> None:
    completed = run_demo_to_completion(run_demo_until_confirmation())
    assert completed.stage == WorkflowStage.COMPLETED
    assert completed.user_profile.confirmed is True


def test_profile_revision_keeps_incremented_version(orchestrator, paused_state) -> None:
    revised = orchestrator.revise_and_pause(paused_state, education_summary="公开匿名修订摘要")
    assert revised.stage == WorkflowStage.AWAITING_PROFILE_CONFIRMATION
    assert revised.user_profile.version == 2
    assert revised.user_profile.confirmed is False


def test_observability_contains_counts_without_raw_input(paused_state) -> None:
    extraction_event = next(event for event in paused_state.agent_events if event.event_type == EventType.LLM_EXTRACTION_COMPLETED)
    assert extraction_event.safe_metadata["signal_counts"]["skills"] == 3
    rendered = "\n".join(event.model_dump_json() for event in paused_state.agent_events)
    assert load_user_input()["project_experience"]["summary"] not in rendered
    assert "DASHSCOPE" not in rendered


def test_public_self_discovery_demo_runs_offline(capsys) -> None:
    assert demo_main([]) == 0
    output = capsys.readouterr().out
    assert "Fixture：public" in output
    assert "Provider：fake" in output
    assert "draft" in output


def test_offline_agent_does_not_require_qwen_configuration(monkeypatch) -> None:
    for name in ("DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    assert demo_main([]) == 0


def test_agent_module_never_imports_qwen_transport() -> None:
    source = Path("agents/self_discovery.py").read_text(encoding="utf-8")
    assert "QwenProvider" not in source
    assert "from openai" not in source


def test_private_review_view_exposes_only_safe_structured_fields(capsys) -> None:
    result = run_demo(live=False, fixture="public")
    print_safe_summary(result, live=False, fixture="private")
    output = capsys.readouterr().out
    assert "confidence=" in output
    assert "inference=" in output
    assert "evidence=" in output
    assert load_user_input()["project_experience"]["summary"] not in output
