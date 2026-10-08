"""Public synthetic D.6 external observer, never imported by production."""

from pathlib import Path
import socket
from tempfile import TemporaryDirectory
from unittest.mock import patch
from specific_role.sources import SpecificRoleRegistry
from career_background_evaluation.match import synthetic_profile
from evidence_match.models import Relation
from evidence_validation.sources import ExperimentRegistry
from evidence_validation.service import targets


def evaluate_validation(root,source):
    from tests.career_discovery_doubles import prepared
    from tests.test_specific_role import expanded
    from evidence_match.service import analyze
    from data.models import UserProfile
    h=prepared(root)
    try:
        w=h.workspace; c=h.checks
        w.memory_service.save_confirmed_profile(w.subject_id,synthetic_profile(source,h.current()))
        peers=[s for s in SpecificRoleRegistry().inventory().records if s.direction_identity==source.direction_identity]
        expanded(h,source.direction_identity.title,peers.index(source))
        w.evidence_match.submit("这个角色适合我吗？")
        parent=w.evidence_match; s=w.evidence_validation
        before=h.current(),h.memories(),h.history(),parent.result,parent.binding,w._snapshot()
        def forbidden(*a,**k): raise AssertionError("D6_FORBIDDEN_WRITE_OR_RETRIEVAL")
        with patch.object(w.memory_service,"save_confirmed_profile",forbidden), patch.object(w.memory_service,"retrieve_context",forbidden), patch.object(w.store,"append_turn",forbidden), patch.object(w.profile_conversation,"start",forbidden):
            c.require("d6_ambiguity",s.submit("我以前其实做过类似的事") and s.target is None and s.pending_claim is not None)
            options=s.messages[-1].options
            target=next(t for t in options if t.relation_type==Relation.PARTIAL)
            c.require("d6_work_unknown_excluded",not {x.signal_id for x in parent.context.work.signals if x.field in ("unknowns","capabilities_involved")} & {t.work_signal_id for t in options})
            c.require("d6_select",s.select(s.messages[-1].token,target.relation_id) and s.current())
            c.require("d6_partial_preserved",s.target.unresolved_scope.startswith("独立性与完整责任尚未证实：") and target.relation_type==Relation.PARTIAL)
            c.require("d6_clarification_authority",s.candidates[0].authority=="session_candidate")
            c.require("d6_template_exact",s.template==ExperimentRegistry().resolve(target,parent.context.work))
            c.require("d6_role_coverage",s.template.role_id==source.representative_role_id)
            for text in ("当前表述：只参与过一次合成练习","范围：协助范围","情境：虚构材料",
                         "给我一个小任务试试","观察：有规则尚待确认","产出：一张合成规则表",
                         "反思：不能推断完整责任","帮助：获得同伴说明","完成本次实验","查看验证摘要","进入已有画像确认入口"):
                c.require("d6_report_accepted",s.submit(text) and s.current())
            c.require("d6_outcome_not_fact",s.outcome.authority=="unverified_session_report" and s.outcome.completion=="reported_completed")
            c.require("d6_handoff_unavailable_safe","未进入 canonical Profile" in s.messages[-1].text)
            c.require("d6_immutable_d5",before[3:5]==(parent.result,parent.binding))
            c.require("d6_authority_unchanged",before[:3]==(h.current(),h.memories(),h.history()))
            c.require("d6_not_persisted",before[5]==w._snapshot() and not w.chat.messages and not w.store.list_messages(w.owner_scope_id,w.thread.thread_id))
            text=" ".join(m.text for m in s.messages if m.role=="assistant")
            c.require("d6_no_score_or_verdict",not any(x in text for x in ("pass/fail","fit score","qualified","high fit","推荐你选择","非常适合","82%")))
            c.require("d6_completion_not_capability","完成不证明能力" in text and "自我反思不是技能事实" in text)
            raw=synthetic_profile(source).model_dump(); raw["work_experience"]=raw["work_experience"][:1]
            result,context=analyze(UserProfile.model_validate(raw),source)
            unknown=next(t for t in targets(result,context) if t.work_evidence_ids==s.template.work_evidence_ids)
            c.require("d6_unknown_not_weakness",unknown.relation_type==Relation.UNKNOWN and unknown.reason=="user_evidence_insufficient")
            c.require("d6_unknown_template",ExperimentRegistry().resolve(unknown,context.work) is not None)
            unsupported=next(t for t in options if ExperimentRegistry().resolve(t,parent.context.work) is None)
            c.require("d6_unsupported_safe",s.select(s.token(),unsupported.relation_id) and s.submit("给我一个小任务试试") and not s.experiment_selected and "unsupported" in s.messages[-1].text)
            token=s.token(); w.create_new_thread()
            c.require("d6_new_chat_clear",s.binding is None and not s.messages and not s.candidates)
            c.require("d6_replay_dropped",s.submit("完成本次实验",token=token) and not s.messages)
        return len(c.passed)
    finally: h.close()


def run():
    attempts=failures=checks=0
    def blocked(*a,**k):
        nonlocal attempts
        attempts+=1; raise AssertionError("D6_OFFLINE_BOUNDARY")
    base=Path(__file__).resolve().parents[1]/"artifacts/evaluation"
    base.mkdir(parents=True,exist_ok=True)
    with patch.object(socket.socket,"connect",blocked), patch.object(socket,"create_connection",blocked), patch("providers.models.load_llm_settings",blocked), patch("resume_evidence.session._qwen_provider",blocked):
        for source in SpecificRoleRegistry().inventory().records:
            with TemporaryDirectory(prefix="d6-",dir=base) as directory:
                try: count=evaluate_validation(directory,source)
                except Exception:
                    failures+=1; print(f"FAIL {source.representative_role_id} category=validation")
                else:
                    checks+=count; print(f"PASS {source.representative_role_id} checks={count}")
    print(f"D.6 total=9 PASS={9-failures} FAIL={failures} checks_passed={checks} network_attempts={attempts}")
    return failures or attempts


if __name__=="__main__":
    raise SystemExit(bool(run()))
