"""Public synthetic D.6 grounding, authority, routing and lifecycle tests."""

import json
from pathlib import Path
from threading import Event, Thread
from uuid import uuid4
import pytest
from data.models import UserProfile
from evidence_match.models import Relation
from evidence_match.service import analyze
from evidence_validation.models import Outcome, Candidate
from evidence_validation.service import targets, NOTICE
from evidence_validation.session import intent
from evidence_validation.sources import ExperimentRegistry, SOURCE_PATH
from specific_role.sources import SpecificRoleRegistry
from career_background_evaluation.match import synthetic_profile
from tests.test_evidence_match import opened
from tests.test_role_landscape import h, offline
from ui.chat_runtime import Workspace

SOURCES = SpecificRoleRegistry().inventory().records


def selected(h):
    parent = opened(h); s = h.workspace.evidence_validation
    assert s.submit("我怎么验证这一点？") and s.target is None
    options = s.messages[-1].options
    target = next(t for t in options if t.relation_type == Relation.PARTIAL)
    assert s.select(s.messages[-1].token, target.relation_id) and s.current()
    return s


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize("kind", ["partial", "unknown"])
def test_nine_templates_exact_unresolved_scope_and_no_first_fallback(source, kind):
    p = synthetic_profile(source)
    if kind == "unknown":
        raw = p.model_dump(); raw["work_experience"] = raw["work_experience"][:1]
        p = UserProfile.model_validate(raw)
    result, context = analyze(p, source)
    options = targets(result, context)
    template = next(t for t in ExperimentRegistry().inventory().templates if t.role_id == source.representative_role_id)
    target = next(t for t in options if t.work_evidence_ids == template.work_evidence_ids)
    assert target.relation_type == (Relation.PARTIAL if kind == "partial" else Relation.UNKNOWN)
    assert target.unresolved_scope == (template.partial_scope if kind == "partial" else template.unknown_scope)
    assert ExperimentRegistry().resolve(target, context.work) == template
    assert template.optional and template.can_stop and 30 <= template.estimated_minutes <= 90
    work = next(s for s in context.work.signals if s.signal_id == target.work_signal_id)
    assert work.authority.name == template.work_authority and work.field == template.work_field
    assert all(s.field != "unknowns" for s in context.work.signals if s.signal_id in {o.work_signal_id for o in options})


def test_work_unknown_capability_exposition_and_projection_omission_not_user_test():
    result, c = analyze(synthetic_profile(SOURCES[0]), SOURCES[0])
    ids = {t.work_signal_id for t in targets(result,c)}
    assert not {s.signal_id for s in c.work.signals if s.field in ("unknowns","capabilities_involved","work_situations")} & ids
    from evidence_match.service import assemble, proposed
    changed = c.model_copy(update={"user":c.user.model_copy(update={"partial":True})})
    assert targets(assemble(changed,proposed(changed)),changed) == ()


def test_coherently_forged_work_projection_still_rejected():
    from evidence_match.service import assemble, proposed
    result,c=analyze(synthetic_profile(SOURCES[0]),SOURCES[0])
    work=c.work.signals[2].model_copy(update={"label":"unapproved task"})
    changed=c.model_copy(update={"work":c.work.model_copy(update={"signals":(*c.work.signals[:2],work,*c.work.signals[3:])})})
    with pytest.raises(ValueError,match="UNVALIDATED_PARENT"):
        targets(assemble(changed,proposed(changed)),changed)


@pytest.mark.parametrize("field", ["reason","relation_type","relationship_id","work_evidence_ids","source_version"])
def test_unvalidated_parent_relation_rejected_without_repair(field):
    result,c=analyze(synthetic_profile(SOURCES[0]),SOURCES[0])
    r=result.relationships[2]; values={"reason":"unsupported","relation_type":Relation.UNKNOWN,
        "relationship_id":"foreign","work_evidence_ids":("foreign",),"source_version":99}
    changed=r.model_copy(update={field:values[field]})
    with pytest.raises(ValueError,match="UNVALIDATED_PARENT"):
        targets(result.model_copy(update={"relationships":(*result.relationships[:2],changed,*result.relationships[3:])}),c)


