"""Explicit v1.3B scope: no wildcard exception to earlier freeze contracts."""

V13B_PATHS = {
    "career_runtime/__init__.py", "career_runtime/models.py", "career_runtime/context.py",
    "career_runtime/tools.py", "career_runtime/engine.py", "career_runtime/streaming.py",
    "career_runtime/session.py", "career_runtime/prompts/planner_v1.md", "career_runtime/prompts/response_v1.md",
    "agent_evaluation/__init__.py", "agent_evaluation/run.py", "agent_evaluation/scenarios.py",
    "tests/runtime_contract.py", "tests/agent_doubles.py", "tests/test_agent_runtime.py",
    "tests/test_agent_streaming.py", "tests/test_agent_session.py", "tests/test_agent_ui.py",
    "ui/agent_activity.py", "observability/models.py", "docs/ORANGE_AGENT_RUNTIME.md",
    "career_runtime/diagnostics.py", "career_runtime/planning.py", "career_runtime/prompts/planner_repair_v1.md",
    "tests/test_agent_planning.py", "tests/fixtures/career_plan_shapes.json",
    "career_runtime/finalization.py", "tests/test_long_response.py",
    "career_runtime/continuity.py", "tests/test_conversation_continuity.py",
    "career_runtime/cancellation.py", "tests/test_generation_control.py",
    "career_runtime/response_budget.py", "tests/test_response_budget.py",
}

# Exact C.1 scope and dependency suffix; no general dependency exemption.
V13C1_PATHS = {
    "resume_intake/__init__.py", "resume_intake/models.py", "resume_intake/policy.py",
    "resume_intake/parser.py", "resume_intake/session.py", "ui/resume_upload.py",
    "requirements.txt", "tests/resume_doubles.py", "tests/test_resume_intake.py",
    "tests/test_resume_upload.py",
}
RESUME_REQUIREMENTS = (
    b"# Bounded local PDF/DOCX intake only; no OCR or external document service.\n"
    b"pypdf>=6.19,<7\npython-docx>=1.2,<2\n"
)


def assert_resume_requirements(current, historical):
    assert current == historical + RESUME_REQUIREMENTS

# Exact C.2 addition; original providers, Agents and authority stay frozen.
V13C2_PATHS = {
    "resume_evidence/__init__.py", "resume_evidence/policy.py", "resume_evidence/models.py",
    "resume_evidence/context.py", "resume_evidence/validation.py", "resume_evidence/prompt.py",
    "resume_evidence/service.py", "resume_evidence/session.py", "ui/resume_evidence.py",
    "config/prompts/resume_evidence_v1.md", "tests/resume_evidence_doubles.py",
    "tests/test_resume_evidence.py", "tests/test_resume_evidence_ui.py", "tests/test_resume_canonical.py",
}

# Exact C.3 component/prompt/test additions; durable authority remains frozen.
V13C3_PATHS = {
    "clarification/__init__.py", "clarification/policy.py", "clarification/models.py",
    "clarification/context.py", "clarification/needs.py", "clarification/service.py",
    "clarification/session.py", "ui/clarification.py", "config/prompts/clarification_v1.md",
    "tests/clarification_doubles.py", "tests/test_clarification.py", "tests/test_clarification_ui.py",
    "clarification/diagnostics.py", "tests/test_clarification_contract.py",
}

# Exact approved C.4 additions/extensions, not a blanket domain/store exemption.
V13C4_PATHS = {
    "profile_refinement/__init__.py", "profile_refinement/models.py", "profile_refinement/context.py",
    "profile_refinement/service.py", "profile_refinement/confirmation.py", "profile_refinement/session.py",
    "ui/profile_refinement.py", "config/prompts/profile_refinement_v1.md", "data/models.py", "memory/sqlite_store.py",
    "tests/profile_refinement_doubles.py", "tests/profile_refinement_contract.py",
    "tests/test_profile_refinement.py", "tests/test_profile_refinement_ui.py", "tests/test_public_readiness.py",
}

# Exact C.5A external evaluation additions; no new production exemptions.
V13C5A_PATHS = {
    "career_background_evaluation/__init__.py", "career_background_evaluation/scenarios.py",
    "career_background_evaluation/harness.py", "career_background_evaluation/run.py",
    "tests/test_universal_career_evaluation.py", "tests/test_resume_career_e2e.py",
    "tests/test_resume_career_e2e_ui.py", "docs/UNIVERSAL_CAREER_VALIDATION.md",
}

# Exact freeze documentation and test-only compatibility repair. No *.md or
# directory-wide exception; all earlier production/safety contracts still run.
V13C_FREEZE_PATHS = {
    "README.md", "PRODUCT_SPEC.md", "ARCHITECTURE.md", "IMPLEMENTATION_PLAN.md",
    "tests/freeze_contract.py", "tests/test_freeze_contract.py",
}
