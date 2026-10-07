"""Synthetic-only D.5 authority, relation, ownership, isolation and bounded UX."""

import json
from threading import Event as ThreadEvent, Thread
import pytest
from data.models import UserProfile, EvidenceItem, ProfileSectionEntry, EvidenceSourceType, InferenceType, ProfileFieldProvenance, ProfileSourceReference, utc_now
from providers.fake import FakeLLMProvider
from providers.errors import LLMStructuredOutputError
from evidence_match.models import Context, Relation, Result, Candidate, Extraction
from evidence_match.projection import project_user, project_work
from evidence_match.service import analyze, proposed, assemble, response_model
from evidence_match.session import intent, NOTICE, LABELS
from specific_role.sources import SpecificRoleRegistry
from career_background_evaluation.match import synthetic_profile
from tests.test_role_landscape import h, offline
from tests.test_specific_role import expanded

SOURCES = SpecificRoleRegistry().inventory().records


def opened(h):
    source = SOURCES[0]
    w = h.workspace
    w.memory_service.save_confirmed_profile(w.subject_id, synthetic_profile(source, h.current()))
    expanded(h)
    s = w.evidence_match
    assert s.submit("我有什么经历和这个工作相关？") and s.current()
    return s


@pytest.mark.parametrize("source", SOURCES)
def test_nine_roles_direct_partial_unknown_tension_exact_ownership(source):
    profile = synthetic_profile(source)
    result, context = analyze(profile, source)
    assert {Relation.DIRECT, Relation.PARTIAL, Relation.UNKNOWN, Relation.TENSION} <= {r.relation_type for r in result.relationships}
    user = {s.signal_id:s for s in context.user.signals}
    work = {s.signal_id:s for s in context.work.signals}
    for r in result.relationships:
        assert set(r.user_evidence_ids) == {e for i in r.user_signal_ids for e in user[i].evidence_ids}
        assert set(r.work_evidence_ids) == {e for i in r.work_signal_ids for e in work[i].evidence_ids}
        assert r.profile_version == profile.version and r.source_version == source.version
        assert r.source_fingerprint == context.work.source_fingerprint
        if work[r.work_signal_ids[0]].field in ("capabilities_involved", "unknowns", "work_situations"):
            assert r.relation_type == Relation.UNKNOWN
    assert context.work.variation == source.organizational_variation and context.work.unknowns == source.unknowns


def test_unconfirmed_candidate_rejected_before_provider():
    provider = FakeLLMProvider(None)
    with pytest.raises(ValueError): analyze(UserProfile(profile_id="candidate"), SOURCES[0], provider)
    assert provider.call_count == 0


@pytest.mark.parametrize("uncertainty,inference,source", [
    ("explicit_uncertainty", InferenceType.EXPLICIT_FACT, EvidenceSourceType.EXPLICIT_USER_INPUT),
    ("none", InferenceType.EVIDENCE_SUPPORTED_INFERENCE, EvidenceSourceType.MODEL_INFERENCE)])
def test_inference_and_uncertainty_retained_not_admitted_as_fact(uncertainty, inference, source):
    p = synthetic_profile(SOURCES[0]); data = p.model_dump()
    data["work_experience"][0].update(inference_type=inference, source_type=source)
    data["field_provenance"]["work_experience.public_d5_entry_0"] = ProfileFieldProvenance(
        source_refs=[ProfileSourceReference(origin="model_inference", reference="public_candidate")],
        uncertainty=uncertainty, last_confirmed_at=utc_now()).model_dump()
    p = UserProfile.model_validate(data)
    result, context = analyze(p, SOURCES[0])
    signal = context.user.signals[0]
    assert not signal.eligible and signal.inference_type == inference.value and signal.uncertainty == uncertainty
    assert result.relationships[1].relation_type == Relation.UNKNOWN


def test_reviewed_resume_provenance_accepted_without_changing_inference():
    p = synthetic_profile(SOURCES[0]); data = p.model_dump()
    data["work_experience"][0].update(inference_type=InferenceType.EVIDENCE_SUPPORTED_INFERENCE, source_type=EvidenceSourceType.MODEL_INFERENCE)
    data["field_provenance"]["work_experience.public_d5_entry_0"] = ProfileFieldProvenance(
        source_refs=[ProfileSourceReference(origin="resume_evidence", reference="public_resume:entry_0")],
        last_confirmed_at=utc_now()).model_dump()
    result, context = analyze(UserProfile.model_validate(data), SOURCES[0])
    assert context.user.signals[0].eligible and context.user.signals[0].inference_type == "evidence_supported_inference"
    assert result.relationships[1].relation_type == Relation.DIRECT