def test_conflicting_confirmed_reports_do_not_become_user_experiment():
    from data.models import EvidenceItem, ProfileSectionEntry, EvidenceSourceType
    source=SOURCES[0]; p=synthetic_profile(source)
    text="目前无法独立完成：" + source.responsibilities[1]
    e=EvidenceItem(id="public_d6_conflict",statement=text,source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,source_name="public_synthetic",confidence=1)
    entry=ProfileSectionEntry(entry_id="public_d6_conflict_entry",label=text,evidence_ids=[e.id],source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,confidence=1)
    p=p.create_revision(work_experience=[*p.work_experience,entry],evidence=[*p.evidence,e]).confirm()
    result,c=analyze(p,source)
    assert result.relationships[2].relation_type == Relation.UNKNOWN
    assert "relationship_003" not in {t.relation_id for t in targets(result,c)}


@pytest.mark.parametrize("phrase,expected", [
    ("我以前其实做过类似的事","recollection"),("我以前其实做过类似的事情","recollection"),
    ("我怎么验证这一点？","experiment"),("给我一个小任务试试","experiment"),
    ("为什么这里是 unknown？",None),("我应该学什么？",None),
    ("这个角色一天怎么工作？",None),("这个角色适合我吗？",None),
    ("Python decorator 是什么？",None),("怎么验证 Python decorator？",None),
    ("验证第2项","select"),("完成本次实验","completion"),("中止本次实验","stop"),
    ("观察：记下了三个待核对问题","report"),("进入已有画像确认入口","handoff")])
def test_bounded_routing(phrase,expected):
    assert intent(phrase)==expected
    if phrase=="为什么这里是 unknown？":
        from evidence_match.session import intent as d5
        assert d5(phrase,active=True)=="detail"


def test_ambiguous_claim_remains_pending_until_explicit_target_and_safe_unsupported(h):
    p=opened(h); s=h.workspace.evidence_validation
    assert s.submit("我以前其实做过类似的事")
    assert s.target is None and not s.candidates and s.pending_claim
    assert len(s.messages[-1].options)>1
    target=next(t for t in s.messages[-1].options if t.relation_type==Relation.UNKNOWN)
    assert s.select(s.messages[-1].token,target.relation_id)
    assert s.candidates[0].authority=="session_candidate"
    assert s.template is None
    assert s.submit("给我一个小任务试试") and "unsupported" in s.messages[-1].text
    assert not s.experiment_selected and p.result.relationships


def test_candidates_outcomes_handoff_and_summary_never_write_or_mutate(h,monkeypatch):
    s=selected(h); w=h.workspace; parent=w.evidence_match
    before=h.current(),h.memories(),h.history(),parent.result,parent.binding,w._snapshot()
    def forbidden(*a,**k): pytest.fail("D6 cannot read Memory, start provider, write or confirm")
    for name in ("save_confirmed_profile","create_confirmed","create_candidate","supersede","retrieve_context"):
        monkeypatch.setattr(w.memory_service,name,forbidden)
    for name in ("get","list_memories"):
        if hasattr(w.memory_service.memory_store,name): monkeypatch.setattr(w.memory_service.memory_store,name,forbidden)
    monkeypatch.setattr(w.store,"append_turn",forbidden)
    monkeypatch.setattr(w.store,"save_snapshot",forbidden) if hasattr(w.store,"save_snapshot") else None
    monkeypatch.setattr(w.profile_conversation,"start",forbidden)
    monkeypatch.setattr(w.profile_refinement,"confirm",forbidden)
    monkeypatch.setattr(parent,"agent_factory",forbidden)
    for text in ("我以前其实做过类似的事","当前表述：只参与一次虚构活动","范围：协助整理","情境：课堂虚构练习",
                 "给我一个小任务试试","观察：有两条规则待核对","产出：一张规则表","反思：仍不清楚异常处理",
                 "帮助：同伴解释了一部分","完成本次实验","查看验证摘要","进入已有画像确认入口"):
        assert s.submit(text) and s.current()
    assert len(s.candidates)==4 and s.outcome.completion=="reported_completed"
    assert s.outcome.authority=="unverified_session_report" and s.outcome.assistance_reports
    assert "未进入 canonical Profile" in s.messages[-1].text and s.handoff_requested
    assert (parent.result,parent.binding,w._snapshot())==before[3:]
    assert not w.chat.messages and not w.store.list_messages(w.owner_scope_id,w.thread.thread_id)
    assert "evidence_validation" not in json.dumps(w._snapshot())
    monkeypatch.undo()
    assert before[:3]==(h.current(),h.memories(),h.history())
    assert not w.controller.state or not w.controller.state.get("match_results")


