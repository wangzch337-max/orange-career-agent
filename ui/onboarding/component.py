"""Local Streamlit v2 bridge; no domain data crosses this component boundary."""

from pathlib import Path
from uuid import uuid4
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
        default={"completed": False},
        on_completed_change=_mirror_completion,
        height=0,
    )
    st.session_state[COMPLETED_KEY] = bool(result.completed)
