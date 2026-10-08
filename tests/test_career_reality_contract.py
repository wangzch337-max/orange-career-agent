"""D.2 may extend selection UI, never rewrite frozen authority/prompt logic."""

import hashlib
from pathlib import Path
import subprocess
import pytest
from tests.career_reality_contract import D1_FREEZE, D2_PATHS, D2_INTEGRATION_HASHES, D3_INTEGRATION_HASHES, D4_INTEGRATION_HASHES, D2_SOURCE_PATH, assert_d2_source_delta, pre_d2_bytes
from tests.freeze_contract import changed_paths
from tests.evidence_match_contract import pre_d5_bytes, assert_match_extension

ROOT = Path(__file__).resolve().parents[1]


def test_exact_d2_scope_and_frozen_authority_dependencies():
    assert changed_paths(ROOT, D1_FREEZE, ".") <= D2_PATHS
    assert not any("*" in path for path in D2_PATHS)
    assert_match_extension(ROOT, D1_FREEZE)
    for scope in ("providers", "workflows", "memory", "clarification", "profile_refinement",
                  "resume_intake", "resume_evidence", "config/prompts", "data/models.py", "requirements.txt"):
        assert not changed_paths(ROOT, D1_FREEZE, scope), scope
    assert changed_paths(ROOT, D1_FREEZE, "career_discovery") == {"career_discovery/session.py", "career_discovery/dialogue.py", "career_discovery/demo.py"}
    assert changed_paths(ROOT, D1_FREEZE, "career_runtime") == {"career_runtime/session.py"}
    old_runtime = subprocess.check_output(["git", "show", f"{D1_FREEZE}:career_runtime/session.py"], cwd=ROOT)
    # The QA engine is byte-preserved except its explicit pending-state hook.
    expected = old_runtime.replace(
        b"# New explicit context invalidates D.1's ephemeral direction review,\n            # without loading discovery Profile/Memory or changing chat routing.",
        b"# Completed direction reviews clear. A valid pending clarification\n            # pauses under its existing authority binding, without new retrieval.").replace(
        b"if discovery is not None:\n                discovery.invalidate()",
        b"if discovery is not None:\n                discovery.on_general_qa()")
    assert (ROOT / "career_runtime/session.py").read_bytes() == expected
    old_test = subprocess.check_output(["git", "show", f"{D1_FREEZE}:tests/test_generation_control.py"], cwd=ROOT)
    expected_test = old_test.replace(
        b"assert not value.exception and not value.chat_message and not value.chat_input[0].disabled",
        b"assert not value.exception and not value.chat_input[0].disabled\n"
        b'        assert len(value.chat_message) == 1 and value.chat_message[0].name == "assistant"\n'
        b"        assert not w.chat.messages and not w.store.list_messages(w.owner_scope_id, w.thread.thread_id)")
    assert (ROOT / "tests/test_generation_control.py").read_bytes() == expected_test


@pytest.mark.parametrize("name", ["ui/app.py", "ui/chat_runtime.py", "ui/conversation_shell.py", "tests/test_ui_rendering.py", "tests/test_conversation_shell.py", "career_runtime/session.py", "career_discovery/session.py", "tests/test_chat_product.py"])
def test_d2_pin_composes_without_accepting_arbitrary_edits(name):
    original = subprocess.check_output(["git", "show", f"{D1_FREEZE}:{name}"], cwd=ROOT)
    current = (ROOT / name).read_bytes()
    assert hashlib.sha256(pre_d5_bytes(ROOT, name, current)).hexdigest() == (D2_INTEGRATION_HASHES | D3_INTEGRATION_HASHES | D4_INTEGRATION_HASHES)[name]
    assert pre_d2_bytes(ROOT, name, current) == original
    assert pre_d2_bytes(ROOT, name, current + b"\n") == current + b"\n"
    assert pre_d2_bytes(ROOT, "./" + name, current) == current


@pytest.mark.parametrize("mutation", ["extra_path", "changed_bytes", "changed_demo_bytes", "changed_role_bytes"])
def test_d2_source_exception_rejects_other_data_changes(monkeypatch, mutation):
    assert_d2_source_delta(ROOT)
    if mutation == "extra_path":
        monkeypatch.setattr("tests.freeze_contract.changed_paths", lambda *a: {D2_SOURCE_PATH, "data/unapproved.json"})
    else:
        original = Path.read_bytes
        from tests.career_reality_contract import DEMO_PROPOSAL_PATH, D3_SOURCE_PATH
        target = {"changed_demo_bytes":DEMO_PROPOSAL_PATH, "changed_role_bytes":D3_SOURCE_PATH}.get(mutation, D2_SOURCE_PATH)
        monkeypatch.setattr(Path, "read_bytes", lambda p: original(p) + b"\n" if p == ROOT / target else original(p))
    with pytest.raises(AssertionError):
        assert_d2_source_delta(ROOT)


def test_integration_freeze_docs_keep_current_scope_and_separate_commit_authority():
    readme = (ROOT / "README.md").read_text()
    roadmap = readme.split("## Roadmap\n", 1)[1].split("## Documentation\n", 1)[0]
    assert "v1.3D.2 未开始" not in roadmap
    for capability in ("pending clarification routing", "state-aware New Chat opening",
                       "Public Synthetic D.1 Demo", "D.2 Career Reality Exploration",
                       "D.3 Role Landscape / Differences Conversation"):
        assert capability in roadmap
    assert "D.4 Representative Specific Role Understanding" in roadmap and "现有9个 Public Demo archetypes" in roadmap
    assert "checkpoint 为 `dfeb535`" in roadmap and "D.1–D.4 checkpoint 为 `044c8a2`" in roadmap
    assert "D.1–D.5 checkpoint 为 `d84005a`" in roadmap
    assert "本轮 D.6 Evidence Gap Validation 增量保持未提交" in roadmap
    assert "Final Product Polish 与人工产品验收尚未完成" in roadmap
    assert "全部通过也不授权暂存、commit 或 push" in readme
    assert "须等待产品负责人单独授权 checkpoint" in readme
    discovery = (ROOT / "docs/CAREER_DIRECTION_DISCOVERY.md").read_text()
    assert "普通 `WorkspaceMode.NORMAL`" in discovery
    assert "完整路径测试使用该入口的默认 provider" in discovery
