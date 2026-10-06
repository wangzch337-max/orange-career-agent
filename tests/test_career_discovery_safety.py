"""Privacy/frozen-boundary and source-supported constraint review gates."""

from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from career_background_evaluation.harness import CapturingFake
from career_discovery.context import CareerDiscoveryContextBuilder, workspace_inputs
from career_discovery.models import DiscoveryError, DiscoveryProposal, Status
from career_discovery.service import validate
from data.models import UserProfile
from tests.career_discovery_contract import C_FREEZE, D1_PATHS, assert_d1_memory_delta, assert_d1_prompt_scope
from tests.career_discovery_doubles import prepared, proposal_from_payload
from tests.freeze_contract import PRE_RESUME_BASELINE, changed_paths, historical_paths

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def h(tmp_path):
    value = prepared(tmp_path)
    yield value
    value.close()


def projected_profile(h, extra):
    raw = h.current().model_dump()
    for category, text in extra.items():
        raw[category] = [dict(entry_id=category + "_public", label=text, confidence=1.0, evidence_ids=[],
            source_type="explicit_user_input", confirmed_by_user=True)]
    return UserProfile.model_validate(raw)


def test_location_workstyle_and_actual_constraints_survive_provider_omission(h):
    profile = projected_profile(h, {"location_preferences": "只考虑本地工作", "work_style_preferences": "偏好稳定工作时间", "constraints": "目前不考虑搬迁"})
    inputs = replace(workspace_inputs(h.workspace, current_statement="探索相邻方向"), profile=profile)
    ctx = CareerDiscoveryContextBuilder().build(inputs, "constraint")
    directions = validate(DiscoveryProposal.model_validate(proposal_from_payload(ctx.provider_payload())), ctx)
    for d in directions:
        for text in ("只考虑本地工作", "偏好稳定工作时间", "目前不考虑搬迁"):
            assert any(text in c.description for c in d.transition_considerations)
        assert all(any(ref.startswith(category + ".") for ref in d.supporting_profile_refs) for category in
                   ("location_preferences", "work_style_preferences", "constraints"))


def test_qualification_barrier_only_with_actual_source_condition(h):
    profile = projected_profile(h, {"professional_qualifications": "相关临床工作必须持有当前有效的专业执照"})
    inputs = replace(workspace_inputs(h.workspace, current_statement="探索相邻方向"), profile=profile)
    ctx = CareerDiscoveryContextBuilder().build(inputs, "qualification")
    source = next(s for s in ctx.sources if s.category == "professional_qualifications")
    raw = proposal_from_payload(ctx.provider_payload())
    raw["directions"][0]["source_refs"].append(source.ref)
    raw["directions"][0]["transition_considerations"] = [dict(kind="qualification_barrier", source_refs=[source.ref],
        topic="专业执照条件", state="source_supported", anchor=dict(source_ref=source.ref, excerpt=source.text))]
    directions = validate(DiscoveryProposal.model_validate(raw), ctx)
    d = next(d for d in directions if d.title == raw["directions"][0]["title"])
    assert d.transition_considerations[0].state == "source_supported"
    assert source.text in d.transition_considerations[0].description


def test_excel_does_not_become_advanced_data_engineering_or_ownership(h):
    profile = projected_profile(h, {"tools": "Used Excel to prepare financial records"})
    inputs = replace(workspace_inputs(h.workspace, current_statement="探索相邻方向"), profile=profile)
    ctx = CareerDiscoveryContextBuilder().build(inputs, "excel")
    raw = proposal_from_payload(ctx.provider_payload())
    raw["directions"][0]["direction_family"] = "Advanced Data Engineering"
    with pytest.raises(DiscoveryError):
        validate(DiscoveryProposal.model_validate(raw), ctx)
    raw["directions"][0]["direction_family"] = "Led Enterprise Transformation"
    with pytest.raises(DiscoveryError):
        validate(DiscoveryProposal.model_validate(raw), ctx)


def test_source_minimization_no_raw_contacts_or_history_dump(h):
    inputs = workspace_inputs(h.workspace, current_statement="探索相邻方向。 Email: synthetic@example.invalid")
    inputs = replace(inputs, recent=(("user", "Phone: +1 202 555 0183\nHome address: Synthetic Street\n探索相邻方向"),))
    ctx = CareerDiscoveryContextBuilder().build(inputs, "privacy")
    payload = json.dumps(ctx.provider_payload(), ensure_ascii=False)
    assert "synthetic@example.invalid" not in payload and "+1 202 555 0183" not in payload and "Synthetic Street" not in payload
    assert ctx.partial and h.raw_text not in payload and "organization" not in payload


