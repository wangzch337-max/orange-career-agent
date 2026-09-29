"""Provider boundary, workflow, prompt, demo, and observability tests."""

import ast
import hashlib
from pathlib import Path

import pytest

from agents.match_context import MatchContextBuilder
from agents.match_insight import MatchInsightAgent, public_offline_match_extraction
from agents.match_insight_demo import (
    PRIVATE_CONFIRMED_PROFILE,
    confirm_and_store_profile,
    main as match_demo_main,
    run_offline_demo,
)
from data.models import EventType, MatchResult
from providers.base import LLMProvider
from providers.fake import FakeLLMProvider
from providers.prompts import (
    MATCH_INSIGHT_PROMPT_NAME,
    MATCH_INSIGHT_PROMPT_VERSION,
    load_match_insight_prompt,
)
from workflows.stages import WorkflowStage
from workflows.stages import ProfileNotConfirmedError


ROOT = Path(__file__).resolve().parents[1]


def test_match_agent_depends_on_llm_provider_not_qwen() -> None:
    source = (ROOT / "agents" / "match_insight.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "providers.base" in imports
    assert "providers.qwen" not in imports


def test_fake_provider_runs_real_match_agent() -> None:
    intelligence, expected_result, _ = run_offline_demo()[0]
    from agents.match_insight_demo import load_public_profile
    profile = load_public_profile()
    context = MatchContextBuilder().build(profile, intelligence)
    provider = FakeLLMProvider(public_offline_match_extraction(context))
    agent = MatchInsightAgent(provider)
    result = agent.analyze(profile, intelligence)
    assert isinstance(agent.llm_provider, LLMProvider)
    assert result.model_dump(exclude={"analysis_metadata"}) == expected_result.model_dump(exclude={"analysis_metadata"})
    assert provider.call_count == 1


def test_match_agent_rejects_unconfirmed_profile_before_provider_call() -> None:
    from agents.match_insight_demo import build_offline_job_intelligence
    from data.models import UserProfile
    provider = FakeLLMProvider(None)
    agent = MatchInsightAgent(provider)
    with pytest.raises(ProfileNotConfirmedError):
        agent.analyze(UserProfile(profile_id="draft"), build_offline_job_intelligence()[0])
    assert provider.call_count == 0


def test_match_prompt_is_versioned_and_evidence_first() -> None:
    prompt = load_match_insight_prompt()
    assert MATCH_INSIGHT_PROMPT_NAME == "match_insight"
    assert MATCH_INSIGHT_PROMPT_VERSION == "v5"
    for phrase in (
        "evidence_missing",
        "confirmed_gap",
        "不计算总体分",
        "不排名岗位",
        "chain",
        "action intent",
        "不得同义改写",
        "不要输出 evidence ID",
        "Bilateral relations",
        "request-scoped allowed IDs",
        "不得创建、改写、缩写、翻译、变换或推断 signal ID",
    ):
        assert phrase in prompt


def test_all_older_prompt_files_are_byte_for_byte_unchanged() -> None:
    expected = {
        "profile_signal_extraction_v1.md": "4021dc9feb9441720e92325ca70f58deac5d7fcfb12690655c56a30512727192",
        "self_discovery_v1.md": "27ce461b5c1a6b1f062f24f04dfa42aaa90e0d00803d41d579b2ba475134eacb",
        "job_intelligence_v1.md": "dbd8f117714059c51a279b5e87c7426cea3e41a01361ab4f3f6e7fd7e5812a6a",
        "match_insight_v1.md": "151b41c72a29a27b80b35c5ff7d1bfc6e5fd3c4086e0e0dc7ad4415b60f7928d",
        "match_insight_v2.md": "487e6e48ed3fb6dc89019fdc8d25d5349b0f5e1d609b0318e4b3bc7d66425fa9",
        "match_insight_v3.md": "abfc731a9073c3481fa0abfb0be7a833c923151ea6e778d913cf9ca28c3cb30e",
        "match_insight_v4.md": "8e36ed7f467de16854606b698ee889e7d80f0a4c191de5de5a3d6c07c92c449f",
    }
    for name, digest in expected.items():
        assert hashlib.sha256((ROOT / "config" / "prompts" / name).read_bytes()).hexdigest() == digest


def test_workflow_uses_real_match_agent_after_confirmation(completed_state) -> None:
    assert completed_state.stage == WorkflowStage.COMPLETED
    assert len(completed_state.match_results) == 20
    assert all(isinstance(item, MatchResult) for item in completed_state.match_results)
    assert all("overall_score" not in item.model_dump() for item in completed_state.match_results)


def test_match_observability_events_have_safe_counts(completed_state) -> None:
    required = {
        EventType.MATCH_INSIGHT_STARTED,
        EventType.MATCH_CONTEXT_BUILT,
        EventType.MATCH_LLM_EXTRACTION_COMPLETED,
        EventType.MATCH_EVIDENCE_VALIDATION_COMPLETED,
        EventType.MATCH_RESULT_ASSEMBLED,
        EventType.MATCH_ACTIONS_VALIDATED,
        EventType.MATCH_INSIGHT_COMPLETED,
    }
    events = [event for event in completed_state.agent_events if event.event_type in required]
    assert {event.event_type for event in events} == required
    rendered = "\n".join(event.model_dump_json() for event in events)
    assert '"relation_counts"' in rendered
    assert '"action_count"' in rendered
    assert "DASHSCOPE_API_KEY" not in rendered
    assert "Authorization" not in rendered
    assert "Implemented a small Python prototype" not in rendered


def test_report_builder_displays_relation_sections_without_score_or_ranking(completed_state) -> None:
    report = completed_state.report
    assert report is not None
    assert report.why_it_may_fit
    assert report.evidence_missing
    assert report.unknowns
    serialized = report.model_dump_json()
    assert "overall_score" not in serialized
    assert "best role" not in serialized.casefold()
    assert "ranking" not in serialized.casefold()


def test_public_offline_demo_runs_all_twenty_in_dataset_order(capsys) -> None:
    results = run_offline_demo()
    assert len(results) == 20
    assert [item.role_title for item, _, _ in results][:3] == [
        "AI Product Intern", "Associate AI Product Manager", "Technical Product Manager — AI"
    ]
    assert match_demo_main([]) == 0
    output = capsys.readouterr().out
    assert "All 20 roles completed offline" in output
    assert "no ranking" in output.lower()
    assert "Evidence relationships only; no scoring" in output


def test_offline_demo_does_not_require_qwen_configuration(monkeypatch) -> None:
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)
    assert match_demo_main([]) == 0


def test_private_confirmation_defaults_to_no_and_writes_nothing(tmp_path) -> None:
    from agents.match_insight_demo import load_public_profile
    output = tmp_path / "confirmed_profile.json"
    assert confirm_and_store_profile(
        load_public_profile(), output, input_fn=lambda _: ""
    ) is False
    assert not output.exists()


def test_private_confirmation_requires_literal_y(tmp_path) -> None:
    from agents.match_insight_demo import load_public_profile
    for response in ("yes", "Y ", "n"):
        output = tmp_path / f"{response.strip() or 'blank'}.json"
        assert confirm_and_store_profile(
            load_public_profile(), output, input_fn=lambda _, value=response: value
        ) is (response.strip().lower() == "y")
    assert not (tmp_path / "yes.json").exists()


def test_private_confirmed_profile_path_is_ignored_without_reading_private_data() -> None:
    import subprocess
    result = subprocess.run(
        ["git", "check-ignore", "-q", str(PRIVATE_CONFIRMED_PROFILE.relative_to(ROOT))],
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0
