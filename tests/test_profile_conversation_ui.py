"""Main-timeline, single-composer and explicit whole-profile review contracts."""

from dataclasses import asdict
import json
from uuid import uuid4

import pytest

from career_runtime.profile_conversation import InterviewStage as Stage
from tests.agent_doubles import ScriptedProvider, plan, answer
from tests.test_chat_product import app, WORKSPACE_KEY
from tests.test_profile_conversation import prepare
from tests.test_resume_evidence_ui import visible_text


@pytest.fixture(autouse=True)
def no_credentials(monkeypatch):
    monkeypatch.setattr("providers.models.load_llm_settings", lambda *a: pytest.fail("No local settings"))
    monkeypatch.setattr("resume_evidence.session._qwen_provider", lambda: pytest.fail("No live Qwen"))


def start_ui(tmp_path, background="audit"):
    value = app(tmp_path, str(uuid4()))
    w = value.session_state[WORKSPACE_KEY]
    selector, refiner = prepare(w, background)
    value.run()
    return value, w, selector, refiner


def test_resume_question_answer_automatic_review_and_confirmation_are_one_ephemeral_timeline(tmp_path):
    value, w, selector, refiner = start_ui(tmp_path)
    try:
        text = visible_text(value)
        assert "Orange 从简历中整理出的职业证据" in text
        assert value.button(key="orange_clarification_start").label == "继续完善我的职业画像"
        assert "Qwen" in text and "只有你确认后才会保存职业画像" in text
        for old in ("同意并继续澄清职业情况", "本轮画像补充", "同意并整理画像变更草案", "INVALID_DRAFT"):
            assert old not in text
        assert not value.text_area and not [x for x in value.text_input if x.key.startswith("orange_profile_")]
        assert len(value.chat_input) == 1 and not w.agent_session.consent
        value.button(key="orange_clarification_start").click().run()
        question = w.clarification.current_question()
        assert question and selector.call_count == 1 and refiner.call_count == 0
        assert any(question.decision.question in " ".join(e.value for e in m.text) for m in value.chat_message if m.name == "assistant")
        assert not [x for x in value.checkbox if x.key and x.key.startswith("orange_clarification_answer_")]
        user_text = "我想探索数据分析和业务分析，但暂时不确定是否完全离开审计。"
        value.chat_input[0].set_value(user_text).run()
        assert not value.exception and w.profile_conversation.stage == Stage.REVIEW
        assert any(user_text == e.value for m in value.chat_message if m.name == "user" for e in m.markdown)
        assert "我的职业画像" in visible_text(value) and "只有你确认后" in visible_text(value)
        assert "Audit Associate" in visible_text(value) and "仍不确定" in visible_text(value)
        assert not w.memory_service.get_current_confirmed_profile(w.subject_id)
        assert not w.store.list_messages(w.owner_scope_id, w.thread.thread_id)
        assert not w.memory_service.memory_store.list_active(w.subject_id)
        assert not value.button(key="orange_profile_confirm").disabled
        for secret in (w.resume_analysis.bundle.source_id, w.owner_scope_id, question.question_id,
                       w.profile_refinement.draft.draft_id, "resume_evidence_001", "source_quotes", "INVALID_DRAFT"):
            assert secret not in visible_text(value)
        value.run()
        assert selector.call_count == refiner.call_count == 1
        value.button(key="orange_profile_confirm").click().run()
        assert not value.exception and w.profile_conversation.stage == Stage.CONFIRMED
        final = w.memory_service.get_current_confirmed_profile(w.subject_id)
        assert final and final.work_experience and not final.projects and final.uncertainties
        # D.2 approval makes the existing D.1 downstream entry available after
        # confirmation; it does not add a second Profile/D.2 questionnaire.
        assert value.button(key="orange_discovery_start").disabled
        assert not [x for x in value.text_input if x.key and x.key.startswith("orange_profile_")]
        assert not w.memory_service.memory_store.list_active(w.subject_id)
        assert selector.call_count == refiner.call_count == 1
    finally:
        w.close()


