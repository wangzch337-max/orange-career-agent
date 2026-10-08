"""Exact D.6 scope, synthetic fixture, independent authority and docs."""

import ast
import hashlib
from pathlib import Path
import subprocess
import pytest
from tests.evidence_validation_contract import D6_FREEZE, D6_PATHS, D6_SOURCE_PATH, D6_SOURCE_HASH, D6_INTEGRATION_HASHES, pre_d6_bytes
from tests.freeze_contract import changed_paths, assert_original_inventory
from tests.career_reality_contract import assert_d2_source_delta
from tests.online_foundation_contract import PACK1_PATHS, pre_pack1_bytes, assert_pre_pack1_scope

ROOT = Path(__file__).resolve().parents[1]


def test_exact_d6_scope_without_private_artifact_wildcard_exemptions():
    assert changed_paths(ROOT,D6_FREEZE,".")==D6_PATHS | PACK1_PATHS
    assert not any("*" in p for p in D6_PATHS)
    for scope in ("agents","providers","memory","workflows","career_discovery","career_reality",
        "role_landscape","specific_role","career_runtime","clarification","profile_refinement",
        "resume_intake","resume_evidence","config","requirements.txt","data/models.py"):
        assert_pre_pack1_scope(ROOT,D6_FREEZE,scope)
    assert changed_paths(ROOT,D6_FREEZE,"data")=={D6_SOURCE_PATH}
    assert_d2_source_delta(ROOT)
    from evidence_validation.sources import SOURCE_HASH
    assert SOURCE_HASH==D6_SOURCE_HASH==hashlib.sha256((ROOT/D6_SOURCE_PATH).read_bytes()).hexdigest()


@pytest.mark.parametrize("name",tuple(D6_INTEGRATION_HASHES))
def test_exact_integration_pin_rejects_extra_byte_and_alias(name):
    current=(ROOT/name).read_bytes()
    assert hashlib.sha256(pre_pack1_bytes(ROOT,name,current)).hexdigest()==D6_INTEGRATION_HASHES[name]
    original=subprocess.check_output(["git","show",f"{D6_FREEZE}:{name}"],cwd=ROOT)
    assert pre_d6_bytes(ROOT,name,current)==original
    assert pre_d6_bytes(ROOT,name,current+b"\n")==current+b"\n"
    assert pre_d6_bytes(ROOT,"./"+name,current)==current


@pytest.mark.parametrize("name",["models.py","sources.py","service.py","session.py"])
def test_no_canonical_mutator_memory_read_provider_storage_or_eval_coupling(name):
    text=(ROOT/"evidence_validation"/name).read_text(); tree=ast.parse(text)
    names={n.id for n in ast.walk(tree) if isinstance(n,ast.Name)}|{n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}
    assert not names & {"get_current_confirmed_profile","retrieve_context","memory_store","list_memories","save_confirmed_profile",
        "create_confirmed","create_candidate","supersede","append_turn","save_snapshot","start","confirm",
        "load_llm_settings","load_dotenv","QwenProvider","MatchResult","JobRecord","JobIntelligenceRecord","socket","requests","httpx"}
    modules=[n.module or "" for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    assert not any(m.startswith(("evaluation","agent_evaluation","career_background_evaluation","providers","memory","workflows")) for m in modules)
    assert ".env.local" not in text and "demo_jobs.json" not in text


def test_legacy_d5_bytes_preserved_except_exact_unknown_question():
    current=(ROOT/"evidence_match/session.py").read_bytes()
    original=subprocess.check_output(["git","show",f"{D6_FREEZE}:evidence_match/session.py"],cwd=ROOT)
    assert current==original.replace("|还是unknown|仍未知".encode(),"|还是unknown|是unknown|仍未知".encode(),1)


@pytest.mark.parametrize("doc",["README.md","PRODUCT_SPEC.md","ARCHITECTURE.md","DATA_CONTRACTS.md","IMPLEMENTATION_PLAN.md","AGENTS.md",
    "docs/ORANGE_AGENT_RUNTIME.md","docs/EVIDENCE_BASED_MATCH.md","docs/EVIDENCE_GAP_VALIDATION.md"])
def test_docs_distinguish_d6_uncertainty_from_capability_or_plans(doc):
    text=(ROOT/doc).read_text()
    assert "D.6" in text and "session-only" in text
    assert "Profile" in text and "Memory" in text and "D.5" in text
    assert "Action Plan" in text and "score" in text and "handoff" in text


def test_external_observer_runs_real_synthetic_d6_checks(tmp_path):
    from career_background_evaluation.validation import evaluate_validation
    from specific_role.sources import SpecificRoleRegistry
    assert evaluate_validation(tmp_path,SpecificRoleRegistry().inventory().records[0])>=25
