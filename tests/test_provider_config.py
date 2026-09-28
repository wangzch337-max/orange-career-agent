"""Repository-local, credential-safe configuration tests."""

from pathlib import Path

import pytest
from pydantic import SecretStr

from providers.errors import LLMConfigurationError
from providers.models import LLMSettings, load_llm_settings


ENV_NAMES = (
    "ORANGE_LLM_PROVIDER",
    "ORANGE_LLM_MODEL",
    "DASHSCOPE_API_KEY",
    "DASHSCOPE_BASE_URL",
)


def clear_llm_env(monkeypatch) -> None:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_missing_api_key_is_configuration_error() -> None:
    settings = LLMSettings(base_url=SecretStr("https://workspace.invalid/compatible-mode/v1"))
    with pytest.raises(LLMConfigurationError, match="API key"):
        settings.require_live_qwen()


def test_missing_base_url_is_configuration_error() -> None:
    settings = LLMSettings(api_key=SecretStr("unit-test-key"))
    with pytest.raises(LLMConfigurationError, match="base URL"):
        settings.require_live_qwen()


def test_phase_two_live_model_is_restricted_to_qwen_flash() -> None:
    settings = LLMSettings(
        model="different-model",
        api_key=SecretStr("unit-test-key"),
        base_url=SecretStr("https://workspace.invalid/compatible-mode/v1"),
    )
    with pytest.raises(LLMConfigurationError, match="qwen3.8-flash"):
        settings.require_live_qwen()


def test_safe_summary_never_contains_secret_values() -> None:
    key = "unit-test-private-value"
    url = "https://workspace-identifier.invalid/compatible-mode/v1"
    settings = LLMSettings(api_key=SecretStr(key), base_url=SecretStr(url))
    rendered = repr(settings.safe_summary())
    assert key not in rendered
    assert url not in rendered
    assert settings.safe_summary()["api_key_configured"] is True
    assert settings.safe_summary()["base_url_configured"] is True


def test_shell_environment_wins_over_repository_local_file(tmp_path: Path, monkeypatch) -> None:
    clear_llm_env(monkeypatch)
    key_name = "DASHSCOPE_" + "API_KEY"
    (tmp_path / ".env.local").write_text(
        f"ORANGE_LLM_MODEL=file-model\n{key_name}=file-value\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ORANGE_LLM_MODEL", "shell-model")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "shell-value")
    settings = load_llm_settings(tmp_path)
    assert settings.model == "shell-model"
    assert settings.api_key.get_secret_value() == "shell-value"


def test_loader_does_not_search_parent_or_home(tmp_path: Path, monkeypatch) -> None:
    clear_llm_env(monkeypatch)
    parent_env = tmp_path / ".env.local"
    key_name = "DASHSCOPE_" + "API_KEY"
    parent_env.write_text(f"{key_name}=parent-value\n", encoding="utf-8")
    repository = tmp_path / "repo"
    repository.mkdir()
    settings = load_llm_settings(repository)
    assert settings.api_key is None