@pytest.mark.parametrize("action", ["orange_profile_edit", "orange_profile_continue"])
def test_modify_and_continue_keep_composer_available_without_confirming_or_writing(tmp_path, action):
    value, w, selector, refiner = start_ui(tmp_path)
    try:
        value.button(key="orange_clarification_start").click().run()
        value.chat_input[0].set_value("我还不确定").run()
        value.button(key=action).click().run()
        assert not value.exception and len(value.chat_input) == 1
        assert w.profile_refinement.draft is None
        assert w.profile_conversation.stage in {Stage.EDITING, Stage.SUPPLEMENT}
        assert not w.memory_service.get_current_confirmed_profile(w.subject_id)
        assert not w.memory_service.memory_store.list_active(w.subject_id)
        assert selector.call_count == refiner.call_count == 1
        value.chat_input[0].set_value("我希望探索运营管理，也想保留原有领域的选择。").run()
        assert not value.exception and w.profile_conversation.stage == Stage.REVIEW
        assert refiner.call_count == 2 and not w.memory_service.get_current_confirmed_profile(w.subject_id)
        assert not value.text_area and not [x for x in value.text_input if x.key.startswith("orange_profile_")]
    finally:
        w.close()


def test_general_qa_uses_existing_consented_runtime_and_interview_recovers_afterwards(tmp_path):
    value, w, selector, refiner = start_ui(tmp_path)
    try:
        value.button(key="orange_clarification_start").click().run()
        question = w.clarification.current_question()
        qa = ScriptedProvider([plan()], answer("业务分析师会梳理业务需求，分析流程，并帮助团队理解需要改善的问题。"))
        w.agent_session.provider_factory = lambda: qa
        value.button(key="orange_agent_consent").click().run()
        value.chat_input[0].set_value("业务分析师主要做什么？").run()
        assert not value.exception and "业务分析师会梳理业务需求" in visible_text(value)
        assert qa.structured_calls == qa.stream_calls == 1
        assert w.clarification.current_question() == question and not w.clarification.state.answer_candidates
        assert selector.call_count == 1 and refiner.call_count == 0
        assert len(w.store.list_messages(w.owner_scope_id, w.thread.thread_id)) == 2
        value.chat_input[0].set_value("我还不确定").run()
        assert not value.exception and w.profile_conversation.stage == Stage.REVIEW
        assert len(w.store.list_messages(w.owner_scope_id, w.thread.thread_id)) == 2
        assert qa.structured_calls == qa.stream_calls == 1 and refiner.call_count == 1
        messages = [m for m in value.chat_message]
        qa_index = next(i for i, m in enumerate(messages) if any("业务分析师会梳理业务需求" in e.value for e in m.markdown))
        answer_index = next(i for i, m in enumerate(messages) if m.name == "user" and any(e.value == "我还不确定" for e in m.markdown))
        assert qa_index < answer_index
    finally:
        w.close()


@pytest.mark.parametrize("mode", ["跟随系统", "浅色模式", "深色模式"])
def test_theme_rerenders_do_not_call_providers_or_lose_active_question(tmp_path, mode):
    value, w, selector, refiner = start_ui(tmp_path, "switcher")
    try:
        value.button(key="orange_clarification_start").click().run()
        q = w.clarification.current_question()
        value.radio(key="orange_appearance").set_value(mode).run()
        value.run()
        assert not value.exception and w.clarification.current_question() == q
        assert selector.call_count == 1 and refiner.call_count == 0 and len(value.chat_input) == 1
        assert "Orange Career" in visible_text(value) and "orange-demo-tag" in visible_text(value)
        assert "Operations Supervisor" in visible_text(value)
    finally:
        w.close()


def test_invalid_draft_is_not_exposed_and_refresh_does_not_replay(tmp_path):
    value, w, selector, refiner = start_ui(tmp_path)
    try:
        refiner.plan = lambda payload: {"outcome": "CHANGES", "changes": []}
        value.button(key="orange_clarification_start").click().run()
        value.chat_input[0].set_value("我还不确定").run()
        assert not value.exception and w.profile_conversation.stage == Stage.FAILED
        text = visible_text(value)
        assert "这次整理没有成功" in text and "暂时还在本次会话" in text
        for code in ("INVALID_DRAFT", "PROVIDER_FAILED", "INVALID_STRUCTURED_OUTPUT", "状态："):
            assert code not in text
        assert any(e.error_category == "INVALID_DRAFT" for e in w.profile_conversation.events)
        value.run()
        assert selector.call_count == refiner.call_count == 1
        assert not w.memory_service.get_current_confirmed_profile(w.subject_id)
        assert not w.store.list_messages(w.owner_scope_id, w.thread.thread_id)
        assert "我还不确定" not in json.dumps([asdict(e) for e in w.profile_conversation.events])
    finally:
        w.close()
