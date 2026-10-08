"""D.6 transient messages and explicit scoped selection in the existing chat."""

from html import escape
import streamlit as st
from ui.onboarding.assets import sphere_markup


def render_validation_messages(workspace, offsets):
    session = workspace.evidence_validation
    for index, message in enumerate(session.messages):
        if message.offsets != offsets:
            continue
        with st.chat_message(message.role, avatar=sphere_markup() if message.role == "assistant" else None):
            st.markdown(escape(message.text).replace("\n", "<br>"), unsafe_allow_html=True)
            for number, target in enumerate(message.options, 1):
                st.text(f"{number}. {target.relation_id} · {target.relation_type.value} · {target.unresolved_scope}")
                st.button(f"验证第{number}项", key=f"d6_select_{session.generation}_{index}_{number}",
                    disabled=workspace.agent_session.busy or message.token != session.token(),
                    on_click=session.select, args=(message.token, target.relation_id))
