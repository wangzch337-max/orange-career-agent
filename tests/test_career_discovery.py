"""Focused D.1 readiness, authority, provider and lifecycle regression matrix."""

from copy import deepcopy
from dataclasses import asdict, replace
import json
from threading import Event, Thread
from uuid import uuid4

import pytest

from career_background_evaluation.harness import CapturingFake
from career_discovery.context import (CareerDiscoveryContextBuilder, DiscoveryInputs, MAX_JSON_CHARS,
    MAX_PROFILE_FACTS, bind, readiness, workspace_inputs)
from career_discovery.models import (CareerDiscoveryResult, DiscoveryError, DiscoveryProposal, Readiness, Status)
from career_discovery.service import validate
from providers.fake import FakeLLMProvider
from tests.career_discovery_doubles import prepared, proposal_from_payload


@pytest.fixture
def h(tmp_path):
    value = prepared(tmp_path)
    yield value
    value.close()


def context(h, statement="我想从已有经验探索相邻方向。", request_id="test_request"):
    inputs = workspace_inputs(h.workspace, current_statement=statement, include_memory=True)
    return CareerDiscoveryContextBuilder().build(inputs, request_id)


def start(h, program=proposal_from_payload, **kwargs):
    provider = CapturingFake(program)
    h.workspace.career_discovery.provider_factory = lambda: provider
    result = h.workspace.career_discovery.start(explicitly_requested=True, consent=True,
        current_statement=kwargs.pop("current_statement", "我想从已有经验探索相邻方向。"), **kwargs)
    return result, provider


def test_ready_work_heavy_no_projects_one_call_and_no_writes(h):
    old, history, memories = h.current(), h.history(), h.memories()
    result, provider = start(h, request_id="one")
    assert result.readiness == Readiness.READY and len(result.directions) == 3
    assert not old.projects and h.current() == old and h.history() == history and h.memories() == memories
    session = h.workspace.career_discovery
    assert session.start(explicitly_requested=True, consent=True, request_id="one") == result
    assert provider.attempts == provider.call_count == 1
    assert all(o.max_retries == 0 and not o.thinking_enabled and o.model == "qwen3.8-flash" for o in provider.options)
    assert all(c.interpretation_status == "derived_candidate" for d in result.directions for c in d.transferable_capabilities)
    assert all(c.state == "unknown" for d in result.directions for c in d.transition_considerations)
    assert all(d.status == "candidate" for d in result.directions)


@pytest.mark.parametrize("statement", ["Python generator 是什么？", "", "普通知识问题"])
def test_not_requested_does_not_load_any_profile_memory_provider(h, statement):
    session = h.workspace.career_discovery
    session.input_factory = lambda **kwargs: pytest.fail("discovery input loaded on QA")
    session.provider_factory = lambda: pytest.fail("provider constructed on QA")
    result = session.start(current_statement=statement)
    assert result.readiness == Readiness.NOT_REQUESTED and not result.directions


def test_no_consent_no_loading(h):
    session = h.workspace.career_discovery
    session.input_factory = lambda **kwargs: pytest.fail("loaded before consent")
    assert session.start(explicitly_requested=True) is None
    assert session.status == Status.CONSENT_REQUIRED


def test_unknown_current_intent_not_suppressed_by_old_goal(h):
    result, provider = start(h, current_statement="我还没有明确的职业方向，不知道方向。")
    assert result.readiness == Readiness.NEEDS_CLARIFICATION and not result.directions
    assert result.clarification_need.need_id == "exploration_scope" and provider.attempts == 0


@pytest.mark.parametrize("statement", ["我想探索数据或业务分析方向，但不确定是否转向。", "我想看看产品方向。", "我希望继续审计。", "Explore adjacent career directions", "探索数据或业务分析，尚未确定"])
def test_bounded_current_exploration_can_be_ready(h, statement):
    assert readiness(context(h, statement))[0] == Readiness.READY


def test_missing_confirmed_profile_one_need_and_no_call(h):
    session = h.workspace.career_discovery
    original = session.input_factory
    session.input_factory = lambda **kwargs: replace(original(**kwargs), profile=None)
    result, provider = start(h)
    assert result.readiness == Readiness.NEEDS_CLARIFICATION and result.clarification_need.need_id == "background"
    assert not result.directions and provider.attempts == 0


