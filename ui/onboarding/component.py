"""Local Streamlit v2 bridge; no domain data crosses this component boundary."""

from pathlib import Path
from uuid import UUID, uuid4
from weakref import WeakKeyDictionary

import streamlit as st
from streamlit.components.v2 import component
from streamlit.runtime import Runtime

from ui.onboarding.assets import leaf_markup, sphere_markup


FRONTEND = Path(__file__).parent / "frontend"
MESSAGES = (
    "你好。",
    "我叫 Orange。",
    "我是你的 AI 职业探索伙伴。",
    "我会先了解你，再陪你一起理解岗位、发现值得继续探索的方向。",
    "你不需要现在就知道所有答案。",
    "准备好了吗？让我们开始吧。",
)
COMPONENT_KEY = "orange_intro_component"
COMPLETED_KEY = "orange_intro_completed"
REPLAY_KEY = "orange_intro_replay_request"
SESSION_KEY = "orange_intro_presentation_session"
CLIENT_SCOPE_KEY = "orange_client_scope_v1"

_renderers = WeakKeyDictionary()


def _renderer():
    """Register once per runtime/assets version, including isolated AppTest runtimes."""
    runtime = Runtime.instance()
    # Register on every rerun, including cache hits, to retain the session's
    # local media reference. Streamlit serves these public bytes on this origin.
    video_url = runtime.media_file_mgr.add(
        str(FRONTEND / "assets/orange_thinking.mp4"), "video/mp4", "orange_intro_video"
    )
    assets = (
        (FRONTEND / "index.html").read_text(encoding="utf-8").replace(
            "<!-- SPHERE -->", sphere_markup()
        ).replace("<!-- LEAF -->", leaf_markup()).replace("__THINKING_VIDEO__", video_url),
        (FRONTEND / "onboarding.css").read_text(encoding="utf-8"),
        (FRONTEND / "onboarding.js").read_text(encoding="utf-8"),
    )
    cached = _renderers.get(runtime)
    if cached is None or cached[0] != assets:
        # Local trusted assets, never interpolated user data; no build step.
        renderer = component(
            "orange_first_visit_v1", html=assets[0], css=assets[1], js=assets[2], isolate_styles=True
        )
        _renderers[runtime] = (assets, renderer)
    return _renderers[runtime][1]


def request_replay() -> None:
    """Request only an intro replay; never touch controller or workflow state."""
    st.session_state[REPLAY_KEY] = uuid4().hex
    st.session_state[COMPLETED_KEY] = False
    st.session_state[COMPONENT_KEY] = {"completed": False}


def _mirror_completion() -> None:
    """Consume a replay command only after the browser actually finishes it."""
    if st.session_state.get(COMPONENT_KEY, {}).get("completed") is True:
        st.session_state[COMPLETED_KEY] = True
        st.session_state.pop(REPLAY_KEY, None)


def _mirror_entry() -> None:
    """Remember the browser's entry flag, not the flag after this intro finishes."""
    seen = st.session_state.get(COMPONENT_KEY, {}).get("entry_seen")
    if isinstance(seen, bool):
        st.session_state.setdefault("orange_intro_entry_seen_v1", seen)


def _mirror_client_scope() -> None:
    """Accept only an opaque UUID; this local demo scope is not authentication."""
    value = st.session_state.get(COMPONENT_KEY, {}).get("client_scope")
    try:
        parsed = UUID(value) if isinstance(value, str) else None
    except ValueError:
        return
    if parsed is not None and parsed.version == 4:
        st.session_state.setdefault(CLIENT_SCOPE_KEY, str(parsed))


def render_onboarding() -> None:
    """Mount one stable component and mirror its completion for presentation only."""
    st.session_state.setdefault(SESSION_KEY, uuid4().hex)
    result = _renderer()(
        key=COMPONENT_KEY,
        data={
            "messages": MESSAGES,
            "replay_token": st.session_state.get(REPLAY_KEY),
            "completed": bool(st.session_state.get(COMPLETED_KEY, False)),
            "presentation_session": st.session_state[SESSION_KEY],
        },
        default={"completed": False, "entry_seen": None, "client_scope": None},
        on_completed_change=_mirror_completion,
        on_entry_seen_change=_mirror_entry,
        on_client_scope_change=_mirror_client_scope,
        height=0,
    )
    st.session_state[COMPLETED_KEY] = bool(result.completed)
    if result.entry_seen is not None:
        st.session_state.setdefault("orange_intro_entry_seen_v1", bool(result.entry_seen))
    if result.client_scope is not None:
        _mirror_client_scope()