def test_overlong_current_intent_does_not_fall_back_to_old_goal(h):
    inputs = workspace_inputs(h.workspace, current_statement="X" * 1201)
    with pytest.raises(DiscoveryError):
        CareerDiscoveryContextBuilder().build(inputs, "long")


@pytest.mark.parametrize("goal_type", ["project_goal", "learning_goal"])
def test_noncareer_goal_not_treated_as_career_intent(h, goal_type):
    from career_discovery.context import readiness
    from career_discovery.models import Readiness
    raw = h.current().model_dump()
    raw["goals"][0].update(goal_type=goal_type, label="Build a software portfolio project")
    inputs = replace(workspace_inputs(h.workspace), profile=UserProfile.model_validate(raw))
    ctx = CareerDiscoveryContextBuilder().build(inputs, "goal-type")
    assert readiness(ctx)[0] == Readiness.NEEDS_CLARIFICATION
    assert next(s for s in ctx.sources if s.category == "goals").goal_type == goal_type


@pytest.mark.parametrize("statement", ["我希望换工作", "我想转行", "探索职业方向", "我想探索职业方向", "I want to explore career directions"])
def test_materially_unresolved_transition_needs_one_question(h, statement):
    from career_discovery.context import readiness
    from career_discovery.models import Readiness
    ctx = CareerDiscoveryContextBuilder().build(workspace_inputs(h.workspace, current_statement=statement), "unclear")
    assert readiness(ctx)[0] == Readiness.NEEDS_CLARIFICATION


def test_old_ui_scope_rejected_before_provider(h):
    w, session = h.workspace, h.workspace.career_discovery
    old_thread = w.thread.thread_id
    w.create_new_thread()
    provider = CapturingFake(proposal_from_payload)
    session.provider_factory = lambda: provider
    assert session.start(explicitly_requested=True, consent=True, current_statement="探索相邻方向",
        expected_conversation_id=old_thread, expected_owner_scope_id=w.owner_scope_id) is None
    assert session.status == Status.STALE and provider.attempts == 0


def test_recent_context_change_invalidates_selection(h):
    from ui.conversation_shell import ChatMessage
    session = h.workspace.career_discovery
    session.provider_factory = lambda: CapturingFake(proposal_from_payload)
    result = session.start(explicitly_requested=True, consent=True, current_statement="探索相邻方向")
    token = session.token()
    h.workspace.chat.messages.append(ChatMessage("user", "新的本轮工作限制"))
    assert not session.select(token, result.directions[0].direction_id)


def test_provider_can_not_publish_after_profile_changed_mid_call(h):
    def changing(payload):
        h.workspace.memory_service.save_confirmed_profile(h.workspace.subject_id,
            h.current().create_revision(education_summary="new confirmed version").confirm())
        return proposal_from_payload(payload)
    session = h.workspace.career_discovery
    provider = CapturingFake(changing)
    session.provider_factory = lambda: provider
    assert session.start(explicitly_requested=True, consent=True, current_statement="探索相邻方向") is None
    assert session.status == Status.STALE and session.result is None and provider.attempts == 1


def test_idempotency_key_cannot_leak_prose_into_events(h):
    session = h.workspace.career_discovery
    session.provider_factory = lambda: CapturingFake(proposal_from_payload)
    result = session.start(explicitly_requested=True, consent=True, current_statement="探索相邻方向", request_id="PUBLIC SYNTHETIC prose not an opaque id")
    assert result and result.request_id.startswith("discovery_")
    assert "PUBLIC SYNTHETIC prose" not in json.dumps([asdict(e) for e in session.events])


def test_conflicting_duplicate_capabilities_rejected_not_repaired(h):
    ctx = CareerDiscoveryContextBuilder().build(workspace_inputs(h.workspace, current_statement="探索相邻方向"), "dup")
    raw = proposal_from_payload(ctx.provider_payload())
    cap = deepcopy(raw["directions"][0]["transferable_capabilities"][0])
    cap["uncertainty"] = "context_dependent"
    raw["directions"][0]["transferable_capabilities"].append(cap)
    with pytest.raises(DiscoveryError):
        validate(DiscoveryProposal.model_validate(raw), ctx)


