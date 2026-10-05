"""Exact D.1 additions; preserve every earlier prompt and Memory consumer byte."""

import hashlib
from pathlib import Path
import subprocess

from tests.freeze_contract import historical_paths, repository_paths, validate_prompt_inventory

C_FREEZE = "c19170cc04dfd1b49b164774f47f9a1fea9ac132"
D_PROMPT = "config/prompts/career_direction_discovery_v1.md"
D_PROMPT_HASH = "a5a58b404e0a9577d4f57862db6f40e383ae909dc0e096e146df516c4e43116f"
D1_PATHS = {
    "career_discovery/__init__.py", "career_discovery/models.py", "career_discovery/context.py",
    "career_discovery/service.py", "career_discovery/session.py", "ui/career_discovery.py", D_PROMPT,
    "memory/models.py", "memory/integration.py", "career_background_evaluation/discovery.py",
    "tests/career_discovery_doubles.py", "tests/career_discovery_contract.py", "tests/test_career_discovery.py",
    "tests/test_career_discovery_memory.py", "tests/test_career_discovery_ui.py", "tests/test_career_discovery_backgrounds.py",
    "tests/test_career_discovery_safety.py", "tests/test_phase7c_memory_integration.py",
    "tests/test_onboarding_tuning.py", "tests/test_ui_rendering.py", "docs/CAREER_DIRECTION_DISCOVERY.md",
    "README.md", "ui/chat_runtime.py", "ui/conversation_shell.py", "career_runtime/session.py",
}


def assert_d1_prompt_scope(root, baseline):
    historical = {name: subprocess.check_output(["git", "show", f"{baseline}:{name}"], cwd=root)
                  for name in historical_paths(root, baseline, "config/prompts")}
    current = {name: (Path(root) / name).read_bytes() for name in repository_paths(root, "config/prompts")}
    assert hashlib.sha256(current.pop(D_PROMPT)).hexdigest() == D_PROMPT_HASH
    validate_prompt_inventory(historical, current)  # Original strict THREE-C-prompt contract unchanged.


def assert_d1_memory_delta(root):
    additions = {
        "memory/models.py": [
            '    CAREER_DIRECTION_DISCOVERY = "career_direction_discovery"\n',
            '    CAREER_DIRECTION_DISCOVERY_SERVICE = "career_direction_discovery_service"\n'],
        "memory/integration.py": [
            '\n# D.1 explicit read-only consumer. Existing consumers and write paths unchanged.\n'
            'CAREER_DIRECTION_DISCOVERY_POLICY: Final = MemoryContextPolicy(\n'
            '    use_case=MemoryUseCase.CAREER_DIRECTION_DISCOVERY,\n'
            '    allowed_memory_types=[MemoryType.CAREER_PREFERENCE, MemoryType.GOAL, MemoryType.USER_FEEDBACK],\n'
            '    retrieval_mode=MemoryRetrievalMode.HYBRID,\n'
            '    top_k=5,\n    max_records=3,\n    max_characters=1800,\n'
            '    session_input_contributes=True,\n'
            '    consumer=MemoryConsumer.CAREER_DIRECTION_DISCOVERY_SERVICE,\n)\n',
            '        MemoryUseCase.CAREER_DIRECTION_DISCOVERY: CAREER_DIRECTION_DISCOVERY_POLICY,\n'],
    }
    for name, blocks in additions.items():
        current = (Path(root) / name).read_text()
        for block in blocks:
            assert current.count(block) == 1
            current = current.replace(block, "", 1)
        original = subprocess.check_output(["git", "show", f"{C_FREEZE}:{name}"], cwd=root).decode()
        assert current == original, name
