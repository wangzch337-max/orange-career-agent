"""Exact Pack 1 storage integration; preserve every older domain/source guard."""

import hashlib
import subprocess

PACK1_BASELINE = "b319c67060cddba219d29522a3b784910dcfe2d3"
PACK1_PATHS = {
    "storage/__init__.py", "storage/contracts.py", "storage/conversation.py",
    "storage/memory.py", "storage/vector.py", "storage/settings.py",
    "storage/checkpoint.py", "storage/workspace.py",
    "memory/base.py", "memory/service.py", "ui/chat_runtime.py",
    "ui/demo_controller.py", "career_runtime/session.py",
    "tests/test_workspace_storage.py", "tests/test_storage_career_parity.py",
    "tests/online_foundation_contract.py", "tests/test_online_foundation_contract.py",
    "tests/evidence_validation_contract.py", "tests/test_evidence_validation_contract.py",
    "tests/test_evidence_match_contract.py", "tests/test_specific_role_contract.py",
    "tests/career_reality_contract.py", "tests/test_career_reality_contract.py",
    "tests/test_career_discovery_memory.py", "tests/test_agent_runtime.py",
    "tests/test_agent_planning.py",
    "tests/test_conversation_shell.py", "tests/test_demo_flow.py",
    "tests/v12_contract.py", "tests/test_onboarding_tuning.py", "tests/test_resume_career_e2e.py",
    "README.md", "ARCHITECTURE.md", "IMPLEMENTATION_PLAN.md", "AGENTS.md",
    "docs/ONLINE_FOUNDATION_STORAGE.md",
}

# Reviewed integration bytes only, not a broad exemption for a directory.
PACK1_INTEGRATION_HASHES = {
    "tests/v12_contract.py": "bc29557580c910fc31bcc0334632c0e682b4b8d0ecebf1d18aaa08dfdef11d50",
    "tests/test_onboarding_tuning.py": "05fe09d221af8cdcf8430c8705a3ce5fa6cb18aa1d1bb6f13be378284621a50b",
    "tests/test_resume_career_e2e.py": "20dd8a60e86c100ff5e4dd8572463002370b45502440811231325b9ea0c5135e",
    "tests/test_conversation_shell.py": "bb4ed0b5ebf5bf8fd3ff3becaf31a6045c2a85e2888457478bb433302c2ae28c",
    "tests/test_demo_flow.py": "8623218dadc9af460b768a16e54dd72f5ffb051bec37b54a30707af1e9569c4b",
    "tests/test_agent_planning.py": "be4db909d69049f13ab90c1f2a9c570a859bcb301da1a0f9d699ff52c6581000",
    "tests/test_career_discovery_memory.py": "9e1a4dc62591b3aed3500115eb265acd145ed5e190f91ca96a14267f693fd7ed",
    "tests/test_agent_runtime.py": "24c36c7d0cf43195399d7ccfc4bab27adf2d3fb1a5c372478fe61016e816929b",
    "memory/base.py": "2b1c0dbd2f1de74bdf44234c12493a72dc9c0eec2f5293f5be112aade8948928",
    "memory/service.py": "825a240b91a83f656994e0b116a869055528a2137f4030769dc39644d4821c8a",
    "ui/chat_runtime.py": "d036c113bc855901995dc7ab9b360c7cd6a2b3ae51a3b7506cba659271a5b099",
    "ui/demo_controller.py": "28ea7b2d4f10c3a29214959af70552019eb02a69daca7681f1a520a64cfbd89b",
    "career_runtime/session.py": "5ab10f204cc0c64b9a553b8de9376f068b6858db24b98028d6701a54483cf2be",
    "tests/evidence_validation_contract.py": "9af903f7b08322d39852d8e455ea46b0e7380893f28e97096912a1b1e6381120",
    "tests/test_evidence_validation_contract.py": "d565866b799eacb3eec89ab585bd9357882e00db9520c68b475e6a3614365517",
    "tests/test_evidence_match_contract.py": "9abfab62ea6d11298813f64b0d2c1898a9278ec1bba60e8f088adbf286ecfcc9",
    "tests/test_specific_role_contract.py": "067f9b924a8cea1f33d9cf85e7c019c2605c7545f20fba2c5e56de7701b34097",
    "tests/career_reality_contract.py": "1d1f6f84cc41b163527db622f8c40f00a38411597f7cb82f920b29265d435525",
    "tests/test_career_reality_contract.py": "97cbe0c2162792bf5017ceb7214be2c6495078750855676871b8aab393156dad",
}


def pre_pack1_bytes(root, name, current):
    if name in PACK1_INTEGRATION_HASHES and hashlib.sha256(current).hexdigest() == PACK1_INTEGRATION_HASHES[name]:
        return subprocess.check_output(["git", "show", f"{PACK1_BASELINE}:{name}"], cwd=root)
    return current


def assert_pre_pack1_scope(root, baseline, scope):
    """Only exactly pinned integration deltas may compose with protected scopes."""
    from tests.freeze_contract import changed_paths, assert_original_inventory
    for name in changed_paths(root, baseline, scope):
        assert name in PACK1_INTEGRATION_HASHES, name
        current = (root / name).read_bytes()
        original = subprocess.check_output(["git", "show", f"{baseline}:{name}"], cwd=root)
        assert pre_pack1_bytes(root, name, current) == original, name
    assert_original_inventory(root, baseline, scope)
