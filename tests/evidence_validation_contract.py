"""D.6 exact approval; compose old freezes without widening their authority."""

import hashlib
import subprocess
from tests.online_foundation_contract import pre_pack1_bytes

D6_FREEZE = "d84005af3ba28c717e54ae1ee076b5f220b5d884"
D6_SOURCE_PATH = "data/fixtures/evidence_validation/experiments.json"
D6_SOURCE_HASH = "4bbcb8b0db1dc517020720bb9f2ba2b17fc8a5ff5f96fd7297d3b69322f0ce23"
D6_PATHS = {
    "evidence_validation/__init__.py", "evidence_validation/models.py", "evidence_validation/sources.py",
    "evidence_validation/service.py", "evidence_validation/session.py", D6_SOURCE_PATH,
    "ui/evidence_validation.py", "ui/evidence_match.py", "ui/chat_runtime.py", "ui/conversation_shell.py",
    "evidence_match/session.py", "career_background_evaluation/validation.py",
    "tests/test_evidence_validation.py", "tests/test_evidence_validation_ui.py",
    "tests/evidence_validation_contract.py", "tests/test_evidence_validation_contract.py",
    "tests/evidence_match_contract.py", "tests/test_evidence_match_contract.py",
    "tests/career_reality_contract.py", "tests/test_career_reality_contract.py",
    "tests/test_specific_role_contract.py", "tests/test_conversation_shell.py",
    "README.md", "PRODUCT_SPEC.md", "ARCHITECTURE.md", "DATA_CONTRACTS.md", "IMPLEMENTATION_PLAN.md", "AGENTS.md",
    "docs/ORANGE_AGENT_RUNTIME.md", "docs/EVIDENCE_BASED_MATCH.md", "docs/EVIDENCE_GAP_VALIDATION.md",
}
D6_INTEGRATION_HASHES = {
    "ui/chat_runtime.py": "cb62bf35450bdd1d90ad9f6dd49faf568d9534ab8ce111f271e39042845e716f",
    "ui/conversation_shell.py": "09a6111a57f0b5c7d76be9207d91a2769e245d016a4e51624a40fe93ed17361a",
    "ui/evidence_match.py": "6754d3e6b2786a4c0e23e68727a843a8454b5de9bf257945c6b145808059eba2",
    "evidence_match/session.py": "e53def5acbcbb3fd738206bcf6ef60b6f5a899627e8eb41d89581f6feef27aac",
    "tests/test_conversation_shell.py": "7be586d128e1c3fc04aa6187da7ac73023c9eb9dd19d653d218463e7df703fd7",
}


def pre_d6_bytes(root, name, current):
    current = pre_pack1_bytes(root, name, current)
    if name in D6_INTEGRATION_HASHES and hashlib.sha256(current).hexdigest() == D6_INTEGRATION_HASHES[name]:
        return subprocess.check_output(["git", "show", f"{D6_FREEZE}:{name}"], cwd=root)
    return current
