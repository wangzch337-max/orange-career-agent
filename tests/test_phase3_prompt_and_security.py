"""Prompt history, private boundary, and prohibited integration tests."""

import ast
import hashlib
import subprocess
from pathlib import Path

from providers.prompts import (
    SELF_DISCOVERY_PROMPT_NAME,
    SELF_DISCOVERY_PROMPT_PATH,
    SELF_DISCOVERY_PROMPT_VERSION,
    load_self_discovery_prompt,
)


ROOT = Path(__file__).resolve().parents[1]


def test_self_discovery_prompt_is_versioned_and_grounded() -> None:
    assert SELF_DISCOVERY_PROMPT_PATH.name == "self_discovery_v2.md"
    assert SELF_DISCOVERY_PROMPT_NAME == "self_discovery"
    assert SELF_DISCOVERY_PROMPT_VERSION == "v2"
    prompt = load_self_discovery_prompt()
    for phrase in (
        "不得虚构",
        "explicit_fact",
        "缺少证据不等于弱点",
        "0–5",
        "最窄范围",
        "career_goal",
        "project_goal",
        "learning_goal",
        "chain-of-thought",
    ):
        assert phrase in prompt


def test_self_discovery_v1_prompt_remains_byte_for_byte_unchanged() -> None:
    payload = (ROOT / "config" / "prompts" / "self_discovery_v1.md").read_bytes()
    assert hashlib.sha256(payload).hexdigest() == "27ce461b5c1a6b1f062f24f04dfa42aaa90e0d00803d41d579b2ba475134eacb"


def test_phase2_prompt_remains_byte_for_byte_unchanged() -> None:
    payload = (ROOT / "config" / "prompts" / "profile_signal_extraction_v1.md").read_bytes()
    assert hashlib.sha256(payload).hexdigest() == "4021dc9feb9441720e92325ca70f58deac5d7fcfb12690655c56a30512727192"


def test_private_directory_is_git_ignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "-q", "data/private/golden_case/profile_input.json"],
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0


def test_private_golden_case_is_not_tracked() -> None:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "data/private/golden_case/profile_input.json"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    assert result.returncode != 0


def test_normal_git_add_dry_run_cannot_stage_private_golden_case() -> None:
    result = subprocess.run(
        ["git", "add", "--dry-run", "data/private/golden_case/profile_input.json"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    assert result.returncode != 0


def test_public_tests_do_not_reference_private_fixture_contents() -> None:
    institution = "City University" + " of Hong Kong"
    course_code = "SYE" + "6601"
    for path in (ROOT / "tests").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert institution not in text
        assert course_code not in text


def test_phase3_has_no_forbidden_framework_or_external_data_imports() -> None:
    forbidden = {"langgraph", "langchain", "streamlit", "chromadb", "sqlite3", "canvasapi"}
    imported = set()
    for path in ROOT.rglob("*.py"):
        if ".venv" in path.parts or "data/private" in path.as_posix():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(forbidden)


def test_qwen_transport_remains_explicit_live_only() -> None:
    source = (ROOT / "agents" / "self_discovery_demo.py").read_text(encoding="utf-8")
    assert "if live:" in source
    assert "QwenProvider.from_settings" in source
    assert "--live" in source
