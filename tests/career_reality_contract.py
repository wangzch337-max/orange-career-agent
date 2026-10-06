"""Exact approved D.2 scope; no wildcard exemptions to previous safety gates."""

import hashlib
import subprocess

D1_FREEZE = "2316616ca8244d545d966f1064c7f7b798d53b22"
D2_PATHS = {
    "career_reality/__init__.py", "career_reality/models.py", "career_reality/sources.py",
    "career_reality/service.py", "career_reality/session.py", "ui/career_reality.py",
    "data/fixtures/career_reality/work_sources.json", "career_background_evaluation/reality.py",
    "tests/test_career_reality.py", "tests/test_career_reality_ui.py", "tests/career_reality_contract.py",
    "tests/test_career_reality_contract.py", "tests/test_career_discovery_safety.py",
    "tests/test_profile_conversation_ui.py", "tests/profile_conversation_contract.py",
    "tests/test_ui_rendering.py", "tests/test_freeze_contract.py",
    "tests/test_conversation_shell.py",
    "ui/career_discovery.py", "ui/chat_runtime.py", "ui/conversation_shell.py",
    "README.md", "PRODUCT_SPEC.md", "ARCHITECTURE.md", "DATA_CONTRACTS.md", "IMPLEMENTATION_PLAN.md",
    "AGENTS.md", "docs/CAREER_DIRECTION_DISCOVERY.md", "docs/CHAT_NATIVE_PROFILE_CONVERSATION.md",
    "docs/ORANGE_AGENT_RUNTIME.md", "docs/CAREER_REALITY_EXPLORATION.md",
    # Explicitly authorized P0/P1 pack: exact paths, no new domain/source scope.
    "career_discovery/session.py", "career_discovery/dialogue.py", "career_runtime/session.py",
    "ui/chat_opening.py", "tests/test_discovery_dialogue.py", "tests/test_chat_opening.py",
    "tests/test_ux_fix_ui.py", "tests/test_chat_product.py",
    "tests/test_generation_control.py",
    # Explicit D.1 public-demo blocker fix; normal runtime still fails closed.
    "career_discovery/demo.py", "data/fixtures/career_discovery/public_demo_proposal.json",
    "ui/app.py", "tests/career_discovery_doubles.py", "tests/test_public_discovery_demo.py",
}

D2_SOURCE_PATH = "data/fixtures/career_reality/work_sources.json"
D2_SOURCE_HASH = "26d11d83b155694d8eeea500f7f54a82a747ee16559a1832840267f6ff1cebc3"
DEMO_PROPOSAL_PATH = "data/fixtures/career_discovery/public_demo_proposal.json"
DEMO_PROPOSAL_HASH = "28b0723f84d2a28289c6cdb7fa15ad0a05f9d449661c817b32458b47ad52bc23"

# Explicit D.3 source/service/session/UI/docs/test extension, not a wildcard.
D3_PATHS = {
    "role_landscape/__init__.py", "role_landscape/models.py", "role_landscape/sources.py",
    "role_landscape/service.py", "role_landscape/session.py", "ui/role_landscape.py",
    "data/fixtures/role_landscape/role_sources.json", "docs/ROLE_LANDSCAPE_EXPLORATION.md",
    "career_background_evaluation/landscape.py", "tests/test_role_landscape.py",
    "tests/test_role_landscape_ui.py", "tests/test_role_landscape_contract.py",
}
D2_PATHS |= D3_PATHS  # Compose the exact authorized additions for older scope gates.
D3_SOURCE_PATH = "data/fixtures/role_landscape/role_sources.json"
D3_SOURCE_HASH = "4d27dce2284bc0fe02c1d5f388d068af05add6ba15c8420324361dea7a117e33"


def assert_d2_source_delta(root, *, inventory_baseline=D1_FREEZE):
    from tests.freeze_contract import changed_paths, historical_paths, repository_paths
    additions = {D2_SOURCE_PATH, DEMO_PROPOSAL_PATH, D3_SOURCE_PATH}
    assert changed_paths(root, D1_FREEZE, "data") == additions
    assert repository_paths(root, "data") == historical_paths(root, inventory_baseline, "data") | additions
    assert hashlib.sha256((root / D2_SOURCE_PATH).read_bytes()).hexdigest() == D2_SOURCE_HASH
    assert hashlib.sha256((root / DEMO_PROPOSAL_PATH).read_bytes()).hexdigest() == DEMO_PROPOSAL_HASH
    assert hashlib.sha256((root / D3_SOURCE_PATH).read_bytes()).hexdigest() == D3_SOURCE_HASH

# Approved new integration bytes will compose with the original D.1 pins;
# unapproved mutations still face every historical guard.
D2_INTEGRATION_HASHES = {
    "ui/app.py": "72f41424e5be0c234a2535252876d0c7f24c792b4eb6d80121c0f3c401507d70",
    "tests/test_conversation_shell.py": "cb6ebd1048577b0077eed13aabae6ccdfd626aea7a70c3a5c65c354748d7460c",
    "tests/test_chat_product.py": "c4bb9f1027350279dd96007260c397ffe3a1b2df56c4f048ad7d6a9f9b2927bb",
    "career_runtime/session.py": "113958afccbb4dc307d3bff601967f4a25b9ddbc2e738d5cc95ce119e87c8394",
    "career_discovery/session.py": "780e49ab0e6e0414ac9a18b3f164923f6fc91f0ed1847a1f0b52a222b9c8a735",
    "ui/chat_runtime.py": "545408bc278c12e7bd751c2b4b8fec40c33fd65939178a83478e0e4068572013",
    "ui/conversation_shell.py": "35cf8cb777c1792b074e8040597e9706f3171f5c3e727195d7cc4a1fb609f2af",
    "tests/test_ui_rendering.py": "476f78d1040a7b0203a89e6f642b93dc78507fa3bb14bafe515ade0a3c5c4e22",
}


D3_INTEGRATION_HASHES = {
    "tests/test_conversation_shell.py": "bf84b3b959281b5e28da618289ae0dccfc4ea14bd63b90d5bf7a79874493c705",
    "ui/chat_runtime.py": "3e784eaa4d7ab997acea2450df154e9e99167ab98d7e1b7a5a97eb198da377c8",
    "ui/conversation_shell.py": "f0bef0008ddb1b5ea1d1a0da8953106576d9517d8c23c16155ed7a79ee4f9326",
}


def pre_d2_bytes(root, name, current):
    pins = D2_INTEGRATION_HASHES | D3_INTEGRATION_HASHES
    if name in pins and hashlib.sha256(current).hexdigest() == pins[name]:
        return subprocess.check_output(["git", "show", f"{D1_FREEZE}:{name}"], cwd=root)
    return current
