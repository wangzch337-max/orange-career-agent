"""Automated public/Fake user paths, NOT manual visual or live acceptance."""

from uuid import uuid4
import pytest

from career_background_evaluation.harness import CareerHarness, CapturingFake
from career_background_evaluation.scenarios import SCENARIOS
from tests.career_discovery_doubles import proposal_from_payload
from tests.test_chat_product import app, WORKSPACE_KEY
from tests.agent_doubles import ScriptedProvider, plan, answer


def visible(value):
    return "\n".join(str(e.value) for e in [*value.markdown, *value.caption, *value.text] if not str(e.value).startswith("<style>"))


def prepare(value, tmp_path):
    w = value.session_state[WORKSPACE_KEY]
    h = CareerHarness(tmp_path, SCENARIOS[12], workspace=w)
    h.prepare(); h.resolve_all(); h.confirm(memory=True)
    w.agent_session.set_consent(granted=False)
    fake = CapturingFake(proposal_from_payload)
    w.career_discovery.provider_factory = lambda: fake
    value.button(key="orange_new_chat").click().run()
    return w, h, fake


def enter_discovery(value, w):
    value.button(key="orange_opening_discover").click().run()
    assert w.career_discovery.status.value == "CONSENT_REQUIRED"
    value.checkbox(key="orange_discovery_consent_" + w.thread.thread_id).check().run()
    value.button(key="orange_discovery_start").click().run()
    assert w.career_discovery.pending_token() is not None


def test_manual_equivalent_new_chat_opening_pending_answer_direction_and_reality(tmp_path, monkeypatch):
    monkeypatch.setattr("providers.models.load_llm_settings", lambda *a: pytest.fail("No configuration"))
    value = app(tmp_path, str(uuid4()))
    w = value.session_state[WORKSPACE_KEY]
    try:
        w, h, fake = prepare(value, tmp_path)
        assert "你确认过" in visible(value) and len(value.chat_input) == 1
        before = h.current(), h.memories(), h.history()
        enter_discovery(value, w)
        question = w.career_discovery.result.clarification_need.question
        assert question in visible(value) and "直接说" in visible(value)
        value.chat_input[0].set_value("都可以").run()
        assert not value.exception and fake.attempts == 1
        assert w.career_discovery.result.directions and w.agent_session.pending is None
        assert not w.chat.messages
        next(b for b in value.button if b.label == "继续探索这个方向").click().run()
        assert w.career_reality.current() and "公开虚构工作情境" in visible(value)
        assert before == (h.current(), h.memories(), h.history())
        value.button(key="orange_new_chat").click().run()
        assert not w.career_reality.messages and w.career_discovery.result is None
        assert value.button(key="orange_opening_discover") and "刚才的方向" not in visible(value)
    finally:
        w.close()


def test_pending_general_qa_interrupts_and_answer_returns_to_same_request(tmp_path):
    value = app(tmp_path, str(uuid4()))
    w = value.session_state[WORKSPACE_KEY]
    try:
        w, h, fake = prepare(value, tmp_path)
        enter_discovery(value, w)
        request = w.career_discovery.result.request_id
        qa = ScriptedProvider([plan(relevance="LEARNING_OR_TECHNICAL")], answer("Attention 用相关性权重聚合信息。"))
        w.agent_session.provider_factory = lambda: qa
        value.button(key="orange_agent_consent").click().run()
        value.chat_input[0].set_value("Transformer 的 attention 是什么？").run()
        assert not value.exception and "Attention 用相关性" in visible(value)
        assert w.career_discovery.pending_token() and w.career_discovery.result.request_id == request
        value.chat_input[0].set_value("都可以").run()
        assert not value.exception and w.career_discovery.result.directions
        assert fake.attempts == qa.structured_calls == qa.stream_calls == 1
        stored = w.store.list_messages(w.owner_scope_id, w.thread.thread_id)
        assert len(stored) == 2 and all(m.content != "都可以" for m in stored)
        w.agent_session.set_consent(granted=False)
    finally:
        w.close()


def test_no_profile_opening_direct_question_and_decline_never_gate_chat(tmp_path):
    value = app(tmp_path, str(uuid4()))
    w = value.session_state[WORKSPACE_KEY]
    try:
        assert "经历、想法" in visible(value) and value.button(key="orange_opening_self")
        qa = ScriptedProvider([plan(relevance="LEARNING_OR_TECHNICAL")], answer("位置编码提供顺序信息。"))
        w.agent_session.provider_factory = lambda: qa
        value.button(key="orange_opening_chat").click().run()
        assert len(value.chat_input) == 1 and not w.chat.messages
        value.button(key="orange_agent_consent").click().run()
        value.chat_input[0].set_value("Transformer 为什么需要 positional encoding？").run()
        assert not value.exception and "位置编码提供顺序信息" in visible(value)
        assert qa.structured_calls == qa.stream_calls == 1
        assert not w.memory_service.get_current_confirmed_profile(w.subject_id)
        w.agent_session.set_consent(granted=False)
    finally:
        w.close()


def test_opening_and_discovery_copy_avoid_internal_terms_or_rankings(tmp_path):
    value = app(tmp_path, str(uuid4()))
    w = value.session_state[WORKSPACE_KEY]
    try:
        text_a = visible(value)
        w, h, fake = prepare(value, tmp_path)
        text_b = visible(value)
        assert text_a != text_b
        for term in ("D.1", "D.2", "Confirmed Profile", "Memory consumer", "Fake provider", "canonical", "session-only", "最适合", "职业排名"):
            assert term not in text_a + text_b
        assert not value.text_area and len(value.chat_input) == 1
        assert fake.attempts == 0
    finally:
        w.close()
