"""Actual chat-native UI, no new page, live model or automatic persistence."""

from uuid import uuid4
import pytest

from career_background_evaluation.harness import CareerHarness, CapturingFake
from career_background_evaluation.scenarios import SCENARIOS
from tests.career_discovery_doubles import proposal_from_payload
from tests.test_chat_product import app, WORKSPACE_KEY


def prepare(w, root):
    harness = CareerHarness(root, SCENARIOS[3], workspace=w)
    harness.prepare(); harness.resolve_all(); harness.confirm(memory=True)
    w.agent_session.set_consent(granted=False)
    provider = CapturingFake(proposal_from_payload)
    w.career_discovery.provider_factory = lambda: provider
    return harness, provider


def test_chat_native_start_cards_selection_refresh_and_no_automatic_call(tmp_path, monkeypatch):
    monkeypatch.setattr("providers.models.load_llm_settings", lambda *a: pytest.fail("loaded local credentials"))
    value = app(tmp_path, str(uuid4()))
    w = value.session_state[WORKSPACE_KEY]
    try:
        h, provider = prepare(w, tmp_path)
        old, memories = h.current(), h.memories()
        value.run()
        assert provider.attempts == 0 and value.button(key="orange_discovery_start").disabled
        value.text_input(key="orange_discovery_statement_" + w.thread.thread_id).set_value("探索相邻方向").run()
        value.checkbox(key="orange_discovery_consent_" + w.thread.thread_id).check().run()
        assert provider.attempts == 0
        value.button(key="orange_discovery_start").click().run()
        assert not value.exception and provider.attempts == 1
        text = "\n".join(str(e.value) for e in [*value.markdown, *value.caption] if not str(e.value).startswith("<style>"))
        for label in ("顺序不代表排名。", "可迁移能力（待验证解释）", "迁移考量（不是确认缺口）", "不确定项 / 需要补充的证据"):
            assert label in text
        for forbidden in ("匹配分", "成功率", "#1", "最适合", "salary", "job_ids"):
            assert forbidden not in text
        buttons = [b for b in value.button if b.label == "继续探索这个方向"]
        assert len(buttons) == 3 and len(value.chat_input) == 1
        buttons[0].click().run()
        assert w.career_discovery.selected_direction_id and h.current() == old and h.memories() == memories
        assert not w.chat.messages and provider.attempts == 1
        value.run()
        assert provider.attempts == 1
        value.button(key="orange_new_chat").click().run()
        assert not value.exception and w.career_discovery.result is None
        assert h.current() == old and h.memories() == memories
    finally:
        w.close()


def test_general_qa_ui_never_loads_discovery_inputs(tmp_path, monkeypatch):
    value = app(tmp_path, str(uuid4()))
    w = value.session_state[WORKSPACE_KEY]
    try:
        monkeypatch.setattr(w.career_discovery, "input_factory", lambda **k: pytest.fail("QA loaded discovery inputs"))
        value.chat_input[0].set_value("Python generator 是什么？").run()
        assert not value.exception and w.career_discovery.result is None
        assert w.chat.messages[0].content == "Python generator 是什么？"
        assert value.button(key="orange_discovery_start").disabled
    finally:
        w.close()


def test_unknown_goal_ui_one_question_and_no_direction(tmp_path):
    value = app(tmp_path, str(uuid4()))
    w = value.session_state[WORKSPACE_KEY]
    try:
        h, provider = prepare(w, tmp_path)
        value.run()
        value.text_input(key="orange_discovery_statement_" + w.thread.thread_id).set_value("我没有明确的职业方向，不知道方向").run()
        value.checkbox(key="orange_discovery_consent_" + w.thread.thread_id).check().run()
        value.button(key="orange_discovery_start").click().run()
        assert not value.exception and provider.attempts == 0
        assert not [b for b in value.button if b.label == "继续探索这个方向"]
        question = w.career_discovery.result.clarification_need.question
        assert question in [m.value for m in value.markdown]
    finally:
        w.close()


def test_default_discovery_is_offline_safe_failure(tmp_path):
    value = app(tmp_path, str(uuid4()))
    w = value.session_state[WORKSPACE_KEY]
    try:
        prepare(w, tmp_path)
        from providers.fake import FakeLLMProvider
        w.career_discovery.provider_factory = lambda: FakeLLMProvider(None)
        value.run()
        value.text_input(key="orange_discovery_statement_" + w.thread.thread_id).set_value("探索相邻方向").run()
        value.checkbox(key="orange_discovery_consent_" + w.thread.thread_id).check().run()
        value.button(key="orange_discovery_start").click().run()
        assert not value.exception and w.career_discovery.result is None
        assert any("未自动重试" in warning.value for warning in value.warning)
    finally:
        w.close()