@pytest.mark.parametrize("count", range(6))
def test_zero_to_five_allowed(h, count):
    ctx = context(h)
    raw = proposal_from_payload(ctx.provider_payload(), titles=tuple(f"Exploration Family {i}" for i in range(count)))
    assert len(validate(DiscoveryProposal.model_validate(raw), ctx)) == count


@pytest.mark.parametrize("extra", ["score", "ranking", "success_probability", "specific_role_candidates", "job_ids", "company", "salary", "job_url", "direction_id", "summary", "why_explore"])
def test_strict_extra_direction_keys_rejected(h, extra):
    def bad(payload):
        raw = proposal_from_payload(payload)
        raw["directions"][0][extra] = "unsupported"
        return raw
    result, provider = start(h, bad)
    assert result is None and h.workspace.career_discovery.status == Status.INVALID_OUTPUT
    assert provider.attempts == 1 and h.workspace.career_discovery.selected_direction_id is None


@pytest.mark.parametrize("field,value", [("confidence", 0.8), ("confidence", "HIGH"), ("goal_relation", "BEST"), ("goal_relation", 90)])
def test_enums_are_coarse_and_closed(h, field, value):
    def bad(payload):
        raw = proposal_from_payload(payload)
        raw["directions"][0][field] = value
        return raw
    assert start(h, bad)[0] is None


def test_six_directions_rejected(h):
    assert start(h, lambda p: proposal_from_payload(p, titles=tuple(f"Family {i}" for i in range(6))))[0] is None


def test_stable_ids_and_order_not_provider_order(h):
    ctx = context(h)
    raw = proposal_from_payload(ctx.provider_payload())
    first = validate(DiscoveryProposal.model_validate(raw), ctx)
    raw["directions"].reverse()
    assert validate(DiscoveryProposal.model_validate(raw), ctx) == first
    assert [d.title for d in first] == sorted(d.title for d in first)
    assert all(d.direction_id.startswith("direction_") for d in first)
    other = context(h, request_id="other")
    second = validate(DiscoveryProposal.model_validate(proposal_from_payload(other.provider_payload())), other)
    assert [d.direction_id for d in second] == [d.direction_id for d in first]


def test_exact_duplicate_dedup_conflicting_duplicate_rejected(h):
    ctx = context(h)
    raw = proposal_from_payload(ctx.provider_payload())
    raw["directions"].append(deepcopy(raw["directions"][0]))
    assert len(validate(DiscoveryProposal.model_validate(raw), ctx)) == 3
    raw["directions"][-1]["confidence"] = "UNCERTAIN"
    with pytest.raises(DiscoveryError):
        validate(DiscoveryProposal.model_validate(raw), ctx)


@pytest.mark.parametrize("target", ["direction", "capability", "transition"])
def test_invented_refs_rejected(h, target):
    def bad(payload):
        raw = proposal_from_payload(payload)
        d = raw["directions"][0]
        unknown = "src_aaaaaaaaaaaaaaaa_999"
        if target == "direction": d["source_refs"].append(unknown)
        elif target == "capability": d["transferable_capabilities"][0]["anchors"][0]["source_ref"] = unknown
        else: d["transition_considerations"][0]["source_refs"] = [unknown]
        return raw
    assert start(h, bad)[0] is None
    assert h.workspace.career_discovery.status == Status.INVALID_REFERENCE


def test_request_conversation_and_owner_scoped_ref(h):
    inputs = workspace_inputs(h.workspace, current_statement="探索相邻方向")
    builder = CareerDiscoveryContextBuilder()
    first = builder.build(inputs, "same")
    for changed in (replace(inputs, owner_scope_id=str(uuid4())), replace(inputs, conversation_id="other")):
        other = builder.build(changed, "same")
        assert not {s.ref for s in first.sources} & {s.ref for s in other.sources}
        with pytest.raises(DiscoveryError):
            validate(DiscoveryProposal.model_validate(proposal_from_payload(first.provider_payload())), other)


@pytest.mark.parametrize("field,value", [("title", "Product Manager"), ("title", "AI Application Engineer"), ("title", "最适合你的方向"), ("title", "成功率 90%"), ("title", "Business Analysis ★★★★★"), ("title", "Business Analysis 8/10"), ("title", "Recommended Product"), ("evidence_gaps", ["缺乏高级工程能力"]), ("evidence_gaps", ["缺少 GitHub 项目"]), ("evidence_gaps", ["SQL 能力不足"]), ("evidence_gaps", ["missing SQL skill"]), ("uncertainties", ["guaranteed employment"]), ("direction_family", "Advanced Data Engineering"), ("direction_family", "Led Enterprise Transformation")])
def test_roles_ranking_inflation_and_missing_projects_rejected(h, field, value):
    def bad(payload):
        raw = proposal_from_payload(payload)
        raw["directions"][0][field] = value
        return raw
    assert start(h, bad)[0] is None
    assert h.workspace.career_discovery.status == Status.INVALID_OUTPUT


