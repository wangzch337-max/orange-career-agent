"""Exact D.4 scope and source pins preserve historical guards and authority."""

import ast
import hashlib
import json
from pathlib import Path
from uuid import uuid4
import pytest
from tests.career_reality_contract import (
    D4_FREEZE, D4_PATHS, D4_SOURCE_PATH, D4_SOURCE_HASH, D4_INTEGRATION_HASHES,
    D4_PROJECTION_HASHES, assert_d2_source_delta, pre_d2_bytes,
)
from tests.freeze_contract import changed_paths, assert_original_inventory
from tests.test_role_landscape import h, offline
from tests.test_specific_role import expanded
from specific_role.sources import SOURCE_HASH
from ui.chat_runtime import Workspace, WorkspaceMode

ROOT = Path(__file__).resolve().parents[1]
EXACT_DELTA = D4_PATHS | {
    "ui/chat_runtime.py", "ui/conversation_shell.py", "ui/role_landscape.py", "career_reality/service.py",
    "tests/career_reality_contract.py", "tests/test_career_reality_contract.py", "tests/test_role_landscape_contract.py",
    "tests/test_conversation_shell.py",
    "README.md", "PRODUCT_SPEC.md", "ARCHITECTURE.md", "DATA_CONTRACTS.md", "IMPLEMENTATION_PLAN.md", "AGENTS.md",
    "docs/ORANGE_AGENT_RUNTIME.md", "docs/ROLE_LANDSCAPE_EXPLORATION.md",
}


def test_exact_d4_delta_and_every_protected_production_inventory():
    assert changed_paths(ROOT, D4_FREEZE, ".") == EXACT_DELTA
    assert not any("*" in name for name in EXACT_DELTA)
    for scope in ("agents", "providers", "memory", "workflows", "career_discovery", "career_runtime",
                  "clarification", "profile_refinement", "resume_intake", "resume_evidence", "config", "requirements.txt", "data/models.py"):
        assert not changed_paths(ROOT, D4_FREEZE, scope), scope
        assert_original_inventory(ROOT, D4_FREEZE, scope)
    assert changed_paths(ROOT, D4_FREEZE, "data") == {D4_SOURCE_PATH}
    assert_d2_source_delta(ROOT)
    assert SOURCE_HASH == D4_SOURCE_HASH == hashlib.sha256((ROOT / D4_SOURCE_PATH).read_bytes()).hexdigest()


@pytest.mark.parametrize("name", tuple(D4_INTEGRATION_HASHES | D4_PROJECTION_HASHES))
def test_exact_integration_bytes_no_wildcard_or_arbitrary_extra_byte(name):
    pin = (D4_INTEGRATION_HASHES | D4_PROJECTION_HASHES)[name]
    current = (ROOT / name).read_bytes()
    assert hashlib.sha256(current).hexdigest() == pin
    assert hashlib.sha256(current + b"\n").hexdigest() != pin
    if name in D4_INTEGRATION_HASHES:
        assert pre_d2_bytes(ROOT, name, current + b"\n") == current + b"\n"
        assert pre_d2_bytes(ROOT, "./" + name, current) == current


@pytest.mark.parametrize("name", ["models.py", "sources.py", "service.py", "session.py"])
def test_d4_has_no_provider_evaluation_profile_memory_match_or_tool_coupling(name):
    text = (ROOT / "specific_role" / name).read_text()
    tree = ast.parse(text)
    modules = [(n.module or "") for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    modules += [alias.name for n in ast.walk(tree) if isinstance(n, ast.Import) for alias in n.names]
    assert not {m.split(".")[0] for m in modules} & {"agents", "providers", "memory", "evaluation", "career_background_evaluation", "career_runtime", "tools", "workflows"}
    assert all(v not in text for v in ("memory_service", "get_current_confirmed_profile", "load_llm_settings", "demo_jobs.json", "MatchResult"))


def test_switch_away_return_and_new_workspace_do_not_restore_context(h):
    s = expanded(h)
    w = h.workspace
    original = w.thread.thread_id
    w.create_new_thread(); w.activate(original)
    assert s.binding is None and not s.messages
    assert s.submit("详细讲讲第一种") and s.messages[-1].reply is None
    owner, root = w.owner_scope_id, w.root
    assert "specific_role" not in json.dumps(w._snapshot())
    w.close()
    with Workspace(owner, root) as restored:
        assert restored.specific_role.binding is None and not restored.specific_role.messages
        assert restored.specific_role.submit("详细讲讲第一种") and restored.specific_role.messages[-1].reply is None


def test_foreign_owner_cannot_use_owned_token_or_ephemeral_context(h, tmp_path):
    s = expanded(h)
    with Workspace(str(uuid4()), tmp_path / "foreign", mode=WorkspaceMode.NORMAL) as other:
        assert other.specific_role.submit("这个角色通常和谁合作？", token=s.token())
        assert other.specific_role.binding is None and not other.specific_role.messages
        assert other.runtime_mode == WorkspaceMode.NORMAL
        assert other.specific_role.submit("详细讲讲第二种") and other.specific_role.messages[-1].reply is None
    assert s.current()


@pytest.mark.parametrize("doc", ["README.md", "PRODUCT_SPEC.md", "ARCHITECTURE.md", "DATA_CONTRACTS.md", "IMPLEMENTATION_PLAN.md", "AGENTS.md", "docs/ORANGE_AGENT_RUNTIME.md", "docs/ROLE_LANDSCAPE_EXPLORATION.md"])
def test_current_docs_distinguish_d4_understanding_from_match_and_polish(doc):
    source = (ROOT / doc).read_text()
    assert "v1.3D.4" in source
    assert "Representative Specific Role Understanding" in source or "代表性具体角色理解" in source
    assert "Match" in source and "Profile" in source and "Memory" in source


def test_d4_focused_evaluation_is_external_and_all_nine_cases_are_checked(tmp_path):
    from career_background_evaluation.specific import evaluate_specific
    assert evaluate_specific(tmp_path, "Business Analysis", 1) >= 100
