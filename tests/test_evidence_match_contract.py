"""D.5 exact approved delta plus unchanged authority/source inventories."""

import ast
import hashlib
from pathlib import Path
import subprocess
import pytest
from tests.evidence_match_contract import (
    D5_FREEZE, D5_PATHS, D5_INTEGRATION_HASHES, D5_PROMPT_PATH, D5_PROMPT_HASH,
    pre_d5_bytes, assert_match_extension,
)
from tests.freeze_contract import changed_paths, assert_original_inventory, historical_paths, repository_paths
from tests.career_reality_contract import assert_d2_source_delta
from tests.evidence_validation_contract import D6_PATHS, D6_SOURCE_PATH, pre_d6_bytes

ROOT = Path(__file__).resolve().parents[1]


def test_exact_d5_delta_no_wildcard_or_private_artifact_exemption():
    assert changed_paths(ROOT, D5_FREEZE, ".") == D5_PATHS | D6_PATHS
    assert not any("*" in name for name in D5_PATHS)
    assert_match_extension(ROOT, D5_FREEZE)
    for scope in ("providers", "memory", "workflows", "career_discovery", "career_reality",
                  "role_landscape", "specific_role", "career_runtime", "clarification",
                  "profile_refinement", "resume_intake", "resume_evidence", "config", "requirements.txt"):
        assert not changed_paths(ROOT, D5_FREEZE, scope), scope
        assert_original_inventory(ROOT, D5_FREEZE, scope)
    assert changed_paths(ROOT, D5_FREEZE, "data") == {D6_SOURCE_PATH}
    assert repository_paths(ROOT, "data") == historical_paths(ROOT, D5_FREEZE, "data") | {D6_SOURCE_PATH}
    assert_d2_source_delta(ROOT)


@pytest.mark.parametrize("name", tuple(D5_INTEGRATION_HASHES))
def test_approved_pins_reject_extra_byte_and_noncanonical_name(name):
    current = (ROOT / name).read_bytes()
    assert hashlib.sha256(pre_d6_bytes(ROOT, name, current)).hexdigest() == D5_INTEGRATION_HASHES[name]
    original = subprocess.check_output(["git", "show", f"{D5_FREEZE}:{name}"], cwd=ROOT)
    assert pre_d5_bytes(ROOT, name, current) == original
    assert pre_d5_bytes(ROOT, name, current + b"\n") == current + b"\n"
    assert pre_d5_bytes(ROOT, "./" + name, current) == current


def test_legacy_match_agent_bytes_are_preserved_except_single_entrypoint():
    current = (ROOT / "agents/match_insight.py").read_bytes()
    extension = (
        b'    def analyze_role_relationships(self, profile, source):\n'
        b'        """D.5 contract; no legacy jobs/actions/workflow, Fake only this phase."""\n'
        b'        from evidence_match.service import analyze\n'
        b'        return analyze(profile, source, self.llm_provider)\n\n'
    )
    assert current.count(extension) == 1
    original = subprocess.check_output(["git", "show", f"{D5_FREEZE}:agents/match_insight.py"], cwd=ROOT)
    assert current.replace(extension, b"", 1) == original


def test_independent_versioned_prompt_exact_bytes_and_no_legacy_prompt_change():
    assert hashlib.sha256((ROOT / D5_PROMPT_PATH).read_bytes()).hexdigest() == D5_PROMPT_HASH
    assert not changed_paths(ROOT, D5_FREEZE, "config/prompts")


@pytest.mark.parametrize("name", ["models.py", "projection.py", "service.py", "session.py"])
def test_d5_no_retrieval_mutator_live_provider_legacy_job_or_evaluation_coupling(name):
    path = ROOT / "evidence_match" / name
    source = path.read_text()
    tree = ast.parse(source)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not names & {"retrieve_context", "save_confirmed_profile", "create_confirmed", "create_candidate",
                        "supersede", "append_turn", "load_llm_settings", "load_dotenv", "QwenProvider",
                        "MatchResult", "JobRecord", "JobIntelligenceRecord", "socket", "requests", "httpx"}
    modules = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not any(m.startswith(("evaluation", "agent_evaluation", "career_background_evaluation")) for m in modules)
    assert ".env.local" not in source and "demo_jobs.json" not in source


@pytest.mark.parametrize("doc", ["README.md", "PRODUCT_SPEC.md", "ARCHITECTURE.md", "DATA_CONTRACTS.md",
    "IMPLEMENTATION_PLAN.md", "AGENTS.md", "docs/ORANGE_AGENT_RUNTIME.md", "docs/REPRESENTATIVE_SPECIFIC_ROLE.md", "docs/EVIDENCE_BASED_MATCH.md"])
def test_current_docs_preserve_d5_contract_and_boundary(doc):
    text = (ROOT / doc).read_text()
    assert "D.5" in text and "session-only" in text
    assert "Profile" in text and "Memory" in text and "ranking" in text


def test_external_d5_observer_executes_real_checks(tmp_path):
    from career_background_evaluation.match import evaluate_match
    from specific_role.sources import SpecificRoleRegistry
    count = evaluate_match(tmp_path, SpecificRoleRegistry().inventory().records[0])
    assert count >= 90
