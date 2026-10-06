"""Opening state is presentation, never authority or a provider permission."""

from uuid import uuid4
import pytest

from ui.chat_runtime import Workspace
from ui.chat_opening import build_opening, opening_action, OpeningAction, OpeningState
from tests.career_discovery_doubles import prepared


def test_no_profile_opening_is_non_blocking_and_self_action_reuses_chat(tmp_path, monkeypatch):
    with Workspace(str(uuid4()), tmp_path) as w:
        monkeypatch.setattr(w.memory_service, "retrieve_context", lambda **k: pytest.fail("No Memory"))
        opening = build_opening(w)
        assert opening.state == OpeningState.NO_PROFILE
        assert {a for a, _ in opening.suggestions} == {OpeningAction.SELF, OpeningAction.CHAT}
        assert opening_action(w, opening.token, OpeningAction.SELF)
        assert w.chat.messages and w.controller.conversation.stage.value != "career_question"
        assert not w.memory_service.get_current_confirmed_profile(w.subject_id)


def test_confirmed_profile_opening_reaches_existing_discovery_consent_gate(tmp_path, monkeypatch):
    h = prepared(tmp_path)
    try:
        w = h.workspace
        w.create_new_thread()
        before = h.current(), h.memories(), h.history()
        consent_before = w.agent_session.consent
        monkeypatch.setattr(w.memory_service, "retrieve_context", lambda **k: pytest.fail("Opening adds no retrieval"))
        opening = build_opening(w)
        assert opening.state == OpeningState.CONFIRMED_PROFILE
        assert "你确认过" in opening.text and "先聊聊你现在" not in opening.text
        assert opening_action(w, opening.token, OpeningAction.DISCOVER)
        assert w.career_discovery.status.value == "CONSENT_REQUIRED"
        assert w.agent_session.consent == consent_before and not w.career_discovery.result
        assert not opening_action(w, opening.token, OpeningAction.DISCOVER)
        assert before == (h.current(), h.memories(), h.history())
    finally:
        h.close()


@pytest.mark.parametrize("change", ["decline", "chat"])
def test_old_opening_action_cannot_reenter_after_opening_ends(tmp_path, change):
    with Workspace(str(uuid4()), tmp_path) as w:
        opening = build_opening(w)
        if change == "decline":
            assert opening_action(w, opening.token, OpeningAction.CHAT)
        else:
            w.submit("公共合成普通消息")
        before = list(w.chat.messages)
        assert not opening_action(w, opening.token, OpeningAction.SELF)
        assert w.chat.messages == before


@pytest.mark.parametrize("change", ["new_thread", "owner", "profile"])
def test_stale_opening_action_is_owner_thread_profile_bound(tmp_path, change):
    h = prepared(tmp_path)
    try:
        w = h.workspace
        token = build_opening(w).token
        if change == "new_thread": w.create_new_thread()
        elif change == "owner": w.owner_scope_id = str(uuid4())
        elif change == "profile":
            get = w.memory_service.get_current_confirmed_profile
            w.memory_service.get_current_confirmed_profile = lambda subject: get(subject).model_copy(update={"version": 999})
        try:
            handled = opening_action(w, token, OpeningAction.DISCOVER)
        except ValueError:
            handled = False
        assert not handled and not w.career_discovery.result
    finally:
        h.close()
