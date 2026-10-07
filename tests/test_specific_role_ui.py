"""Actual single-input Public Demo matrix and cross-layer D.2/D.3/D.4/QA routing."""

from uuid import uuid4
import json
import pytest
from tests.test_chat_product import app, WORKSPACE_KEY
from tests.test_public_discovery_demo import confirmed
from tests.test_role_landscape_ui import select
from tests.test_career_reality_ui import visible
from tests.test_specific_role import COVERAGE
from tests.test_role_landscape import offline
from tests.agent_doubles import ScriptedProvider, plan, answer
from specific_role.models import Dimension
from role_landscape.models import Dimension as LandscapeDimension
from career_reality.models import Dimension as RealityDimension


@pytest.mark.parametrize("title,index", COVERAGE)
def test_real_public_demo_all_nine_archetypes_to_d4_without_live_match_or_memory(tmp_path, monkeypatch, title, index):
    value = app(tmp_path, str(uuid4()))
    w = value.session_state[WORKSPACE_KEY]
    try:
        h = confirmed(w, tmp_path)
        before = h.current(), h.memories(), h.history()
        select(value, w, title)
        def forbidden(*a, **k): pytest.fail("No D.4 provider/retrieval/write/tool")
        monkeypatch.setattr(w.agent_session, "queue", forbidden)
        monkeypatch.setattr(w.memory_service, "retrieve_context", forbidden)
        monkeypatch.setattr("career_runtime.tools.ToolRegistry.execute", forbidden)
        s = w.specific_role
        value.chat_input[0].set_value(f"详细讲讲第{index+1}种角色").run()
        assert not value.exception and s.current()
        assert s.source.parent_archetype_id == w.role_landscape.binding.displayed_role_ids[index]
        assert len(value.chat_input) == 1 and not value.text_area
        assert s.source.display_name in visible(value) and "不是真实招聘" in visible(value)
        assert len(s.messages[-1].reply.blocks) == 2
        assert any(e.label == "这段代表性角色理解的来源" for e in value.expander)
        value.button(key=f"orange_specific_chip_{s.binding.request_id}_0").click().run()
        assert s.messages[-1].reply.dimension == Dimension.COLLABORATION
        value.chat_input[0].set_value("这个角色最后要交付什么？").run()
        assert s.messages[-1].reply.dimension == Dimension.IO
        value.chat_input[0].set_value("这个角色适合我吗？").run()
        assert w.evidence_match.current() and "最终决定属于你" in visible(value)
        value.chat_input[0].set_value("你觉得我能做" + w.role_landscape.source.roles[index].display_name + "吗？").run()
        assert not value.exception and s.messages[-1].reply is None
        assert "个人证据与工作证据" in s.messages[-1].text
        value.chat_input[0].set_value(s.source.display_name + "适合我吗？").run()
        assert not value.exception and s.messages[-1].reply is None
        assert "个人证据与工作证据" in s.messages[-1].text
        stamp = s.binding
        value.radio(key="orange_appearance").set_value(("浅色模式", "深色模式", "跟随系统")[index]).run()
        assert not value.exception and s.binding == stamp
        assert before == (h.current(), h.memories(), h.history())
        assert not w.chat.messages and not w.store.list_messages(w.owner_scope_id, w.thread.thread_id)
        assert "specific_role" not in json.dumps(w._snapshot())
        assert not w.controller.state or not w.controller.state.get("match_results")
        value.button(key="orange_new_chat").click().run()
        assert s.binding is None and not s.messages
    finally:
        w.close()


def test_dispatcher_d3_difference_d2_purpose_general_qa_interruption_and_d4_resume(tmp_path):
    value = app(tmp_path, str(uuid4()))
    w = value.session_state[WORKSPACE_KEY]
    try:
        confirmed(w, tmp_path); select(value, w, "Business Analysis")
        value.chat_input[0].set_value("详细讲讲第二种角色").run()
        s, stamp = w.specific_role, w.specific_role.binding
        before = s.messages[:]
        value.chat_input[0].set_value("第一种和第二种有什么区别？").run()
        assert w.role_landscape.messages[-1].reply.dimension == LandscapeDimension.COMPARISON
        assert s.messages == before
        value.chat_input[0].set_value("这个方向整体在解决什么问题？").run()
        assert w.career_reality.messages[-1].reply.dimension == RealityDimension.PURPOSE
        assert s.messages == before
        qa = ScriptedProvider([plan(relevance="LEARNING_OR_TECHNICAL")], answer("Attention 在输入位置之间分配权重。"))
        w.agent_session.provider_factory = lambda: qa
        value.button(key="orange_agent_consent").click().run()
        value.chat_input[0].set_value("Transformer 的 attention 是什么？").run()
        assert not value.exception and "Attention 在输入位置" in visible(value)
        assert qa.structured_calls == qa.stream_calls == 1
        assert qa.requests[-1]["selected_context"] == []
        assert s.current() and s.binding == stamp
        value.chat_input[0].set_value("这个角色通常和谁合作？").run()
        assert s.messages[-1].reply.dimension == Dimension.COLLABORATION
        assert qa.structured_calls == qa.stream_calls == 1
        user_texts = [m.markdown[0].value for m in value.chat_message if m.name == "user" and m.markdown]
        assert user_texts[-5:] == ["详细讲讲第二种角色", "第一种和第二种有什么区别？", "这个方向整体在解决什么问题？", "Transformer 的 attention 是什么？", "这个角色通常和谁合作？"]
        stored = w.store.list_messages(w.owner_scope_id, w.thread.thread_id)
        assert len(stored) == 2 and all(s.source.display_name not in m.content for m in stored)
        w.agent_session.set_consent(granted=False)
    finally:
        w.close()


