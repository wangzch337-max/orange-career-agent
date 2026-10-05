"""Content/history guards, independent of index placement or moving HEAD."""

import hashlib
from pathlib import Path
import subprocess


# Last published pre-Resume checkpoint: includes the approved onboarding/chat
# bridge, but the original authority files/dependencies and no C.1-C.4 prompts.
# Verified against the paired original hashes in profile_refinement_contract.
PRE_RESUME_BASELINE = "74a19ec7953ebceb69fa46dad1cb84c455599616"

RESUME_PROMPT_HASHES = {
    "config/prompts/resume_evidence_v1.md": "dd153f3a936b6e20660350362760db608e892d2d3ea272f4518ea97c50527e6b",
    "config/prompts/clarification_v1.md": "a71906b38015ab0dbc2407d92e12915efe4bfe25d305d4a72ea13fbb899140f7",
    "config/prompts/profile_refinement_v1.md": "bf0ea7027e5c0be221e88a55a9d591b680328854db68abd60845c736a5bb41f9",
}


def _names(root, *args):
    output = subprocess.check_output(["git", *args], cwd=root)
    return {name for name in output.decode().split("\0") if name}


def repository_paths(root, scope):
    """Same public inventory for untracked, staged or committed source."""
    return _names(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", scope)


def historical_paths(root, baseline, scope):
    return _names(root, "ls-tree", "-r", "--name-only", "-z", baseline, "--", scope)


def changed_paths(root, baseline, scope):
    """Include committed/staged/unstaged differences AND untracked additions."""
    return (_names(root, "diff", "--name-only", "--no-renames", "-z", baseline, "--", scope)
            | _names(root, "ls-files", "-z", "--others", "--exclude-standard", "--", scope))


def assert_original_inventory(root, baseline, scope):
    """No new/renamed/deleted path, even when it is now tracked."""
    actual = repository_paths(root, scope)
    assert actual == historical_paths(root, baseline, scope), scope
    assert all((Path(root) / name).is_file() for name in actual), scope


def validate_prompt_inventory(historical, current):
    """Freeze ALL historical bytes and exactly THREE approved new prompts."""
    assert not set(historical) & RESUME_PROMPT_HASHES.keys()
    assert set(current) == set(historical) | RESUME_PROMPT_HASHES.keys()
    for name, content in historical.items():
        assert current[name] == content, name
    for name, digest in RESUME_PROMPT_HASHES.items():
        assert hashlib.sha256(current[name]).hexdigest() == digest, name


def assert_resume_prompt_scope(root, baseline):
    historical = {name: subprocess.check_output(["git", "show", f"{baseline}:{name}"], cwd=root)
                  for name in historical_paths(root, baseline, "config/prompts")}
    current = {name: (Path(root) / name).read_bytes()
               for name in repository_paths(root, "config/prompts")}
    validate_prompt_inventory(historical, current)
