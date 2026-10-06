"""State-aware, non-blocking presentation over existing conversation entries."""

from dataclasses import dataclass
from enum import Enum
import streamlit as st

from data.models import ProfileStatus
from ui.onboarding.assets import sphere_markup


class OpeningState(str, Enum):
    NO_PROFILE = "NO_PROFILE"
    CONFIRMED_PROFILE = "CONFIRMED_PROFILE"


class OpeningAction(str, Enum):
    SELF = "SELF"
    DISCOVER = "DISCOVER"
    CHAT = "CHAT"


@dataclass(frozen=True)
class OpeningToken:
    owner: str
    thread: str
    profile_ref: tuple[str, int] | None


@dataclass(frozen=True)
class NewChatOpening:
    state: OpeningState
    token: OpeningToken
    text: str
    suggestions: tuple[tuple[OpeningAction, str], ...]


def build_opening(workspace):
    """Only canonical existence/version, never Memory retrieval or personal prose."""
    if workspace._closed:
        return None
    workspace.store.get_thread(workspace.owner_scope_id, workspace.thread.thread_id)
    profile = workspace.memory_service.get_current_confirmed_profile(workspace.subject_id)
    confirmed = profile is not None and profile.confirmed and profile.status == ProfileStatus.CONFIRMED
    token = OpeningToken(workspace.owner_scope_id, workspace.thread.thread_id,
                         (profile.profile_id, profile.version) if confirmed else None)
    if confirmed:
        return NewChatOpening(OpeningState.CONFIRMED_PROFILE, token,
            "我已经有一版你确认过的职业画像了。\n\n"
            "如果你愿意，我们可以往前走一步，看看哪些职业方向值得继续了解。"
            "也可以直接聊别的问题，不必现在做职业决定。",
            ((OpeningAction.DISCOVER, "看看职业方向"), (OpeningAction.CHAT, "先聊别的")))
    return NewChatOpening(OpeningState.NO_PROFILE, token,
        "嗨，我是 Orange。\n\n我们可以先聊聊你现在的经历、想法和对工作的期待。"
        "不用现在就确定一个职业方向；你也可以直接问我任何问题。",
        ((OpeningAction.SELF, "先聊聊我自己"), (OpeningAction.CHAT, "我先问个问题")))


def opening_action(workspace, token, action, *, discovery_consent=False):
    """Closed, current actions reuse existing entries; clicks never grant consent."""
    if (workspace._closed or workspace.agent_session.busy or workspace.career_discovery.busy or
            workspace.chat.messages or workspace.career_discovery.result is not None or
            workspace.career_discovery.status.value == "CONSENT_REQUIRED" or
            getattr(workspace, "opening_dismissed_thread", None) == token.thread):
        return False
    try:
        opening = build_opening(workspace)
    except ValueError:
        return False
    if opening is None or token != opening.token or action not in {a for a, _ in opening.suggestions}:
        return False
    if action == OpeningAction.DISCOVER:
        workspace.career_discovery.start(explicitly_requested=True, consent=discovery_consent,
            current_statement="", expected_owner_scope_id=token.owner, expected_conversation_id=token.thread)
    elif action == OpeningAction.SELF:
        # Reuse the original main-chat self-discovery entry, not a parallel
        # profile builder or an implicit C.3/resume data-sharing permission.
        from ui.conversation_shell import INITIAL_SUGGESTIONS, _submit
        _submit(workspace, INITIAL_SUGGESTIONS[0], token.thread, suggested=True)
    else:
        workspace.opening_dismissed_thread = token.thread
    return True


def render_opening(workspace):
    if getattr(workspace, "opening_dismissed_thread", None) == workspace.thread.thread_id:
        return
    opening = build_opening(workspace)
    if opening is None:
        return
    with st.chat_message("assistant", avatar=sphere_markup()):
        st.write(opening.text)
        with st.container(horizontal=True, wrap=True):
            for action, label in opening.suggestions:
                st.button(label, key="orange_opening_" + action.value.lower(),
                    on_click=opening_action, args=(workspace, opening.token, action),
                    kwargs={"discovery_consent": bool(st.session_state.get(
                        "orange_discovery_consent_" + workspace.thread.thread_id, False))})
