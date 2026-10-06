"""Real Streamlit main-composer integration with offline synthetic providers."""

from uuid import uuid4
import json
import pytest
from tests.test_chat_product import app, WORKSPACE_KEY
from tests.test_career_discovery_ui import prepare
from tests.agent_doubles import ScriptedProvider, plan, answer
from career_reality.models import Dimension, Status


def visible(value):
    return "\n".join(str(e.value) for e in [*value.markdown, *value.text, *value.caption] if not str(e.value).startswith("<style>"))


def start(value, w):
    value.text_input(key="orange_discovery_statement_" + w.thread.thread_id).set_value("探索相邻方向").run()
    value.checkbox(key="orange_discovery_consent_" + w.thread.thread_id).check().run()
    value.button(key="orange_discovery_start").click().run()
    next(b for b in value.button if b.label == "继续探索这个方向").click().run()


@pytest.mark.parametrize("theme", ["浅色模式", "深色模式", "跟随系统"])
def test_selection_free_followup_chips_and_no_detached_d2_form(tmp_path, monkeypatch, theme):
    monkeypatch.setattr("providers.models.load_llm_settings", lambda *a: pytest.fail("No credentials"))
    value = app(tmp_path, str(uuid4()))
    w = value.session_state[WORKSPACE_KEY]
    try:
        h, fake = prepare(w, tmp_path)
        profile, memories, history = h.current(), h.memories(), h.history()
        value.run(); start(value, w)
        assert not value.exception and w.career_reality.current()
        assert len(value.chat_input) == 1 and not value.text_area
        assert not [e for e in [*value.text_input, *value.checkbox] if e.key and e.key.startswith("orange_reality_")]
        assert "公开虚构工作情境" in visible(value) and "工单" in visible(value)
        assert any("把它拆成工作看看" in " ".join(e.value for e in m.markdown) for m in value.chat_message if m.name == "assistant")
        value.chat_input[0].set_value("工作成果是什么？").run()
        assert w.career_reality.messages[-1].reply.dimension == Dimension.IO
        chip = next(b for b in value.button if b.key and b.key.startswith("orange_reality_chip_") and b.label == "需要哪些能力？")
        chip.click().run()
        assert "不是在判断你已经具备或缺少" in visible(value)
        before = len(w.career_reality.messages)
        value.radio(key="orange_appearance").set_value(theme).run(); value.run()
        assert len(w.career_reality.messages) == before and fake.attempts == 1
        assert (profile, memories, history) == (h.current(), h.memories(), h.history())
        assert not w.store.list_messages(w.owner_scope_id, w.thread.thread_id)
        assert "career_reality" not in json.dumps(w._snapshot())
    finally:
        w.close()


def test_unrelated_real_qa_pipeline_then_return_to_work_context(tmp_path):
    value = app(tmp_path, str(uuid4()))
    w = value.session_state[WORKSPACE_KEY]
    try:
        h, fake = prepare(w, tmp_path)
        value.run(); start(value, w)
        stamp = w.career_reality.binding
        qa = ScriptedProvider([plan(relevance="LEARNING_OR_TECHNICAL")], answer("Attention 用相关性权重聚合信息。"))
        w.agent_session.provider_factory = lambda: qa
        value.button(key="orange_agent_consent").click().run()
        value.chat_input[0].set_value("Transformer 的 attention 是什么？").run()
        assert not value.exception and "Attention 用相关性" in visible(value)
        assert qa.structured_calls == qa.stream_calls == 1
        assert qa.requests[-1]["selected_context"] == []
        assert w.career_reality.current() and w.career_reality.binding == stamp
        value.chat_input[0].set_value("那刚才那个方向平时跟谁合作？").run()
        assert not value.exception and w.career_reality.messages[-1].reply.dimension == Dimension.COLLABORATION
        assert qa.structured_calls == qa.stream_calls == fake.attempts == 1
        messages = w.store.list_messages(w.owner_scope_id, w.thread.thread_id)
        assert len(messages) == 2 and all("工单" not in m.content for m in messages)
        w.agent_session.set_consent(granted=False)
        value.button(key="orange_new_chat").click().run()
        assert not w.career_reality.messages and w.career_reality.status == Status.IDLE
    finally:
        w.close()


def test_unsupported_work_question_is_local_unknown(tmp_path):
    value = app(tmp_path, str(uuid4()))
    w = value.session_state[WORKSPACE_KEY]
    try:
        h, fake = prepare(w, tmp_path)
        value.run(); start(value, w)
        value.chat_input[0].set_value("这个方向工资多少？").run()
        assert not value.exception and "保留为未知" in visible(value)
        assert w.career_reality.messages[-1].reply is None
        assert fake.attempts == 1 and not w.chat.messages
    finally:
        w.close()