@pytest.mark.parametrize("available",[True,False])
def test_explicit_handoff_does_not_invoke_old_flow(h,monkeypatch,available):
    s=selected(h); assert not s.handoff_requested
    from types import SimpleNamespace
    from career_runtime.profile_conversation import InterviewStage
    w=h.workspace
    if available:
        w.profile_conversation.stage=InterviewStage.REVIEW
        w.profile_conversation._token=SimpleNamespace(owner=w.owner_scope_id,thread=w.thread.thread_id)
    def forbidden(*a,**k): pytest.fail("Navigation is not consent or confirmation")
    monkeypatch.setattr(h.workspace.profile_conversation,"start",forbidden)
    monkeypatch.setattr(h.workspace.profile_conversation,"available",forbidden)
    monkeypatch.setattr(h.workspace.resume_analysis,"_identity",forbidden)
    assert s.submit("进入已有画像确认入口") and s.handoff_requested
    assert ("入口可用" if available else "入口不可用") in s.messages[-1].text


@pytest.mark.parametrize("field",["score","pass_fail","qualified","fit_score","skill_fact","confirmed_evidence"])
@pytest.mark.parametrize("cls",[Outcome,Candidate])
def test_no_canonical_or_grade_fields(cls,field):
    payload={} if cls==Outcome else {"kind":"recollection","text":"合成练习"}
    with pytest.raises(ValueError): cls.model_validate({**payload,field:True})
    assert field not in cls.model_fields


@pytest.mark.parametrize("mutation",["bytes","version","direction","archetype","role","work_ref","duplicate","source_fp","field","provenance","score"])
def test_fixture_rejects_all_unapproved_changes(monkeypatch,mutation):
    data=json.loads(SOURCE_PATH.read_text()); t=data["templates"][0]
    if mutation=="bytes": t["task"]+=" unapproved"
    elif mutation=="duplicate": data["templates"][1]=t
    else:
        keys={"version":"version","direction":"direction_id","archetype":"archetype_id","role":"role_id",
            "work_ref":"work_evidence_ids","source_fp":"source_fingerprint","field":"work_field","provenance":"provenance","score":"fit_score"}
        t[keys[mutation]]=2 if mutation=="version" else ["foreign"] if mutation=="work_ref" else "foreign"
    original=Path.read_bytes
    monkeypatch.setattr(Path,"read_bytes",lambda p:json.dumps(data).encode() if p==SOURCE_PATH else original(p))
    with pytest.raises(ValueError): ExperimentRegistry().inventory()


def test_identical_fixture_at_noncanonical_path_rejected(tmp_path):
    with pytest.raises(ValueError): ExperimentRegistry(tmp_path/"experiments.json").inventory()
    with pytest.raises(ValueError): ExperimentRegistry(SOURCE_PATH.parent/".."/"evidence_validation"/"experiments.json").inventory()