@pytest.mark.parametrize("change", ["invented_excerpt", "preference_as_capability", "advanced_skill", "ownership", "authoritative_status"])
def test_capability_cannot_inflate_or_use_preference_as_proof(h, change):
    def bad(payload):
        raw = proposal_from_payload(payload)
        c = raw["directions"][0]["transferable_capabilities"][0]
        if change == "invented_excerpt": c["anchors"][0]["excerpt"] = "Led full commercial transformation"
        elif change == "preference_as_capability":
            s = next(s for s in payload["sources"] if s["origin"] == "current_explicit")
            c["anchors"] = [dict(source_ref=s["ref"], excerpt=s["text"])]
        elif change == "advanced_skill": c["interpretation"] = "advanced_data_engineering"
        elif change == "ownership": c["interpretation"] = "transformation_ownership"
        else: c["interpretation_status"] = "confirmed_fact"
        return raw
    assert start(h, bad)[0] is None


@pytest.mark.parametrize("change", ["barrier", "confirmed_gap", "invented_anchor", "unsupported_source", "numeric_difficulty"])
def test_transition_safety(h, change):
    def bad(payload):
        raw = proposal_from_payload(payload)
        c = raw["directions"][0]["transition_considerations"][0]
        if change == "barrier": c["kind"] = "qualification_barrier"
        elif change == "confirmed_gap": c["state"] = "confirmed_gap"
        elif change == "invented_anchor":
            c["anchor"] = dict(source_ref=c["source_refs"][0], excerpt="Invented licence requirement")
        elif change == "unsupported_source": c["state"] = "source_supported"
        else: c["difficulty"] = 0.9
        return raw
    assert start(h, bad)[0] is None


def test_current_exploration_plus_history_remains_visible_no_writes(h):
    old, memories = h.current(), h.memories()
    result, provider = start(h, current_statement="我想探索产品方向，还未确定是否离开审计。")
    assert result and provider.attempts == 1
    assert all(d.current_signal_refs and d.supporting_memory_refs for d in result.directions)
    assert all("本轮探索意向优先" in d.why_explore and "历史目标" in d.why_explore for d in result.directions)
    assert h.current() == old and h.memories() == memories


def test_provider_cannot_ignore_current_statement(h):
    def bad(payload):
        raw = proposal_from_payload(payload)
        current = {s["ref"] for s in payload["sources"] if s["origin"] == "current_explicit"}
        raw["directions"][0]["source_refs"] = [r for r in raw["directions"][0]["source_refs"] if r not in current]
        return raw
    assert start(h, bad)[0] is None


def test_selection_ephemeral_no_profile_memory_or_transcript_write(h):
    old, memories, transcript = h.current(), h.memories(), list(h.workspace.chat.messages)
    result, provider = start(h)
    session = h.workspace.career_discovery
    assert session.select(session.token(), result.directions[0].direction_id)
    assert session.selected_direction_id == result.directions[0].direction_id
    assert h.current() == old and h.memories() == memories and h.workspace.chat.messages == transcript
    assert provider.attempts == 1


@pytest.mark.parametrize("change", ["profile", "new_chat", "delete", "statement", "owner_token", "wrong_id", "close"])
def test_stale_selection_rejected_and_no_resurrection(h, change):
    result, provider = start(h)
    w, session = h.workspace, h.workspace.career_discovery
    token = session.token()
    if change == "profile":
        revised = h.current().create_revision(education_summary="changed").confirm()
        w.memory_service.save_confirmed_profile(w.subject_id, revised)
    elif change == "new_chat": w.create_new_thread()
    elif change == "delete": w.delete_thread(w.thread.thread_id)
    elif change == "statement": w.submit("普通知识问题")
    elif change == "owner_token": token = token.model_copy(update={"owner_scope_id": str(uuid4())})
    elif change == "close": w.close()
    target = "direction_unknown" if change == "wrong_id" else result.directions[0].direction_id
    assert not session.select(token, target) and session.selected_direction_id is None
    assert provider.attempts == 1


