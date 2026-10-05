"""Functional real Streamlit shell upload → review → restart, Fake only."""

from uuid import uuid4

import pytest

from career_background_evaluation.harness import CareerHarness
from career_background_evaluation.scenarios import SCENARIOS
from profile_refinement.models import Resolution
from tests.test_chat_product import app, WORKSPACE_KEY


@pytest.mark.parametrize("theme", ["浅色模式", "深色模式"])
def test_product_shell_true_synthetic_e2e_with_explicit_edit_and_uncertainty(tmp_path, monkeypatch, theme):
    monkeypatch.setattr("resume_evidence.session._qwen_provider", lambda: (_ for _ in ()).throw(AssertionError("No Qwen")))
    scope = str(uuid4())
    value = app(tmp_path, scope)
    w = value.session_state[WORKSPACE_KEY]
    h = CareerHarness(tmp_path, SCENARIOS[3], workspace=w)
    try:
        labels = []
        import ui.resume_upload as upload
        native = upload.st.status
        def reading(label, **kwargs):
            labels.append(label)
            return native(label, **kwargs)
        monkeypatch.setattr(upload.st, "status", reading)
        value.radio(key="orange_appearance").set_value(theme).run()
        assert {element.proto.popover.label for element in value.get("popover")} == {"＋", "···"}
        value.file_uploader[0].upload("public-synthetic.docx", h.raw_bytes).run()
        h.raw_text = "\n".join(b.text for b in w.resume_intake.result.document.blocks)
        assert labels and any(t.value == "public-synthetic.docx" for t in value.text)
        assert not value.exception and value.file_uploader[0].value is None
        assert not w.resume_analysis.has_consent and all(p.attempts == 0 for p in h.providers)
        value.button(key="orange_resume_ai_consent").click().run()
        value.button(key="orange_resume_ai_analyze").click().run()
        assert not value.exception and w.resume_analysis.bundle and h.extraction.attempts == 1
        value.button(key="orange_clarification_start").click().run()
        q = w.clarification.current_question()
        assert q and h.clarifier.attempts == 1
        value.chat_input[0].set_value(h.scenario.answer).run()
        h.answer_text = h.scenario.answer
        assert not value.exception and len(w.clarification.state.answer_candidates) == 1
        s = w.profile_refinement
        assert not value.exception and s.draft and h.refiner.attempts == 1
        assert not value.button(key="orange_profile_confirm").disabled
        goal = next(ch for ch in s.draft.changes if ch.category == "goals")
        # Keep/reject is a real supported control; reconsidering it stays local.
        value.button(key="orange_profile_keep_" + goal.change_id).click().run()
        assert next(ch for ch in s.draft.changes if ch.category == "goals").user_resolution == Resolution.REJECT
        value.button(key="orange_profile_edit").click().run()
        original = h.refiner.program
        edited_label = h.scenario.goal_label + "（由用户确认保留探索状态）"
        def edited_program(payload):
            output = original(payload)
            for change in output["changes"]:
                if change["category"] == "goals":
                    change["proposed_value"]["label"] = edited_label
                    change["uncertainty"] = "explicit_uncertainty"
            return output
        h.refiner.program = edited_program
        value.chat_input[0].set_value("我想补充：" + edited_label + "，目前还不确定。").run()
        assert not value.exception and not h.current() and not h.memories()
        value.button(key="orange_profile_confirm").click().run()
        assert not value.exception
        final = h.current()
        assert final and final.version == 1 and final.work_experience and not final.projects
        assert any("由你确认" in item.value for item in value.text)
        h.universal_checks(final); h.privacy_checks(final)
        counts = [p.attempts for p in h.providers]
        value.run()
        assert [p.attempts for p in h.providers] == counts == [1, 1, 2]
        assert not w.chat.messages and not w.store.list_messages(w.owner_scope_id, w.thread.thread_id)
        value.button(key="orange_new_chat").click().run()
        assert not value.exception and w.resume_intake.result is None and s.draft is None
        assert w.thread.profile_id_ref == final.profile_id
    finally:
        h.close()
    refreshed = app(tmp_path, scope)
    try:
        restored = refreshed.session_state[WORKSPACE_KEY]
        assert not refreshed.exception and restored.memory_service.get_current_confirmed_profile(restored.subject_id) == final
        assert restored.memory_service.profile_store.list_profile_history(restored.subject_id) == [final]
        assert restored.resume_intake.result is None and restored.profile_refinement.draft is None
        assert not restored.memory_service.memory_store.list_active(restored.subject_id)
    finally:
        refreshed.session_state[WORKSPACE_KEY].close()
