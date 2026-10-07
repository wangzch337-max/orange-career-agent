"""Actual public Demo composer D.1–D.5 and General QA, all Fake."""

from uuid import uuid4
import pytest
from tests.test_chat_product import app, WORKSPACE_KEY
from tests.test_public_discovery_demo import confirmed
from tests.test_role_landscape_ui import select
from tests.test_career_reality_ui import visible
from tests.test_specific_role import COVERAGE
from tests.test_role_landscape import offline
from tests.agent_doubles import ScriptedProvider, plan, answer
from career_background_evaluation.match import synthetic_profile
from specific_role.sources import SpecificRoleRegistry
from evidence_match.models import Relation


@pytest.mark.parametrize("title,index", COVERAGE)
def test_actual_nine_d5_paths_no_verdict_action_persistence_or_authority_write(tmp_path,monkeypatch,title,index):
    value=app(tmp_path,str(uuid4())); w=value.session_state[WORKSPACE_KEY]
    try:
        h=confirmed(w,tmp_path)
        source=[s for s in SpecificRoleRegistry().inventory().records if s.direction_identity.title==title][index]
        w.memory_service.save_confirmed_profile(w.subject_id,synthetic_profile(source,h.current()))
        select(value,w,title)
        value.chat_input[0].set_value(f"详细讲讲第{index+1}种角色").run()
        before=h.current(),h.memories(),h.history()
        def forbidden(*a,**k): pytest.fail("D.5 forbids write/retrieval/runtime/legacy Match")
        for name in ("save_confirmed_profile","create_confirmed","create_candidate","retrieve_context"):
            monkeypatch.setattr(w.memory_service,name,forbidden)
        monkeypatch.setattr(w.store,"append_turn",forbidden)
        monkeypatch.setattr(w.agent_session,"queue",forbidden)
        value.chat_input[0].set_value("这个角色适合我吗？").run()
        s=w.evidence_match
        assert not value.exception and s.current() and s.result.role_id==source.representative_role_id
        assert {Relation.DIRECT,Relation.PARTIAL,Relation.UNKNOWN,Relation.TENSION} <= {r.relation_type for r in s.displayed}
        assert len(value.chat_input)==1 and not value.text_area
        assert "最终决定属于你" in visible(value)
        assert not any(word in visible(value) for word in ("high fit","low fit","good fit","bad fit","推荐你选择","你的缺点是","你缺少"))
        value.chat_input[0].set_value("这里具体用了我的哪段经历？").run()
        assert not value.exception and s.messages[-1].detailed and "public_d5_evidence_0" in visible(value)
        value.chat_input[0].set_value("我还缺什么？").run()
        assert not value.exception and "材料不足不是能力弱点" in visible(value)
        stamp=s.binding
        value.chat_input[0].set_value("这个角色一天怎么工作？").run()
        assert w.specific_role.messages[-1].reply.dimension.value=="work_rhythm" and s.binding==stamp
        value.chat_input[0].set_value("这个方向整体做什么？").run()
        assert w.career_reality.messages[-1].reply.dimension.value=="typical_work" and s.binding==stamp
        value.chat_input[0].set_value("第一种和第二种有什么区别？").run()
        assert w.role_landscape.messages[-1].reply.dimension.value=="comparison" and s.binding==stamp
        assert before==(h.current(),h.memories(),h.history())
        assert not w.chat.messages and not w.store.list_messages(w.owner_scope_id,w.thread.thread_id)
        assert not w.controller.state or not w.controller.state.get("match_results")
        value.button(key="orange_new_chat").click().run()
        assert s.binding is None and not s.messages
    finally: w.close()


def test_actual_qa_interruption_resume_d5_without_personal_context(tmp_path):
    value=app(tmp_path,str(uuid4())); w=value.session_state[WORKSPACE_KEY]
    try:
        confirmed(w,tmp_path); select(value,w,"Business Analysis")
        value.chat_input[0].set_value("详细讲讲第二种角色").run()
        value.chat_input[0].set_value("我还缺什么？").run()
        s=w.evidence_match; stamp=s.binding
        qa=ScriptedProvider([plan(relevance="LEARNING_OR_TECHNICAL")],answer("Decorator 包装一个函数。"))
        w.agent_session.provider_factory=lambda:qa
        value.button(key="orange_agent_consent").click().run()
        value.chat_input[0].set_value("Python decorator 是什么？").run()
        assert not value.exception and qa.structured_calls==qa.stream_calls==1
        assert qa.requests[-1]["selected_context"]==[] and s.current() and s.binding==stamp
        value.chat_input[0].set_value("为什么这里还是 unknown？").run()
        assert not value.exception and s.messages[-1].detailed
        assert qa.structured_calls==qa.stream_calls==1
        stored=w.store.list_messages(w.owner_scope_id,w.thread.thread_id)
        assert len(stored)==2 and all("证据关系" not in m.content for m in stored)
        w.agent_session.set_consent(granted=False)
    finally:w.close()


def test_missing_parent_is_visible_unavailable_not_general_qa(tmp_path,monkeypatch):
    value=app(tmp_path,str(uuid4())); w=value.session_state[WORKSPACE_KEY]
    try:
        monkeypatch.setattr(w.agent_session,"queue",lambda *_:pytest.fail("Missing D.4 cannot fall back to QA"))
        value.chat_input[0].set_value("这个角色适合我吗？").run()
        assert not value.exception and "需要当前合法的代表性角色和已确认画像" in visible(value)
        assert not w.chat.messages and not w.store.list_messages(w.owner_scope_id,w.thread.thread_id)
    finally:w.close()
