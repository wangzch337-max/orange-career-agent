"""D.4 projects validated source facts in the existing single-input transcript."""

from html import escape
import streamlit as st
from specific_role.service import NOTICE, CHIPS
from ui.career_reality import AUTHORITY
from ui.onboarding.assets import sphere_markup


def render_specific_messages(workspace, anchor, reality_offset, landscape_offset):
    session = workspace.specific_role
    session.current()
    for message in session.messages:
        if (message.anchor, message.reality_offset, message.landscape_offset) != (anchor, reality_offset, landscape_offset):
            continue
        with st.chat_message(message.role, avatar=sphere_markup() if message.role == "assistant" else None):
            if message.text:
                st.markdown(escape(message.text).replace("\n", "<br>"), unsafe_allow_html=True)
            if message.reply is not None and message.source is not None:
                reply, source = message.reply, message.source
                # Keep the historical source with the message when another role
                # is explored; never relabel prior facts as the new selection.
                session.service.validate(reply, source)
                st.caption(NOTICE)
                st.markdown("**" + source.display_name + "**")
                for block in reply.blocks:
                    st.caption(AUTHORITY[block.authority])
                    st.text(block.text)
                with st.expander("这段代表性角色理解的来源"):
                    st.text(source.scope)
                    for name in ("display_name", "scope"):
                        st.caption(f"{source.source_id}@{source.version}:{source.representative_role_id}:{name}:0")
                    st.caption(f"独立公开合成 / curated · v{reply.source_version}")
                    st.text(source.membership.direction_archetype_evidence)
                    st.text(source.membership.archetype_role_evidence)
                    st.caption("来源指纹：" + reply.source_fingerprint)
                    for block in reply.blocks:
                        st.caption(block.source_ref)
                        for ref in block.membership_refs:
                            st.caption(ref)


def render_specific_chips(workspace):
    session = workspace.specific_role
    if session.current() and not workspace.agent_session.busy:
        token = session.token()
        with st.container(horizontal=True, wrap=True):
            for index, text in enumerate(CHIPS):
                st.button(text, key=f"orange_specific_chip_{token.request_id}_{index}",
                          on_click=session.submit, args=(text,), kwargs={"token": token})