def test_interest_never_proves_capability_and_missing_never_tension():
    p = synthetic_profile(SOURCES[0]); data = p.model_dump()
    entry = data["work_experience"].pop(0)
    data["interests"] = [dict(interest_id="public_interest", label=entry["label"], evidence_ids=entry["evidence_ids"],
        confidence=1, source_type="explicit_user_input", confirmed_by_user=True)]
    result, _ = analyze(UserProfile.model_validate(data), SOURCES[0])
    assert result.relationships[1].relation_type == Relation.UNKNOWN


@pytest.mark.parametrize("field,value", [("source_id","specific_wrong"), ("version",2), ("purpose","unsupported")])
def test_changed_source_rejected(field,value):
    with pytest.raises(ValueError): project_work(SOURCES[0].model_copy(update={field:value}))


@pytest.mark.parametrize("field", ["fit_score", "percentage", "ranking", "best_role", "good_fit", "bad_fit", "actions"])
def test_no_score_or_action_schema_and_provider_text_field(field):
    p = synthetic_profile(SOURCES[0]); context = Context(user=project_user(p), work=project_work(SOURCES[0]))
    payload = proposed(context).model_dump(); payload[field] = "invented"
    provider = FakeLLMProvider(payload)
    with pytest.raises(LLMStructuredOutputError): analyze(p, SOURCES[0], provider)
    assert field not in Result.model_fields
    assert not any(v in NOTICE + " ".join(LABELS.values()) for v in ("high fit", "low fit", "good fit", "bad fit", "推荐你选择", "%"))


@pytest.mark.parametrize("side", ["user_signal_ids", "work_signal_ids"])
def test_scoped_ids_reject_unknown_and_wrong_domain(side):
    p = synthetic_profile(SOURCES[0]); c = Context(user=project_user(p), work=project_work(SOURCES[0]))
    payload = proposed(c).model_dump(); payload["relations"][1][side] = ("foreign",)
    with pytest.raises(LLMStructuredOutputError): analyze(p, SOURCES[0], FakeLLMProvider(payload))


def test_semantic_lie_or_unrelated_owned_signal_rejected_no_repair():
    p = synthetic_profile(SOURCES[0]); c = Context(user=project_user(p), work=project_work(SOURCES[0]))
    payload = proposed(c).model_dump(); payload["relations"][1]["user_signal_ids"] = (c.user.signals[1].signal_id,)
    with pytest.raises(ValueError, match="UNSUPPORTED"): assemble(c, Extraction.model_validate(payload))


@pytest.mark.parametrize("text,expected", [
    ("我有什么经历和这个工作相关？","start"), ("这个角色适合我吗？","start"), ("我还缺什么？","start"),
    ("这个方向整体做什么？",None), ("第一种和第二种有什么区别？",None),
    ("这个角色一天怎么工作？",None), ("Python decorator 是什么？",None),
    ("我做过整理记录", "new_evidence"), ("为什么这里还是 unknown？", "detail")])
def test_routing_bounded_whole_question(text, expected): assert intent(text, active=True) == expected


def test_session_only_authority_unchanged_current_claim_not_promoted_and_progressive(h, monkeypatch):
    s = opened(h); w = h.workspace
    before = h.current(), h.memories(), h.history(), s.result
    def forbidden(*a,**k): pytest.fail("No D.5 durable write, retrieval or legacy tool")
    for name in ("save_confirmed_profile", "create_confirmed", "create_candidate", "retrieve_context"):
        monkeypatch.setattr(w.memory_service, name, forbidden)
    monkeypatch.setattr(w.store, "append_turn", forbidden)
    assert len(s.displayed) <= 5
    assert s.submit("我做过更大的项目") and s.result == before[-1]
    assert s.submit("这里具体用了我的哪段经历？") and s.messages[-1].detailed
    assert s.submit("为什么这里还是 unknown？") and s.messages[-1].relationships[0].relation_type == Relation.UNKNOWN
    assert before[:3] == (h.current(), h.memories(), h.history())
    assert not w.chat.messages and not w.store.list_messages(w.owner_scope_id,w.thread.thread_id)
    assert "evidence_match" not in json.dumps(w._snapshot())
    events = json.dumps([e.model_dump(mode="json") for e in s.events])
    assert all(e.text not in events for e in s.context.user.evidence)


