"""Actual main-chat public Demo entry, not injected role results or a directory."""

from uuid import uuid4
import json
import pytest
from tests.test_chat_product import app, WORKSPACE_KEY
from tests.test_public_discovery_demo import confirmed, enter
from tests.test_career_reality_ui import visible
from tests.test_role_landscape import DIRECTIONS, OLD_ROLES, offline
from tests.agent_doubles import ScriptedProvider, plan, answer
from role_landscape.models import Dimension


def select(value, w, title):
    enter(value, w)
    value.chat_input[0].set_value("都可以看看").run()
    result = w.career_discovery.result
    direction = next(d for d in result.directions if d.title == title)
    value.button(key="orange_direction_" + result.request_id + "_" + direction.direction_id).click().run()
    assert w.career_reality.current()
    value.chat_input[0].set_value("这个方向有哪些岗位？").run()
    assert not value.exception and w.role_landscape.current()


@pytest.mark.parametrize("title,theme", [(DIRECTIONS[0],"浅色模式"), (DIRECTIONS[1],"深色模式"), (DIRECTIONS[2],"跟随系统")])
def test_actual_demo_full_path_each_direction_and_progressive_followup(tmp_path, monkeypatch, title, theme):
    value = app(tmp_path, str(uuid4()))
    w = value.session_state[WORKSPACE_KEY]
    try:
        h = confirmed(w, tmp_path)
        before = h.current(), h.memories(), h.history()
        # D.1 can read its original Memory; D.3 must add none after selection.
        select(value, w, title)
        def forbidden(*a, **k): pytest.fail("No added D.3 retrieval/provider/job tool")
        monkeypatch.setattr(w.memory_service, "retrieve_context", forbidden)
        # D.1's existing card renderer revalidates its original Memory refs.
        # Isolated D.3 tests forbid get entirely; do not ban D.1's prior guard.
        monkeypatch.setattr("career_runtime.tools.ToolRegistry.execute", forbidden)
        monkeypatch.setattr(w.agent_session, "queue", forbidden)
        assert len(value.chat_input) == 1 and not value.text_area
        text = visible(value)
        assert all(r.display_name in text for r in w.role_landscape.source.roles)
        assert all(name not in text for name in OLD_ROLES)
        assert "不是排名" in text and "本合成资料" in text
        assert w.role_landscape.messages[-1].reply.dimension == Dimension.OVERVIEW
        value.chat_input[0].set_value("第一种主要做什么？").run()
        assert w.role_landscape.messages[-1].reply.dimension == Dimension.WORK
        value.chat_input[0].set_value("第二种和第一种有什么区别？").run()
        assert w.role_landscape.messages[-1].reply.dimension == Dimension.COMPARISON
        value.chat_input[0].set_value("刚才偏系统的那个呢？").run()
        assert w.role_landscape.messages[-1].reply.dimension == Dimension.TECHNICAL
        value.chat_input[0].set_value("那你觉得哪个更适合我？").run()
        assert w.role_landscape.messages[-1].reply is None and "没有推荐" in visible(value)
        stamp = w.role_landscape.binding
        value.radio(key="orange_appearance").set_value(theme).run(); value.run()
        assert not value.exception and w.role_landscape.binding == stamp
        assert before == (h.current(), h.memories(), h.history())
        assert not w.chat.messages and not w.store.list_messages(w.owner_scope_id, w.thread.thread_id)
        assert "role_landscape" not in json.dumps(w._snapshot())
        value.button(key="orange_new_chat").click().run()
        assert not w.role_landscape.messages and w.role_landscape.binding is None
    finally:
        w.close()


def test_real_general_qa_interrupt_then_resume_owned_role_not_persisted(tmp_path):
    value = app(tmp_path, str(uuid4()))
    w = value.session_state[WORKSPACE_KEY]
    try:
        confirmed(w, tmp_path); select(value, w, DIRECTIONS[0])
        stamp = w.role_landscape.binding
        qa = ScriptedProvider([plan(relevance="LEARNING_OR_TECHNICAL")], answer("Decorator 包装函数以扩展行为。"))
        w.agent_session.provider_factory = lambda: qa
        value.button(key="orange_agent_consent").click().run()
        value.chat_input[0].set_value("Python decorator 是什么？").run()
        assert not value.exception and "Decorator 包装函数" in visible(value)
        assert qa.structured_calls == qa.stream_calls == 1
        assert qa.requests[-1]["selected_context"] == []
        assert w.role_landscape.current() and w.role_landscape.binding == stamp
        value.chat_input[0].set_value("刚才第二种角色平时和谁合作？").run()
        assert w.role_landscape.messages[-1].reply.dimension == Dimension.COLLABORATION
        assert qa.structured_calls == qa.stream_calls == 1
        stored = w.store.list_messages(w.owner_scope_id, w.thread.thread_id)
        assert len(stored) == 2 and all("需求转译型" not in m.content for m in stored)
        w.agent_session.set_consent(granted=False)
    finally:
        w.close()


def test_ephemeral_d2_and_d3_keep_actual_interleaved_order(tmp_path):
    value = app(tmp_path, str(uuid4()))
    w = value.session_state[WORKSPACE_KEY]
    try:
        confirmed(w, tmp_path); select(value, w, DIRECTIONS[0])
        value.chat_input[0].set_value("工作成果是什么？").run()  # D.2 owned question
        value.chat_input[0].set_value("第一种主要做什么？").run()  # D.3 owned question
        user_texts = [m.markdown[0].value for m in value.chat_message if m.name == "user" and m.markdown]
        assert user_texts[-3:] == ["这个方向有哪些岗位？", "工作成果是什么？", "第一种主要做什么？"]
        assert not value.exception and not w.chat.messages
    finally:
        w.close()