def test_anchor_cannot_remove_negation_or_support_qualifier(h):
    raw_profile = h.current().model_dump()
    raw_profile["work_experience"][0]["label"] = "Supported process improvement; did not lead enterprise transformation"
    inputs = replace(workspace_inputs(h.workspace, current_statement="探索相邻方向"), profile=UserProfile.model_validate(raw_profile))
    ctx = CareerDiscoveryContextBuilder().build(inputs, "negative-context")
    raw = proposal_from_payload(ctx.provider_payload())
    cap = raw["directions"][0]["transferable_capabilities"][0]
    assert validate(DiscoveryProposal.model_validate(raw), ctx)
    cap["anchors"][0]["excerpt"] = "lead enterprise transformation"
    with pytest.raises(DiscoveryError):
        validate(DiscoveryProposal.model_validate(raw), ctx)
    cap["anchors"][0]["excerpt"] = raw_profile["work_experience"][0]["label"]
    raw["directions"][0]["title"] = "Lead Enterprise Transformation"
    with pytest.raises(DiscoveryError):
        validate(DiscoveryProposal.model_validate(raw), ctx)


def test_frozen_c_authority_and_exact_d1_scope():
    from tests.profile_conversation_contract import RESUME_SUMMARY_PATHS, PROFILE_CONVERSATION_PATHS, INTEGRATION_FREEZE_PATHS
    from tests.career_reality_contract import D2_PATHS
    # Later explicit UI approvals add exact paths only. The domain/prompt/Memory
    # byte guards below are unchanged and still reject any unauthorized change.
    assert changed_paths(ROOT, C_FREEZE, ".") <= D1_PATHS | RESUME_SUMMARY_PATHS | PROFILE_CONVERSATION_PATHS | INTEGRATION_FREEZE_PATHS | D2_PATHS
    for scope in ("resume_intake", "resume_evidence", "clarification", "profile_refinement", "agents", "workflows", "providers", "data/models.py", "memory/sqlite_store.py", "requirements.txt"):
        assert not changed_paths(ROOT, C_FREEZE, scope), scope
    assert_d1_memory_delta(ROOT)
    assert_d1_prompt_scope(ROOT, PRE_RESUME_BASELINE)
    for name in historical_paths(ROOT, C_FREEZE, "config/prompts"):
        assert (ROOT / name).read_bytes() == subprocess.check_output(["git", "show", f"{C_FREEZE}:{name}"], cwd=ROOT)


def test_no_new_provider_stack_network_imports_mutators_or_environment_reads():
    import ast
    paths = [*sorted((ROOT / "career_discovery").glob("*.py")), ROOT / "ui/career_discovery.py"]
    forbidden = {"save_confirmed_profile", "create_confirmed", "create_candidate", "supersede", "load_llm_settings", "load_dotenv", "QwenProvider", "socket", "httpx", "requests", "urlopen"}
    for path in paths:
        tree = ast.parse(path.read_text())
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert not names & forbidden, path.name
        assert ".env.local" not in path.read_text()


@pytest.mark.parametrize("education", ["Accounting Degree", "Computer Science Degree"])
def test_major_not_direction_and_technical_user_not_forced_into_ai(tmp_path, education):
    from dataclasses import replace
    from career_background_evaluation.scenarios import SCENARIOS
    scenario = replace(SCENARIOS[0], facts=(replace(SCENARIOS[0].facts[0], label=education),))
    h = prepared(tmp_path, scenario)
    try:
        provider = CapturingFake(lambda p: proposal_from_payload(p, titles=("Product", "Service Operations", "UX Research")))
        session = h.workspace.career_discovery
        session.provider_factory = lambda: provider
        result = session.start(explicitly_requested=True, consent=True, current_statement="我想探索产品方向")
        assert result and len(result.directions) == 3 and provider.attempts == 1
        assert not h.current().projects and not h.current().work_experience
        assert all(d.title not in {education, "Accounting", "AI"} for d in result.directions)
        assert all(any(r.startswith("education.") for r in d.supporting_profile_refs) for d in result.directions)
    finally:
        h.close()
