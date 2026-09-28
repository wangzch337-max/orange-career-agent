"""Offline/live-mode boundary and Phase 1 regression tests."""

from pathlib import Path

from agents.self_discovery import SelfDiscoveryAgent
from providers import demo
from providers.models import ProfileSignalExtraction
from workflows.demo import run_demo_to_completion, run_demo_until_confirmation
from workflows.stages import WorkflowStage


def test_offline_provider_demo_succeeds() -> None:
    response = demo.run_offline_demo()
    assert isinstance(response.data, ProfileSignalExtraction)
    assert response.provider == "fake"


def test_offline_main_prints_safe_summary(capsys) -> None:
    assert demo.main([]) == 0
    output = capsys.readouterr().out
    assert "FakeLLMProvider 未进行网络调用" in output
    assert "profile_signal_extraction@v1" in output
    assert "DASHSCOPE" not in output


def test_live_demo_missing_config_fails_before_provider(monkeypatch, capsys) -> None:
    for name in (
        "ORANGE_LLM_PROVIDER",
        "ORANGE_LLM_MODEL",
        "DASHSCOPE_API_KEY",
        "DASHSCOPE_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(demo, "REPOSITORY_ROOT", Path("/nonexistent/orange-test-root"))

    def must_not_construct(*args, **kwargs):
        raise AssertionError("QwenProvider must not be constructed")

    monkeypatch.setattr(demo.QwenProvider, "from_settings", must_not_construct)
    assert demo.main(["--live"]) == 2
    output = capsys.readouterr().out
    assert "配置不完整" in output


def test_phase1_self_discovery_remains_provider_independent() -> None:
    source = Path(SelfDiscoveryAgent.__module__.replace(".", "/") + ".py").read_text(
        encoding="utf-8"
    )
    assert "providers" not in source
    assert "LLM" not in source


def test_existing_deterministic_workflow_still_completes() -> None:
    completed = run_demo_to_completion(run_demo_until_confirmation())
    assert completed.stage == WorkflowStage.COMPLETED
    assert len(completed.user_profile.skills) == 3
