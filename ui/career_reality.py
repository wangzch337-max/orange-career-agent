"""Read-only work-context presentation interleaved with the main transcript."""

from html import escape
import streamlit as st
from career_reality.models import Authority
from career_reality.service import CHIPS
from ui.onboarding.assets import sphere_markup

AUTHORITY = {
    Authority.SOURCE_FACT: "合成资料支持的内容", Authority.OBSERVATION: "来源观察",
    Authority.EXPLANATION: "派生解释", Authority.EXAMPLE: "代表性示例",
    Authority.UNKNOWN: "尚未说明", Authority.SUGGESTION: "可选探索建议",
}


def render_reality_messages(workspace, anchor):
    session = workspace.career_reality
    session.current()
    from ui.role_landscape import render_role_messages, render_role_chips
    for offset, message in enumerate(session.messages):
        render_role_messages(workspace, anchor, offset)
        if message.anchor != anchor:
            continue
        with st.chat_message(message.role, avatar=sphere_markup() if message.role == "assistant" else None):
            if message.text:
                st.markdown(escape(message.text).replace("\n", "<br>"), unsafe_allow_html=True)
            if message.reply is not None and session.source is not None:
                st.caption("公开虚构工作情境 · 不是招聘数据，也不代表这个方向的所有工作。")
                for block in message.reply.blocks:
                    st.caption(AUTHORITY[block.authority])
                    st.text(block.text)
                with st.expander("这段工作理解的来源"):
                    st.text(session.source.display_name)
                    st.caption("独立编写的公开合成演示资料 · 版本 " + str(message.reply.source_version))
                    for block in message.reply.blocks:
                        st.caption(block.source_ref)
    render_role_messages(workspace, anchor, len(session.messages))
    if anchor == len(workspace.chat.messages):
        render_role_chips(workspace)
    if anchor == len(workspace.chat.messages) and session.current() and not workspace.agent_session.busy:
        token = session.token()
        with st.container(horizontal=True, wrap=True):
            for index, text in enumerate(CHIPS):
                st.button(text, key=f"orange_reality_chip_{token.request_id}_{index}",
                    on_click=session.submit, args=(text,), kwargs={"token": token})
