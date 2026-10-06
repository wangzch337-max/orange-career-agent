"""Exact user-approved presentation/orchestration scope, not a broad exclusion."""

RESUME_SUMMARY_PATHS = {"ui/resume_evidence.py", "tests/test_resume_evidence_ui.py"}
PROFILE_CONVERSATION_PATHS = {
    "career_runtime/profile_conversation.py", "career_runtime/session.py",
    "ui/profile_conversation.py", "ui/chat_runtime.py", "ui/conversation_shell.py",
    "docs/CHAT_NATIVE_PROFILE_CONVERSATION.md", "tests/profile_conversation_contract.py",
    "tests/test_profile_conversation.py", "tests/test_profile_conversation_ui.py",
    "tests/test_clarification_ui.py", "tests/test_profile_refinement_ui.py",
    "tests/test_resume_career_e2e_ui.py", "tests/test_career_discovery_safety.py",
    "tests/test_ui_rendering.py",
    "tests/test_conversation_shell.py",
}


# Exact release-compatibility edits only; original domain/prompt guards remain.
INTEGRATION_FREEZE_PATHS = {
    "tests/test_onboarding.py", "tests/test_public_readiness.py",
    "tests/test_resume_canonical.py", "tests/test_resume_upload.py",
    "tests/test_freeze_contract.py",
}

# Approved integrated bytes are pinned, not learned from the working tree.
# After checking the pin, older guards still validate EVERY pre-D.1 byte.
INTEGRATION_HASHES = {
    "career_runtime/session.py": "0f2a4e1b3766c2125c05a963a24d11a21c2e2cc8e8b11e6a49f133a6c068ba99",
    "memory/integration.py": "6f82609f4e0c5e3ab537d5734d7dd66c3feb4b4479d980d160dd76036cd48ffb",
    "memory/models.py": "19e451cbaae2e5a6b17a69dd2fc6ea34524984334eddf7bce42b9d34b7efbba3",
    "tests/test_clarification_ui.py": "bbd00a67ace8f6fd07ab4bc544f33d1d798e0662690046294a04a410b187100e",
    "tests/test_conversation_shell.py": "3d26310ff5ac04b85d834bec126203b534949e87ede4f1614adb30d89f3588f1",
    "tests/test_onboarding_tuning.py": "14164b6aa7d07385bdcba2532b425ec820d54f7c6805a31d452fe21e32fbbad4",
    "tests/test_phase7c_memory_integration.py": "8f0742fc979626bb78b0bf95135950937fc77b6b27f29978a45d26e196db3a64",
    "tests/test_profile_refinement_ui.py": "9d91169de736fd34ef02bd4a940e6d6adb184cccfb569512551b3637af2e2b09",
    "tests/test_resume_career_e2e_ui.py": "d4b351d2b52bda1d8483f56b03b465c8199788565538fcebcb12da3df2f14400",
    "tests/test_resume_evidence_ui.py": "a1e394bc43a9d0d974ffe3562981076071df07bd3a0d07a61e926258c25adf8f",
    "tests/test_ui_rendering.py": "7f913c3cc74359326896dc7356ade55dc8b63afd46fdc139afb1d337ed993f25",
    "ui/chat_runtime.py": "acb584a8f997f87f254ecefefa2343346aa226772af982fd702d2468482fb377",
    "ui/conversation_shell.py": "39fab13cb08604c1af0050cd704dcde31fb1457b0457f4711e64907570e636b4",
    "ui/resume_evidence.py": "2d220a6fe488f0e3a9e354dd09699374c9addb2c381e7f220a84e9f790931ee2",
    "tests/test_onboarding.py": "c0ce6d6c45fa0b54c866f23c8625d122203e35eaf7c0a8e91fa9090fd89b6541",
    "tests/test_resume_canonical.py": "e70bd93231aa73dd0dc42d8196f67cd200f88cf9ab85a3a1655af2e54c614fef",
    "tests/test_resume_upload.py": "c69fce88ba175d8bf81cf23bab44bd20081c9dcfb71e8efbe1fe924e5b1b1c2e",
}


def pre_integration_bytes(root, name, current):
    """Compose exact approved integration deltas with existing historical guards."""
    import hashlib
    import subprocess
    from tests.career_reality_contract import pre_d2_bytes
    current = pre_d2_bytes(root, name, current)
    from tests.career_discovery_contract import C_FREEZE
    if name in INTEGRATION_HASHES and hashlib.sha256(current).hexdigest() == INTEGRATION_HASHES[name]:
        return subprocess.check_output(["git", "show", f"{C_FREEZE}:{name}"], cwd=root)
    return current  # Unapproved bytes must face the original guard, never a bypass.
