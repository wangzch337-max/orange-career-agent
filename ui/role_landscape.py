"""D.3 stays in the main transcript, with progressive source disclosure."""

from html import escape
import streamlit as st
from role_landscape.service import NOTICE, CHIPS
from ui.onboarding.assets import sphere_markup


def render_role_messages(workspace, anchor, reality_offset):
    session = workspace.role_landscape
    for message in session.messages:
        if (message.anchor, message.reality_offset) != (anchor, reality_offset):
            continue
        with st.chat_message(message.role, avatar=sphere_markup() if message.role == "assistant" else None):
            if message.text:
                st.markdown(escape(message.text).replace("\n", "<br>"), unsafe_allow_html=True)
            if message.reply is not None and session.source is not None:
                reply, source = message.reply, session.source
                st.caption(NOTICE)
                for role_id in reply.role_ids:
                    role = next(r for r in source.roles if r.role_id == role_id)
                    index = session.binding.displayed_role_ids.index(role_id) + 1
                    st.markdown(f"**{index}. {role.display_name}**")
                    for block in reply.blocks:
                        if block.role_id == role_id:
                            st.text(block.text)
                with st.expander("这段角色理解的来源"):
                    st.text(source.display_name)
                    st.caption(f"公开合成 / curated · v{reply.source_version} · 仅在此资料中成立")
                    for role_id in reply.role_ids:
                        membership = next(m for m in source.memberships if m.role_id == role_id)
                        st.text(membership.evidence)
                    for block in reply.blocks:
                        st.caption(block.membership_ref)
                        st.caption(block.source_ref)


def render_role_chips(workspace):
    session = workspace.role_landscape
    if session.current() and not workspace.agent_session.busy:
        token = session.token()
        with st.container(horizontal=True, wrap=True):
            for index, text in enumerate(CHIPS):
                st.button(text, key=f"orange_landscape_chip_{token.request_id}_{index}",
                          on_click=session.submit, args=(text,), kwargs={"token": token})
