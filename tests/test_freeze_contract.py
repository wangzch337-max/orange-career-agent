"""Public, deterministic release-guard tests; no repository mutations or live IO."""

import hashlib
from pathlib import Path
import subprocess

import pytest

from tests import freeze_contract as contract
from tests.profile_refinement_contract import SHARED_HASHES, assert_c4_shared_delta
from tests.runtime_contract import V13C_FREEZE_PATHS, assert_resume_requirements


ROOT = Path(__file__).resolve().parents[1]
STATES = ("untracked", "tracked_modified", "staged", "committed")


def prompt_snapshots():
    historical = {"config/prompts/historical_v1.md": b"Frozen historical policy.\n"}
    current = {**historical, **{name: (ROOT / name).read_bytes()
                              for name in contract.RESUME_PROMPT_HASHES}}
    return historical, current


def test_fixed_checkpoint_contains_verified_pre_resume_content():
    baseline = contract.PRE_RESUME_BASELINE
    assert subprocess.check_output(["git", "cat-file", "-t", baseline], cwd=ROOT).strip() == b"commit"
    assert subprocess.check_output(["git", "show", "-s", "--format=%s", baseline], cwd=ROOT).strip() == b"test: adapt release guards for GitHub publication"
    assert not contract.historical_paths(ROOT, baseline, "config/prompts") & contract.RESUME_PROMPT_HASHES.keys()
    for name, (_, original_hash) in SHARED_HASHES.items():
        original = subprocess.check_output(["git", "show", f"{baseline}:{name}"], cwd=ROOT)
        assert hashlib.sha256(original).hexdigest() == original_hash
        current = (ROOT / name).read_bytes()
        assert_c4_shared_delta(name, current, original)
        with pytest.raises(AssertionError):
            assert_c4_shared_delta(name, current + b"\n", original)
    original = subprocess.check_output(["git", "show", f"{baseline}:requirements.txt"], cwd=ROOT)
    assert_resume_requirements((ROOT / "requirements.txt").read_bytes(), original)
    with pytest.raises(AssertionError):
        assert_resume_requirements((ROOT / "requirements.txt").read_bytes() + b"unexpected-package\n", original)


@pytest.mark.parametrize("state", STATES)
def test_identical_source_inventory_and_content_in_every_git_state(monkeypatch, state):
    historical, current = prompt_snapshots()
    additions = set(current) - set(historical)
    baseline, scope = contract.PRE_RESUME_BASELINE, "config/prompts"
    calls = []
    def fake_git(args, cwd):
        calls.append(tuple(args))
        outputs = {
            ("git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", scope): set(current),
            ("git", "ls-tree", "-r", "--name-only", "-z", baseline, "--", scope): set(historical),
            ("git", "diff", "--name-only", "--no-renames", "-z", baseline, "--", scope): set() if state == "untracked" else additions,
            ("git", "ls-files", "-z", "--others", "--exclude-standard", "--", scope): additions if state == "untracked" else set(),
        }
        return "".join(name + "\0" for name in sorted(outputs[tuple(args)])).encode()
    monkeypatch.setattr(subprocess, "check_output", fake_git)
    assert contract.repository_paths(ROOT, scope) == set(current)
    assert contract.historical_paths(ROOT, baseline, scope) == set(historical)
    assert contract.changed_paths(ROOT, baseline, scope) == additions
    contract.validate_prompt_inventory(historical, current)
    assert all("HEAD" not in args and "origin/main" not in args for args in calls)
    assert {args[1] for args in calls} <= {"ls-files", "ls-tree", "diff"}


@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("path", [
    "config/prompts/unapproved_v1.md", "docs/unapproved.md", "providers/debug.py",
    "data/private/resume.docx", ".env.local", "data/local/runtime.sqlite3",
    "artifacts/debug.log", "providers/request_payload.json",
])
def test_real_exact_scope_guard_rejects_unexpected_paths_in_every_state(monkeypatch, state, path):
    from tests import test_ui_rendering as rendering
    original = subprocess.check_output
    def with_unexpected(args, *positional, **kwargs):
        if args == ["git", "diff", "--name-only", rendering.BASELINE]:
            return path + "\n" if state != "untracked" else ""
        if args == ["git", "ls-files", "--others", "--exclude-standard"]:
            return path + "\n" if state == "untracked" else ""
        return original(args, *positional, **kwargs)
    monkeypatch.setattr(subprocess, "check_output", with_unexpected)
    with pytest.raises(AssertionError):
        rendering.test_repair_scope_has_no_other_ui_backend_dependency_or_test_edits()


@pytest.mark.parametrize("name", [
    "config/prompts/other_v2.md", "config/prompts/private_copy.md",
    "config/clarification_v1.md", "config/prompts/nested/clarification_v1.md",
    "config/prompts/.env", "config/prompts/request_payload.json",
])
def test_prompt_inventory_rejects_arbitrary_additions_and_alternate_locations(name):
    historical, current = prompt_snapshots()
    with pytest.raises(AssertionError):
        contract.validate_prompt_inventory(historical, {**current, name: b"Unexpected copy."})


@pytest.mark.parametrize("name", tuple(contract.RESUME_PROMPT_HASHES))
@pytest.mark.parametrize("change", ["missing", "changed", "renamed"])
def test_approved_prompts_are_required_exact_bytes_not_path_exemptions(name, change):
    historical, current = prompt_snapshots()
    if change == "changed":
        current[name] += b"\n"
    elif change == "missing":
        del current[name]
    else:
        current[name + ".copy"] = current.pop(name)
    with pytest.raises(AssertionError):
        contract.validate_prompt_inventory(historical, current)


def test_historical_prompt_regression_is_not_bypassed():
    historical, current = prompt_snapshots()
    current[next(iter(historical))] += b"Unapproved policy change."
    with pytest.raises(AssertionError):
        contract.validate_prompt_inventory(historical, current)


@pytest.mark.parametrize("state", STATES)
def test_original_inventory_rejects_new_or_missing_sources_even_when_tracked(monkeypatch, state):
    baseline, scope = contract.PRE_RESUME_BASELINE, "memory"
    original_names = {"memory/__init__.py", "memory/sqlite_store.py"}
    for actual in (original_names | {"memory/debug.py"}, original_names - {"memory/sqlite_store.py"}):
        def fake_git(args, cwd):
            names = original_names if args[1] == "ls-tree" else actual
            return "".join(name + "\0" for name in sorted(names)).encode()
        monkeypatch.setattr(subprocess, "check_output", fake_git)
        with pytest.raises(AssertionError):
            contract.assert_original_inventory(ROOT, baseline, scope)


def test_freeze_allowlist_is_exact_and_contains_no_wildcard_escape():
    assert V13C_FREEZE_PATHS == {
        "README.md", "PRODUCT_SPEC.md", "ARCHITECTURE.md", "IMPLEMENTATION_PLAN.md",
        "tests/freeze_contract.py", "tests/test_freeze_contract.py",
    }
    assert not any("*" in path for path in V13C_FREEZE_PATHS)


def test_existing_secret_and_private_path_scanners_still_reject_candidates():
    from tests.test_public_readiness import private_path, secret_findings
    candidate = "sk-" + "x" * 32
    result = secret_findings("public_fixture.txt", candidate)
    assert result == [("public_fixture.txt", 1, "provider_key")]
    assert candidate not in repr(result)
    for name in (".env.local", "data/private/resume.docx", "data/local/runtime.sqlite3",
                 "artifacts/debug.log", "memory/private.sqlite3"):
        assert private_path(name)
