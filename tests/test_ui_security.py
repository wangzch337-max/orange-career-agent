"""Static security and dependency boundaries for Orange Interactive Demo v0.1."""

from __future__ import annotations

import ast
from pathlib import Path

import streamlit


ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "ui"


def test_streamlit_dependency_and_telemetry_configuration() -> None:
    assert streamlit.__version__ == "1.64.0"
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "streamlit>=1.64,<1.65" in requirements
    config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert "gatherUsageStats = false" in config
    assert 'address = "localhost"' in config


def test_ui_has_no_private_live_provider_network_or_vector_imports() -> None:
    forbidden_modules = {
        "chromadb",
        "sqlite_vec",
        "sentence_transformers",
        "requests",
        "httpx",
        "socket",
        "selenium",
        "playwright",
    }
    imported_modules = set()
    source = ""
    for path in UI_ROOT.rglob("*.py"):
        file_source = path.read_text(encoding="utf-8")
        source += "\n" + file_source
        tree = ast.parse(file_source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(item.name.split(".")[0] for item in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module.split(".")[0])
    lowered = source.casefold()
    assert imported_modules.isdisjoint(forbidden_modules)
    assert "qwenprovider" not in lowered
    assert "data/private" not in lowered
    assert "confirmed_profile.json" not in lowered
    assert ".env.local" not in lowered
    assert "orange_workflow.sqlite3" not in lowered
    assert "orange_memory.sqlite3" not in lowered
    assert "embeddingprovider" not in lowered


def test_ui_adapter_does_not_import_or_reimplement_domain_assemblers() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in UI_ROOT.rglob("*.py")
    ).casefold()
    for forbidden in (
        "profileassembler",
        "jobintelligenceassembler",
        "matchinsightassembler",
        "actionrenderer(",
        "overall_score",
        "weighted_score",
        "best role",
        "top pick",
    ):
        assert forbidden not in source


def test_streamlit_app_uses_only_approved_role_ids_and_no_private_mode() -> None:
    controller_source = (UI_ROOT / "demo_controller.py").read_text(encoding="utf-8")
    app_source = (UI_ROOT / "app.py").read_text(encoding="utf-8")
    assert "DEFAULT_SELECTED_JOB_IDS" in controller_source
    assert "APPROVED_ROLE_IDS" in app_source
    for forbidden in (
        "Use My Real Profile",
        "Private Mode",
        "Load confirmed_profile.json",
        "Live AI",
    ):
        assert forbidden not in app_source
