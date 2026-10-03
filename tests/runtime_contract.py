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
}