@pytest.mark.parametrize("action", ["new", "switch", "delete", "close", "profile", "role", "source"])
def test_lifecycle_invalidation(h, action):
    s = opened(h); w = h.workspace; token = s.token()
    if action == "new": w.create_new_thread()
    elif action == "switch":
        original=w.thread.thread_id; w.create_new_thread(); w.activate(original)
    elif action == "delete": w.delete_thread(w.thread.thread_id)
    elif action == "close": w.close()
    elif action == "profile": w.memory_service.save_confirmed_profile(w.subject_id, h.current().create_revision().confirm())
    elif action == "role": w.specific_role.submit("详细讲讲第二种角色")
    else: w.specific_role.source = w.specific_role.source.model_copy(update={"version":2})
    assert not s.current() and not s.messages
    assert s.submit("我还缺什么？", token=token) and not s.messages


@pytest.mark.parametrize("field,value", [("owner","other"), ("subject","other"), ("thread","other"), ("request_id","other"), ("generation",999), ("turn",999)])
def test_replay_cross_owner_thread_token_dropped(h,field,value):
    s = opened(h); before=s.messages[:]
    assert s.submit("我还缺什么？", token=s.token().model_copy(update={field:value})) and s.messages==before


def test_qa_reload_then_followup_keeps_current_binding(h):
    s = opened(h); stamp=s.binding
    h.workspace.reload_completed_turn(h.workspace.thread.thread_id)
    assert s.current() and s.binding==stamp
    old=s.token(); assert s.submit("展开第1条关系",token=old)
    before=s.messages[:]; assert s.submit("展开第1条关系",token=old) and s.messages==before


def test_late_result_cannot_resurrect_after_new_chat(h):
    s = opened(h); w = h.workspace
    entered, release = ThreadEvent(), ThreadEvent(); factory=s.agent_factory
    def slow(c):
        agent=factory(c); original=agent.analyze_role_relationships
        def run(*a): entered.set(); assert release.wait(8); return original(*a)
        agent.analyze_role_relationships=run; return agent
    s.agent_factory=slow
    thread=Thread(target=lambda:s.submit("这个角色适合我吗？")); thread.start()
    assert entered.wait(8); w.create_new_thread(); release.set(); thread.join(8)
    assert not thread.is_alive() and not s.messages and s.result is None


def test_unconfirmed_signal_flag_rejected_even_in_confirmed_profile():
    raw = synthetic_profile(SOURCES[0]).model_dump()
    raw["work_experience"][0]["confirmed_by_user"] = False
    provider = FakeLLMProvider(None)
    with pytest.raises(ValueError, match="UNCONFIRMED_SIGNAL"):
        analyze(UserProfile.model_validate(raw), SOURCES[0], provider)
    assert provider.call_count == 0


def test_not_applicable_requires_explicit_confirmed_scope_not_missing():
    source = SOURCES[0]; profile = synthetic_profile(source)
    statement = "明确不在本次比较范围：" + source.work_rhythm[0]
    evidence = EvidenceItem(id="public_scope_evidence", statement=statement,
        source_type=EvidenceSourceType.EXPLICIT_USER_INPUT, source_name="public_synthetic_d5", confidence=1)
    entry = ProfileSectionEntry(entry_id="public_scope", label="本次比较范围",
        evidence_ids=[evidence.id], source_type=EvidenceSourceType.EXPLICIT_USER_INPUT, confidence=1)
    profile = profile.create_revision(constraints=[entry], evidence=[*profile.evidence, evidence]).confirm()
    result, context = analyze(profile, source)
    relation = next(r for r in result.relationships if r.relation_type == Relation.NA)
    assert relation.user_evidence_ids == (evidence.id,) and relation.work_evidence_ids
    assert context.work.signals[next(i for i,s in enumerate(context.work.signals) if s.signal_id == relation.work_signal_ids[0])].field == "work_rhythm"