def test_late_provider_result_after_delete_cannot_publish(h):
    entered, release = Event(), Event()
    def blocking(payload):
        entered.set()
        assert release.wait(5)
        return proposal_from_payload(payload)
    session = h.workspace.career_discovery
    provider = CapturingFake(blocking)
    session.provider_factory = lambda: provider
    thread = Thread(target=lambda: session.start(explicitly_requested=True, consent=True, current_statement="探索相邻方向"))
    thread.start()
    assert entered.wait(5)
    h.workspace.delete_thread(h.workspace.thread.thread_id)
    release.set(); thread.join(5)
    assert not thread.is_alive() and session.result is None and session.selected_direction_id is None
    assert provider.attempts == 1


def test_provider_failure_sanitized_no_partial_state_no_retry(h):
    class Broken(FakeLLMProvider):
        def generate_structured(self, *args, **kwargs):
            self.call_count += 1
            raise RuntimeError("PRIVATE COMPLETION credential-bearing response")
    provider = Broken(None)
    session = h.workspace.career_discovery
    session.provider_factory = lambda: provider
    assert session.start(explicitly_requested=True, consent=True, current_statement="探索相邻方向", request_id="failed") is None
    assert session.status == Status.PROVIDER_FAILED and session.result is None
    session.start(explicitly_requested=True, consent=True, request_id="failed")
    assert provider.call_count == 1 and "PRIVATE" not in json.dumps([asdict(e) for e in session.events])


def test_structural_events_and_provider_minimization(h):
    statement = "我想从已有经验探索相邻方向。"
    result, provider = start(h, current_statement=statement)
    session = h.workspace.career_discovery
    session.select(session.token(), result.directions[0].direction_id)
    events = json.dumps([asdict(e) for e in session.events], ensure_ascii=False)
    assert statement not in events and h.current().work_experience[0].label not in events
    assert result.directions[0].title not in events and "source_refs" not in events and "completion" not in events
    assert {e.event for e in session.events} >= {"career_discovery_requested", "career_discovery_context_built",
        "career_discovery_ready", "career_discovery_directions_created", "career_discovery_direction_selected"}
    serialized = json.dumps(provider.payloads, ensure_ascii=False)
    assert len(json.dumps(provider.payloads[0], ensure_ascii=False, separators=(",", ":"))) <= MAX_JSON_CHARS
    assert not any(value in serialized for value in (h.raw_text, h.workspace.owner_scope_id, h.workspace.subject_id, str(h.root)))
    assert "organization" not in serialized and "evidence_ids" not in serialized


def test_whole_material_fact_not_mid_value_truncated(h):
    p = h.current().model_dump()
    p["skills"] = [dict(skill_id=f"s{i}", label="X" * 1300 if i == 0 else "Structured record " + str(i),
        confidence=1.0, evidence_ids=[], source_type="explicit_user_input", confirmed_by_user=True) for i in range(60)]
    from data.models import UserProfile
    profile = UserProfile.model_validate(p)
    inputs = DiscoveryInputs("owner", "conversation", "subject", profile=profile, current_statement="探索相邻方向")
    ctx = CareerDiscoveryContextBuilder().build(inputs, "bounded")
    assert ctx.partial and not any(s.text.startswith("X") for s in ctx.sources)
    assert sum(s.origin == "confirmed_profile" for s in ctx.sources) <= MAX_PROFILE_FACTS
    assert len(json.dumps(ctx.provider_payload(), ensure_ascii=False, separators=(",", ":"))) <= MAX_JSON_CHARS
    assert all(s.text.endswith(str(int(s.text.rsplit(" ", 1)[1]))) for s in ctx.sources if s.category == "skills")


def test_assistant_recent_context_excluded(h):
    inp = workspace_inputs(h.workspace, current_statement="探索相邻方向")
    ctx = CareerDiscoveryContextBuilder().build(replace(inp, recent=(("assistant", "Invented professional roadmap ownership"), ("user", "当前只考虑本地工作"))), "recent")
    assert all("Invented" not in s.text for s in ctx.sources)
    assert any(s.origin == "recent_user_context" for s in ctx.sources)


def test_top_level_mutually_exclusive_states():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        CareerDiscoveryResult(request_id="r", readiness="NEEDS_CLARIFICATION", status="NEEDS_CLARIFICATION")
    with pytest.raises(ValidationError):
        DiscoveryProposal.model_validate(dict(directions=[], overall_score=88))
