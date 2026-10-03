"""One quiet later-entry boot presentation; no workflow / Memory authority."""

from time import sleep

import streamlit as st

from ui.chat_components import orange_mark
from ui.onboarding import render_onboarding
from ui.onboarding.component import COMPLETED_KEY


BOOT_DONE_KEY = "orange_boot_loader_done_v1"
ENTRY_SEEN_KEY = "orange_intro_entry_seen_v1"
LOADER_SECONDS = .85


def loader_html() -> str:
    return """<style>
    .orange-boot {position:fixed; inset:0; z-index:999990; background:var(--oc-bg,#fff);
      display:flex; flex-direction:column; align-items:center; justify-content:center;
      gap:1.5rem; animation:orange-boot-fade 850ms ease both;}
    .orange-boot .orange-chat-mark {position:relative; display:block; width:96px; height:96px;
      animation:orange-boot-bounce 650ms cubic-bezier(.22,.61,.36,1) 1;}
    .orange-boot .orange-chat-mark>svg {display:block; width:100%; height:100%;}
    .orange-boot .orange-chat-leaf {position:absolute; left:53%; top:24%; width:26%; opacity:.94;}
    .orange-boot .orange-chat-leaf svg {width:100%; height:auto;}
    .orange-boot p {margin:0; color:var(--oc-text-secondary,#596574); font-size:.95rem;}
    @keyframes orange-boot-bounce {
      0%,100% {transform:translateY(0) scale(1);}
      18% {transform:translateY(2px) scale(1.025,.975);}
      48% {transform:translateY(-12px) scale(.99,1.01);}
      76% {transform:translateY(2px) scale(1.01,.99);}
    }
    @keyframes orange-boot-fade {0% {opacity:0;} 15%,80% {opacity:1;} 100% {opacity:0;}}
    @media (prefers-reduced-motion:reduce) {
      .orange-boot, .orange-boot .orange-chat-mark {animation:none;}
    }
    </style>""" + '<div class="orange-boot" role="status" aria-live="polite">' + orange_mark() + '<p>正在加载中</p></div>'


def render_boot() -> None:
    """Browser reports entry kind once; Streamlit holds only this session's latch."""
    render_onboarding()
    if st.session_state.get(BOOT_DONE_KEY):
        return
    if not st.session_state.get(COMPLETED_KEY) or ENTRY_SEEN_KEY not in st.session_state:
        return
    # The first intro is the boot; never follow it with a second animation.
    if st.session_state[ENTRY_SEEN_KEY]:
        overlay = st.empty()
        overlay.markdown(loader_html(), unsafe_allow_html=True)
        sleep(LOADER_SECONDS)
        overlay.empty()
    st.session_state[BOOT_DONE_KEY] = True
