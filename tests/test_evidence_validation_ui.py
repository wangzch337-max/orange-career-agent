"""Actual composer, explicit choice and nine public D.1→D.6 paths; Fake only."""

from uuid import uuid4
import pytest
from tests.test_chat_product import app, WORKSPACE_KEY
from tests.test_public_discovery_demo import confirmed
from tests.test_role_landscape_ui import select
from tests.test_career_reality_ui import visible
from tests.test_specific_role import COVERAGE
from tests.test_role_landscape import offline
from tests.agent_doubles import ScriptedProvider, plan, answer
from specific_role.sources import SpecificRoleRegistry
from career_background_evaluation.match import synthetic_profile
from evidence_match.models import Relation


def open_ui(tmp_path, title="Business Analysis", index=0):
    value=app(tmp_path,str(uuid4())); w=value.session_state[WORKSPACE_KEY]
    h=confirmed(w,tmp_path)
    source=[s for s in SpecificRoleRegistry().inventory().records if s.direction_identity.title==title][index]
    w.memory_service.save_confirmed_profile(w.subject_id,synthetic_profile(source,h.current()))
    select(value,w,title)
    value.chat_input[0].set_value(f"详细讲讲第{index+1}种角色").run()
    value.chat_input[0].set_value("这个角色适合我吗？").run()
    return value,w,h


@pytest.mark.parametrize("title,index",COVERAGE)
def test_actual_nine_paths_explicit_target_and_all_reports_session_only(tmp_path,monkeypatch,title,index):
    value,w,h=open_ui(tmp_path,title,index)
    try:
        s=w.evidence_validation; old=w.evidence_match.result
        before=h.current(),h.memories(),h.history(),w._snapshot()
        def forbidden(*a,**k): pytest.fail("D6 UI must remain offline and ephemeral")
        for name in ("save_confirmed_profile","create_confirmed","create_candidate","retrieve_context"):
            monkeypatch.setattr(w.memory_service,name,forbidden)
        monkeypatch.setattr(w.store,"append_turn",forbidden)
        monkeypatch.setattr(w.agent_session,"queue",forbidden)
        value.chat_input[0].set_value("我怎么验证这一点？").run()
        assert not value.exception and s.target is None and "不会默认选择第一项" in visible(value)
        target=next(t for t in s.messages[-1].options if t.relation_type==Relation.PARTIAL)
        number=s.messages[-1].options.index(target)+1
        button=next(b for b in value.button if b.label==f"验证第{number}项" and not b.disabled)
        button.click().run()
        assert not value.exception and s.current() and s.target==target
        assert not value.text_area and len(value.chat_input)==1
        for phrase in ("我以前其实做过类似的事","范围：合成课堂协助范围","给我一个小任务试试",
                       "观察：两个疑问待核对","产出：合成观察表","反思：范围仍有限","帮助：同伴解释",
                       "完成本次实验","进入已有画像确认入口"):
            value.chat_input[0].set_value(phrase).run()
            assert not value.exception and s.current()
        assert s.outcome.completion=="reported_completed" and s.template.role_id==old.role_id
        body=visible(value)
        assert "未进入 canonical Profile" in body and "产出不证明独立作者身份" in body
        assert w.evidence_match.result==old and before==(h.current(),h.memories(),h.history(),w._snapshot())
        assert not w.chat.messages and not w.store.list_messages(w.owner_scope_id,w.thread.thread_id)
        assert not w.controller.state or not w.controller.state.get("match_results")
        value.button(key="orange_new_chat").click().run()
        assert s.binding is None and not s.messages and not s.candidates
    finally: w.close()


def test_actual_routing_matrix_qa_interrupt_resume_no_personal_context(tmp_path):
    value,w,h=open_ui(tmp_path)
    try:
        for phrase,session in (("这个方向整体做什么？",w.career_reality),
            ("第一种和第二种有什么区别？",w.role_landscape),
            ("这个角色一天怎么工作？",w.specific_role),("为什么这里是 unknown？",w.evidence_match)):
            old=len(session.messages); value.chat_input[0].set_value(phrase).run()
            assert not value.exception and len(session.messages)>old
        value.chat_input[0].set_value("我以前其实做过类似的事").run()
        s=w.evidence_validation; assert s.pending_claim and s.target is None
        value.chat_input[0].set_value("验证第1项").run(); stamp=s.binding
        assert s.current()
        qa=ScriptedProvider([plan(relevance="LEARNING_OR_TECHNICAL")],answer("Decorator 包装一个函数。"))
        w.agent_session.provider_factory=lambda:qa
        value.button(key="orange_agent_consent").click().run()
        value.chat_input[0].set_value("Python decorator 是什么？").run()
        assert not value.exception and qa.structured_calls==qa.stream_calls==1
        assert qa.requests[-1]["selected_context"]==[] and s.current() and s.binding==stamp
        value.chat_input[0].set_value("给我一个小任务试试").run()
        assert s.experiment_selected and qa.structured_calls==qa.stream_calls==1
        assert len(w.store.list_messages(w.owner_scope_id,w.thread.thread_id))==2
        assert not s.submit("我应该学什么？")
        w.agent_session.set_consent(granted=False)
    finally: w.close()


def test_missing_parent_consumed_without_persistence_or_general_provider(tmp_path,monkeypatch):
    value=app(tmp_path,str(uuid4())); w=value.session_state[WORKSPACE_KEY]
    try:
        def forbidden(*a,**k): pytest.fail("No parent cannot become a model call")
        monkeypatch.setattr(w.agent_session,"queue",forbidden)
        monkeypatch.setattr(w.store,"append_turn",forbidden)
        value.chat_input[0].set_value("给我一个小任务试试").run()
        assert not value.exception and w.evidence_validation.target is None
        # Unavailable D.6 messages still render when there are no D.5 messages.
        assert "需要当前有效的 D.5 关系" in visible(value)
    finally: w.close()