@pytest.mark.parametrize("action",["new","switch","delete","close","profile","role","source","parent_result","parent_generation","template","local_template","user_projection"])
def test_lifecycle_every_binding_invalidates_no_resurrection(h,monkeypatch,action):
    s=selected(h); w=h.workspace; token=s.token()
    if action=="new": w.create_new_thread()
    elif action=="switch":
        old=w.thread.thread_id; w.create_new_thread(); w.activate(old)
    elif action=="delete": w.delete_thread(w.thread.thread_id)
    elif action=="close": w.close()
    elif action=="profile": w.memory_service.save_confirmed_profile(w.subject_id,h.current().create_revision().confirm())
    elif action=="role": w.specific_role.submit("详细讲讲第二种角色")
    elif action=="source": w.specific_role.source=w.specific_role.source.model_copy(update={"version":2})
    elif action=="parent_result":
        p=w.evidence_match; r=p.result.relationships[2].model_copy(update={"reason":"unvalidated"})
        p.result=p.result.model_copy(update={"relationships":(*p.result.relationships[:2],r,*p.result.relationships[3:])})
    elif action=="parent_generation": w.evidence_match.generation+=1
    elif action=="local_template": s.template=s.template.model_copy(update={"task":"unapproved task"})
    elif action=="user_projection":
        from evidence_match.service import assemble, proposed
        p=w.evidence_match
        signal=p.context.user.signals[0].model_copy(update={"label":"unapproved claim"})
        p.context=p.context.model_copy(update={"user":p.context.user.model_copy(update={"signals":(signal,*p.context.user.signals[1:])})})
        p.result=assemble(p.context,proposed(p.context))
    else:
        old=s.registry.resolve
        monkeypatch.setattr(s.registry,"resolve",lambda *a:old(*a).model_copy(update={"version":2}))
    assert not s.current() and not s.messages and not s.candidates and s.binding is None
    assert s.submit("完成本次实验",token=token) and not s.messages


@pytest.mark.parametrize("field,value",[("owner","foreign"),("subject","foreign"),("thread","foreign"),
    ("request_id","foreign"),("generation",999),("turn",999),("parent_fingerprint","0"*64)])
def test_foreign_and_replayed_token_dropped(h,field,value):
    s=selected(h); old=s.messages[:]
    assert s.submit("给我一个小任务试试",token=s.token().model_copy(update={field:value})) and s.messages==old


def test_duplicate_token_stop_and_qa_restore(h):
    s=selected(h); stamp=s.binding
    h.workspace.reload_completed_turn(h.workspace.thread.thread_id)
    assert s.current() and s.binding==stamp
    token=s.token(); s.submit("给我一个小任务试试",token=token); messages=s.messages[:]
    assert s.submit("给我一个小任务试试",token=token) and s.messages==messages
    token=s.token(); assert s.submit("中止本次实验",token=token)
    assert s.outcome.completion=="stopped" and not s.candidates and not s.experiment_selected
    old=s.messages[:]; assert s.submit("完成本次实验",token=token) and s.messages==old


def test_late_publication_rejected_after_new_chat(h):
    s=selected(h); entered,release=Event(),Event(); original=s.prepare
    def slow(t): entered.set(); assert release.wait(10); return original(t)
    s.prepare=slow
    thread=Thread(target=lambda:s.submit("给我一个小任务试试")); thread.start()
    assert entered.wait(10); h.workspace.create_new_thread(); release.set(); thread.join(10)
    assert not thread.is_alive() and not s.messages and not s.experiment_selected


def test_same_owner_reload_does_not_restore_session_or_pending_claim(h):
    s=selected(h); w=h.workspace; owner,root=w.owner_scope_id,w.root
    s.submit("当前表述：合成候选"); w.close()
    with Workspace(owner,root) as restored:
        assert not restored.evidence_validation.messages and restored.evidence_validation.binding is None
