"""D.1 focused observer reusing the SAME public backgrounds and real C pipeline."""

from pathlib import Path
import re
import socket
from tempfile import TemporaryDirectory
from unittest.mock import patch

from career_background_evaluation.harness import CareerHarness, CapturingFake, CheckFailure
from career_background_evaluation.scenarios import SCENARIOS
from career_discovery.context import BACKGROUND
from career_discovery.models import Readiness

# Offline semantic proposal examples only, NEVER used by production discovery.
# These expectations exercise breadth; no profession->direction lookup in runtime.
EXAMPLES = (
    ("Service Operations", "Customer Experience", "Business Operations"),
    ("Operations Improvement", "Business Analysis", "Process Coordination"),
    ("Supply Chain Operations", "Process Improvement", "Business Analysis"),
    ("Finance Transformation", "Business Analysis", "Process Improvement"),
    ("Financial Planning", "Business Analysis", "Finance Transformation"),
    ("Manufacturing Automation", "Quality Systems", "Operations Improvement"),
    ("Growth and CRM", "Customer Experience", "Business Analysis"),
    ("UX Research", "Service Design", "Customer Experience"),
    ("Finance Transformation", "Process Improvement", "Business Analysis"),
    ("Policy Analysis", "Public Service Operations", "Research Communication"),
    ("Operations Improvement", "Supply Chain Operations", "Process Coordination"),
    ("Audit Practice", "Quality Systems", "Finance Transformation"),
    (),
    ("Finance Transformation", "Business Analysis", "Process Improvement"),
    ("Healthcare Operations", "Service Operations", "Quality Systems"),
    ("Healthcare Operations", "Patient Experience", "Quality Systems"),
    ("Operations Improvement", "Business Analysis", "Process Coordination"),
)


def program(titles):
    def propose(payload):
        source = next(s for s in payload["sources"] if s["origin"] == "confirmed_profile" and s["category"] in BACKGROUND)
        current = [s["ref"] for s in payload["sources"] if s["origin"] == "current_explicit"]
        memories = [s["ref"] for s in payload["sources"] if s["origin"] == "confirmed_memory"]
        return {"directions": [dict(title=title, direction_family=title, source_refs=[source["ref"], *current, *memories],
            transferable_capabilities=[dict(interpretation="learning_foundation" if source["category"] == "education" else "domain_familiarity",
                anchors=[dict(source_ref=source["ref"], excerpt=source["text"].split(" · ")[0])], relevance_to_direction="potential_transfer")],
            transition_considerations=[dict(kind="domain_transfer", source_refs=[source["ref"]], topic="相关工作情境", state="unknown")],
            uncertainties=["最终探索意向"], evidence_gaps=["相关职责情境"], goal_relation="EXPLORATORY", confidence="TENTATIVE") for title in titles]}
    return propose


def evaluate_discovery(scenario, root):
    index = SCENARIOS.index(scenario)
    h = CareerHarness(root, scenario)
    try:
        h.prepare(); h.resolve_all(); h.confirm(memory=True)
        profile, memories, history = h.current(), h.memories(), h.history()
        provider = CapturingFake(program(EXAMPLES[index]))
        session = h.workspace.career_discovery
        session.provider_factory = lambda: provider
        result = session.start(explicitly_requested=True, consent=True, current_statement=scenario.current)
        c = h.checks
        c.require("discovery_result", result is not None)
        expected = Readiness.NEEDS_CLARIFICATION if "unknown_goal" in scenario.tags else Readiness.READY
        c.require("discovery_readiness", result.readiness == expected)
        c.require("discovery_projects_optional", not profile.projects)
        c.require("discovery_profile_readonly", h.current() == profile and h.history() == history)
        c.require("discovery_memory_readonly", h.memories() == memories)
        c.require("discovery_no_transcript_write", not h.workspace.chat.messages)
        c.require("discovery_one_call_or_none", provider.attempts == (expected == Readiness.READY))
        c.require("discovery_no_default_technical_requirements", not result.clarification_need or not any(
            term in result.clarification_need.question.casefold() for term in ("python", "github", "项目", "cs", "ai")))
        if expected == Readiness.NEEDS_CLARIFICATION:
            c.require("discovery_one_need_only", result.clarification_need is not None and not result.directions)
        else:
            c.require("discovery_no_forced_intern_or_ai", all(not re.search(r"\b(?:intern|ai|student)\b", d.title, re.I) for d in result.directions))
            c.require("discovery_nonranked_order", [d.title for d in result.directions] == sorted(d.title for d in result.directions))
            c.require("discovery_major_not_goal", all(d.title != e.label for d in result.directions for e in profile.education))
            c.require("discovery_capabilities_derived", all(cap.interpretation_status == "derived_candidate" and cap.derived_from_refs for d in result.directions for cap in d.transferable_capabilities))
            c.require("discovery_transitions_not_gaps", all(t.state == "unknown" for d in result.directions for t in d.transition_considerations))
            c.require("discovery_uncertainty_admitted", all(d.uncertainties and d.evidence_gaps for d in result.directions))
            c.require("discovery_work_first_class", all(any(ref.startswith("work_experience.") for ref in d.supporting_profile_refs) for d in result.directions) if profile.work_experience else True)
            c.require("discovery_ephemeral_selection", session.select(session.token(), result.directions[0].direction_id))
            c.require("discovery_selection_no_authority", h.current() == profile and h.memories() == memories)
            c.require("discovery_no_score", all(not {"score", "ranking", "specific_role_candidates"} & d.model_dump().keys() for d in result.directions))
            c.require("discovery_no_retry_thinking", provider.options[0].max_retries == 0 and not provider.options[0].thinking_enabled)
        h.privacy_checks(profile)
        return len(c.passed)
    finally:
        h.close()


def run():
    attempts = failures = checks = 0
    def blocked(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise AssertionError("Offline discovery evaluation forbids network/config")
    base = Path(__file__).resolve().parents[1] / "artifacts/evaluation"
    base.mkdir(parents=True, exist_ok=True)
    with patch.object(socket.socket, "connect", blocked), patch.object(socket, "create_connection", blocked), patch("providers.models.load_llm_settings", blocked), patch("resume_evidence.session._qwen_provider", blocked):
        for scenario in SCENARIOS:
            with TemporaryDirectory(prefix="discovery-d1-", dir=base) as directory:
                try:
                    count = evaluate_discovery(scenario, directory)
                except Exception as error:
                    failures += 1
                    print(f"FAIL {scenario.scenario_id} check={str(error) if isinstance(error, CheckFailure) else 'evaluation_exception'}")
                else:
                    checks += count
                    print(f"PASS {scenario.scenario_id} checks={count}")
    print(f"D.1 total={len(SCENARIOS)} PASS={len(SCENARIOS)-failures} FAIL={failures} checks_passed={checks} network_attempts={attempts}")
    return failures or attempts


if __name__ == "__main__":
    raise SystemExit(bool(run()))