@pytest.mark.parametrize("title", ["Business Analysis", "Knowledge Operations", "Process Improvement"])
def test_freeze_workday_routing_actual_public_demo_and_qa_resume(tmp_path, monkeypatch, title):
    value = app(tmp_path, str(uuid4()))
    w = value.session_state[WORKSPACE_KEY]
    try:
        h = confirmed(w, tmp_path)
        before = h.current(), h.memories(), h.history()
        select(value, w, title)
        def forbidden(*a, **k): pytest.fail("Bounded work routing must not use provider/Memory/tool")
        monkeypatch.setattr(w.memory_service, "retrieve_context", forbidden)
        monkeypatch.setattr("career_runtime.tools.ToolRegistry.execute", forbidden)
        s = w.specific_role
        with monkeypatch.context() as local:
            local.setattr(w.agent_session, "queue", forbidden)
            local.setattr(w, "submit", forbidden)
            value.chat_input[0].set_value("详细讲讲第二种角色").run()
            assert s.current() and s.messages[-1].reply.dimension == Dimension.OVERVIEW
            stamp, messages = s.binding, s.messages[:]
            for question in ("这个方向整体做什么？", "这个方向整体是做什么的？", "这个方向平时主要做什么？"):
                value.chat_input[0].set_value(question).run()
                assert not value.exception
                assert w.career_reality.messages[-1].reply.dimension == RealityDimension.WORK
                assert s.binding == stamp and s.messages == messages
            value.chat_input[0].set_value("第一种和第二种有什么区别？").run()
            assert w.role_landscape.messages[-1].reply.dimension == LandscapeDimension.COMPARISON
            assert s.messages == messages
            for question in ("这个角色一天怎么工作？", "这个角色一天大概怎么工作？", "这个角色平时一天怎么过？"):
                parents = w.career_reality.messages[:], w.role_landscape.messages[:]
                value.chat_input[0].set_value(question).run()
                assert not value.exception and s.binding == stamp
                assert s.messages[-1].reply.dimension == Dimension.RHYTHM
                assert s.service.validate(s.messages[-1].reply, s.source)
                assert parents == (w.career_reality.messages, w.role_landscape.messages)
            value.chat_input[0].set_value("这个角色适合我吗？").run()
            assert w.evidence_match.current() and "最终决定属于你" in visible(value)
        qa = ScriptedProvider([plan(relevance="LEARNING_OR_TECHNICAL")], answer("Attention 在输入位置之间分配权重。"))
        w.agent_session.provider_factory = lambda: qa
        value.button(key="orange_agent_consent").click().run()
        value.chat_input[0].set_value("Transformer attention 是什么？").run()
        assert not value.exception and "Attention 在输入位置" in visible(value)
        assert qa.structured_calls == qa.stream_calls == 1 and qa.requests[-1]["selected_context"] == []
        assert s.current() and s.binding == stamp
        value.chat_input[0].set_value("这个角色一天大概怎么工作？").run()
        assert not value.exception and s.messages[-1].reply.dimension == Dimension.RHYTHM
        assert qa.structured_calls == qa.stream_calls == 1
        assert before == (h.current(), h.memories(), h.history())
        assert not w.controller.state or not w.controller.state.get("match_results")
        assert "specific_role" not in json.dumps(w._snapshot())
        assert len(w.store.list_messages(w.owner_scope_id, w.thread.thread_id)) == 2
        w.agent_session.set_consent(granted=False)
    finally:
        w.close()


def test_historical_role_messages_keep_their_source_and_new_workspace_cannot_restore_d4(tmp_path):
    owner = str(uuid4())
    value = app(tmp_path, owner)
    w = value.session_state[WORKSPACE_KEY]
    try:
        confirmed(w, tmp_path); select(value, w, "Business Analysis")
        value.chat_input[0].set_value("详细讲讲第一种").run()
        first = w.specific_role.source
        value.chat_input[0].set_value("详细讲讲第二种").run()
        assert first.display_name in visible(value) and w.specific_role.source.display_name in visible(value)
        assert not value.exception
        value = app(tmp_path, owner)
        restored = value.session_state[WORKSPACE_KEY]
        try:
            assert restored.specific_role.binding is None and not restored.specific_role.messages
            assert not restored.role_landscape.current()
        finally:
            restored.close()
    finally:
        w.close()
