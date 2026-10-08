"""Pack 1 scope is explicit; new storage does not weaken domain authority."""

import hashlib
from pathlib import Path
import subprocess
import pytest
from tests.freeze_contract import changed_paths, assert_original_inventory
from tests.online_foundation_contract import PACK1_BASELINE, PACK1_PATHS, PACK1_INTEGRATION_HASHES, pre_pack1_bytes

ROOT = Path(__file__).resolve().parents[1]


def test_exact_pack1_scope_and_unchanged_authority_sources():
    assert changed_paths(ROOT, PACK1_BASELINE, ".") == PACK1_PATHS
    assert not any("*" in name for name in PACK1_PATHS)
    for scope in ("agents", "providers", "workflows", "data", "config", "requirements.txt",
                  "career_discovery", "career_reality", "role_landscape", "specific_role",
                  "evidence_match", "evidence_validation", "resume_intake", "resume_evidence",
                  "clarification", "profile_refinement"):
        assert not changed_paths(ROOT, PACK1_BASELINE, scope), scope
        assert_original_inventory(ROOT, PACK1_BASELINE, scope)
    assert changed_paths(ROOT, PACK1_BASELINE, "memory") == {"memory/base.py", "memory/service.py"}
    assert changed_paths(ROOT, PACK1_BASELINE, "career_runtime") == {"career_runtime/session.py"}


@pytest.mark.parametrize("name", tuple(PACK1_INTEGRATION_HASHES))
def test_exact_pack1_pin_rejects_arbitrary_byte_and_noncanonical_alias(name):
    current = (ROOT / name).read_bytes()
    assert hashlib.sha256(current).hexdigest() == PACK1_INTEGRATION_HASHES[name]
    original = subprocess.check_output(["git", "show", f"{PACK1_BASELINE}:{name}"], cwd=ROOT)
    assert pre_pack1_bytes(ROOT, name, current) == original
    assert pre_pack1_bytes(ROOT, name, current + b"\n") == current + b"\n"
    assert pre_pack1_bytes(ROOT, "./" + name, current) == current


def test_documentation_does_not_claim_complete_guest_or_account_security():
    text = (ROOT / "docs/ONLINE_FOUNDATION_STORAGE.md").read_text()
    for term in ("Pack 1", "SQLite", "Ephemeral", "confirmation_guard", "expected_current",
                 "D.5/D.6", "session-only", "四个", "账户级安全", "尚未实现", "Memory",
                 "TTL", "认证", "PostgreSQL", "RLS", "可选", "停止条件"):
        assert term in text