@pytest.mark.parametrize("same_signal", [True, False])
def test_conflicting_confirmed_reports_remain_unknown_not_order_decided(same_signal):
    source = SOURCES[0]; raw = synthetic_profile(source).model_dump()
    evidence = EvidenceItem(id="public_conflict", statement="目前无法独立完成：" + source.responsibilities[0],
        source_type=EvidenceSourceType.EXPLICIT_USER_INPUT, source_name="public_synthetic_d5", confidence=1)
    raw["evidence"].append(evidence.model_dump())
    if same_signal:
        raw["work_experience"][0]["evidence_ids"].append(evidence.id)
    else:
        entry = {**raw["work_experience"][0], "entry_id":"public_conflict_entry", "evidence_ids":[evidence.id]}
        raw["work_experience"].append(entry)
    result, _ = analyze(UserProfile.model_validate(raw), source)
    assert result.relationships[1].relation_type == Relation.UNKNOWN
    assert not result.relationships[1].user_signal_ids


def test_user_scope_survives_relation_limits_not_only_projection():
    result, context = analyze(synthetic_profile(SOURCES[0]), SOURCES[0])
    direct = next(r for r in result.relationships if r.relation_type == Relation.DIRECT)
    signal = next(s for s in context.user.signals if s.signal_id in direct.user_signal_ids)
    assert signal.scope and set(signal.scope) <= set(direct.limitations)


def test_budgets_omit_whole_evidence_mark_partial_without_truncation():
    raw = synthetic_profile(SOURCES[0]).model_dump()
    raw["evidence"][0]["statement"] = "公开合成长材料" * 110
    profile = UserProfile.model_validate(raw)
    result, context = analyze(profile, SOURCES[0])
    assert context.user.partial
    assert all(e.evidence_id != "public_d5_evidence_0" for e in context.user.evidence)
    assert result.relationships[1].relation_type == Relation.UNKNOWN
    assert any("部分材料" in limit for limit in result.relationships[1].limitations)


def test_non_fake_provider_rejected_without_call():
    class ForbiddenProvider:
        def generate_structured(self, *a, **k): pytest.fail("No live/other provider admitted")
    with pytest.raises(ValueError, match="OFFLINE_PROVIDER_REQUIRED"):
        analyze(synthetic_profile(SOURCES[0]), SOURCES[0], ForbiddenProvider())


def test_detail_and_new_claim_do_not_call_provider_again(h):
    s = opened(h)
    s.agent_factory = lambda *_: pytest.fail("Follow-up does not request another analysis")
    result = s.result
    for text in ("为什么你说这个算相关？", "这里具体用了我的哪段经历？", "为什么这里还是 unknown？", "我做过更多公开练习"):
        assert s.submit(text) and s.result == result


@pytest.mark.parametrize("field", ["purpose", "source_id", "representative_role_id"])
def test_same_version_source_mutation_stales_result_and_display(h, field):
    s = opened(h); source = h.workspace.specific_role.source
    h.workspace.specific_role.source = source.model_copy(update={field:"unsupported"})
    assert not s.current() and not s.messages and s.result is None


def test_no_parent_does_not_read_profile_or_fall_back(h, monkeypatch):
    w = h.workspace
    monkeypatch.setattr(w.memory_service, "get_current_confirmed_profile", lambda *_:pytest.fail("No Profile read before valid D.4"))
    w.evidence_match.agent_factory = lambda *_:pytest.fail("No fallback/provider")
    assert w.evidence_match.submit("这个角色适合我吗？")
    assert w.evidence_match.result is None and w.evidence_match.status == "unavailable"


def test_new_workspace_cannot_restore_d5_from_storage(h):
    from ui.chat_runtime import Workspace
    s = opened(h); w = h.workspace
    owner, root = w.owner_scope_id, w.root
    w.close()
    with Workspace(owner, root) as restored:
        assert restored.evidence_match.result is None and not restored.evidence_match.messages
        assert "evidence_match" not in restored._snapshot()


def test_projection_signal_count_budget_uses_whole_entries():
    raw = synthetic_profile(SOURCES[0]).model_dump()
    entry = raw["work_experience"][0]
    raw["work_experience"] += [{**entry, "entry_id":f"public_count_{i}"} for i in range(42)]
    projection = project_user(UserProfile.model_validate(raw))
    assert projection.partial and len(projection.signals) == 40


def test_foreign_owner_cannot_take_result_or_messages(h, tmp_path):
    from ui.chat_runtime import Workspace
    from uuid import uuid4
    s = opened(h)
    with Workspace(str(uuid4()), tmp_path / "other") as other:
        assert other.evidence_match.submit("我还缺什么？", token=s.token())
        assert other.evidence_match.binding is None and not other.evidence_match.messages
    assert s.current()
