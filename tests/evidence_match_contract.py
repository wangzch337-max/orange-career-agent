"""Exact D.5 authorization, composing rather than bypassing older freezes."""

import hashlib
import subprocess
from tests.evidence_validation_contract import pre_d6_bytes

D5_FREEZE = "044c8a2e026adaa2de66d97e652d78f8d20786d1"
D5_PATHS = {
    "evidence_match/__init__.py", "evidence_match/models.py", "evidence_match/projection.py",
    "evidence_match/service.py", "evidence_match/session.py", "evidence_match/prompts/relationships_v1.md",
    "ui/evidence_match.py", "agents/match_insight.py", "ui/chat_runtime.py",
    "ui/conversation_shell.py", "ui/specific_role.py", "career_background_evaluation/match.py",
    "tests/test_evidence_match.py", "tests/test_evidence_match_ui.py", "tests/evidence_match_contract.py",
    "tests/test_evidence_match_contract.py", "tests/test_specific_role_ui.py",
    "tests/career_reality_contract.py", "tests/test_career_reality_contract.py",
    "tests/test_specific_role_contract.py", "tests/test_career_discovery_safety.py",
    "tests/test_conversation_shell.py", "tests/test_onboarding.py", "tests/test_onboarding_tuning.py",
    "README.md", "PRODUCT_SPEC.md", "ARCHITECTURE.md", "DATA_CONTRACTS.md", "IMPLEMENTATION_PLAN.md",
    "AGENTS.md", "docs/ORANGE_AGENT_RUNTIME.md", "docs/REPRESENTATIVE_SPECIFIC_ROLE.md",
    "docs/EVIDENCE_BASED_MATCH.md",
}
D5_INTEGRATION_HASHES = {
    "agents/match_insight.py": "67780504ef669ed07005fab0b5678828744501ac06157e3b4cb4ba43de5e5539",
    "ui/chat_runtime.py": "445f7dca084293f01119f96cddb3dc18661259a2edcd2525cc51b9bbc3812867",
    "ui/conversation_shell.py": "ddbd28905c0ddf99bc573a95b67ddab239baeabdb23295a90cead6bdda3b76b2",
    "ui/specific_role.py": "18d001f5a385ab9cf098ac49dfbeb580a9453c27ba648029d451c2795a5c16a4",
    "tests/test_specific_role_ui.py": "10c0c0c86cb30b4cf8dbdecca3c1bfce3a85926fd27d89946b8a89efafa09e50",
    "tests/test_conversation_shell.py": "324b8c5ceaad0f414502f7600ad0764602a8a7b4693dc711337015dd6dcc441e",
    "tests/test_onboarding.py": "965bb0ba4f12de1c4357c32906dd5b58b5fdbbcef606e010cbad4196e3547d5b",
    "tests/test_onboarding_tuning.py": "b2b88c7d33f149a534a7afbd3db0193806865164e350e6f34a6a25201253f7a0",
}
D5_PROMPT_PATH = "evidence_match/prompts/relationships_v1.md"
D5_PROMPT_HASH = "7dc7cecaee06d81444af552d27803a21baf925f7c08ce171a5b6c6c9b37b25e0"


def pre_d5_bytes(root, name, current):
    current = pre_d6_bytes(root, name, current)
    if name in D5_INTEGRATION_HASHES and hashlib.sha256(current).hexdigest() == D5_INTEGRATION_HASHES[name]:
        return subprocess.check_output(["git", "show", f"{D5_FREEZE}:{name}"], cwd=root)
    return current


def assert_match_extension(root, baseline):
    """Allow ONLY the pinned independent entry point; freeze every legacy byte."""
    from tests.freeze_contract import changed_paths, assert_original_inventory
    assert changed_paths(root, baseline, "agents") == {"agents/match_insight.py"}
    assert_original_inventory(root, baseline, "agents")
    current = (root / "agents/match_insight.py").read_bytes()
    original = subprocess.check_output(["git", "show", f"{baseline}:agents/match_insight.py"], cwd=root)
    assert pre_d5_bytes(root, "agents/match_insight.py", current) == original
