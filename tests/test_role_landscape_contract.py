"""Exact authorized delta, public source pins and no personal/provider coupling."""

import ast
import hashlib
import json
from pathlib import Path
from uuid import uuid4
import pytest
from tests.career_reality_contract import D3_PATHS, D3_SOURCE_PATH, D3_SOURCE_HASH, assert_d2_source_delta
from tests.test_role_landscape import h, offline, opened
from ui.chat_runtime import Workspace

ROOT = Path(__file__).resolve().parents[1]


def test_exact_d3_inventory_and_source_pin():
    assert not any("*" in p for p in D3_PATHS)
    assert all((ROOT / p).is_file() for p in D3_PATHS)
    assert hashlib.sha256((ROOT / D3_SOURCE_PATH).read_bytes()).hexdigest() == D3_SOURCE_HASH
    assert_d2_source_delta(ROOT)


@pytest.mark.parametrize("name,pin", [
    ("models.py","5a6e7aa63cb6433a2c475ba321a22032b2aa2c2d8a17fa376df3216aef7a2f04"),
    ("service.py","a5a70fb8a9087eac115610c80abeb7bca2def0c023e8e8380c82513108f44071"),
    ("session.py","f334ac25a5ee393b06832b62b372359231f8a429107822418c434f1a47bc0c82"),
    ("sources.py","d363b1f70036297417077eac66d2b5ae5bc18db4caf908cf57020862332ff8c8"),
])
def test_d2_production_source_and_copy_remain_exact(name, pin):
    current = (ROOT / "career_reality" / name).read_bytes()
    if name == "service.py":
        # Exact authorized PURPOSE alias and bounded overall-work grammar only;
        # no source/copy/authority changes or permissive hash fallback.
        from tests.career_reality_contract import D4_FREEZE
        import subprocess
        original = subprocess.check_output(["git", "show", f"{D4_FREEZE}:career_reality/service.py"], cwd=ROOT)
        assert hashlib.sha256(original).hexdigest() == pin
        before = "|主要解决什么问题|存在的目的是什么|".encode()
        after = "|主要解决什么问题|整体在解决什么问题|存在的目的是什么|".encode()
        assert original.count(before) == 1
        expected = original.replace(before, after, 1)
        work_before = 'D.WORK: r"(?:平时(?:主要)?做什么|'.encode()
        work_after = 'D.WORK: r"(?:整体(?:是)?做什么(?:的)?|平时(?:主要)?做什么|'.encode()
        assert expected.count(work_before) == 1
        assert current == expected.replace(work_before, work_after, 1)
    else:
        assert hashlib.sha256(current).hexdigest() == pin


@pytest.mark.parametrize("name", ["models.py", "sources.py", "service.py", "session.py"])
def test_d3_has_no_provider_personal_memory_job_or_match_import(name):
    text = (ROOT / "role_landscape" / name).read_text()
    tree = ast.parse(text)
    modules = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert all(not (m or "").split(".")[0] in ("agents", "providers", "memory", "career_runtime", "tools", "workflows") for m in modules)
    assert all(v not in text for v in ("memory_service", "get_current_confirmed_profile", "load_llm_settings", "demo_jobs.json", "MatchResult"))


@pytest.mark.parametrize("field,value", [("owner","other"), ("thread","other"), ("request_id","other"), ("generation",999)])
def test_cross_scope_or_replayed_token_never_falls_to_qa(h, field, value):
    s = opened(h)
    token = s.token().model_copy(update={field:value})
    before = s.messages[:]
    assert s.submit("第一种主要做什么？", token=token) and s.messages == before


def test_new_workspace_cannot_restore_landscape_from_transcript_or_snapshot(h):
    s = opened(h)
    w = h.workspace
    owner, root, thread = w.owner_scope_id, w.root, w.thread.thread_id
    assert not w.store.list_messages(owner, thread) and "role_landscape" not in json.dumps(w._snapshot())
    w.close()
    with Workspace(owner, root) as restored:
        assert restored.role_landscape.binding is None and not restored.role_landscape.messages
        assert restored.role_landscape.submit("第一种主要做什么？")
        assert restored.role_landscape.messages[-1].reply is None


def test_other_thread_switch_never_restores_ephemeral_roles(h):
    s = opened(h)
    original_thread = h.workspace.thread.thread_id
    h.workspace.create_new_thread()
    h.workspace.activate(original_thread)
    assert not s.messages and s.binding is None
    assert s.submit("第一种主要做什么？") and s.messages[-1].reply is None
