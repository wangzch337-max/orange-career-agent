"""Small chat-native optional clarification; ordinary composer stays General QA."""

from html import escape

import streamlit as st

from clarification.context import binding_for, explicit_intent
from clarification.policy import ClarificationStatus as Status, TurnIntent

FAILURE_COPY = {
    Status.CLARIFICATION_CONTEXT_FAILED: "暂时无法安全整理澄清上下文。",
    Status.INVALID_CLARIFICATION_PLAN: "本次澄清结果没有通过校验，未创建问题或候选。",
    Status.INVALID_REFERENCE: "本次澄清的来源引用无效，未创建问题或候选。",
    Status.PROVIDER_FAILED: "本次澄清未完成，不会自动重试。",
    Status.STALE_CLARIFICATION_STATE: "相关简历或画像已变化，旧问题不再适用。",
    Status.ANSWER_NOT_APPLICABLE: "这条回答暂时不能应用到该问题。",
}


def render_clarification(workspace):
    """Return an explicit answer target only when user opts into that route."""
    analysis = workspace.resume_analysis
    if not analysis.has_consent or analysis.bundle is None:
        return None
    session = workspace.clarification
    disabled = workspace.agent_session.busy
    question = session.current_question()
    latest_user = next((m for m in reversed(workspace.chat.messages[-6:]) if m.role == "user"), None)
    text = latest_user.content if latest_user and explicit_intent(latest_user.content) else ""
    with st.container(key="orange_clarification"):
        if question:
            with st.chat_message("assistant"):
                st.write(question.decision.question)
                st.caption("可以自然回答、保持不确定，或暂时跳过；回答只作为临时候选。")
            for index, reply in enumerate(question.decision.suggested_replies):
                st.button(reply, key=f"orange_clarification_reply_{question.question_id}_{index}",
                    on_click=session.answer, args=(question, reply), disabled=disabled)
            st.button("暂时跳过这个问题", key="orange_clarification_dismiss",
                on_click=session.dismiss, args=(question,), disabled=disabled)
            selected = st.checkbox("将下一条消息作为这个问题的回答", value=False,
                key=f"orange_clarification_answer_{question.question_id}", disabled=disabled)
            st.caption("不勾选时，聊天仍按普通问答处理，不会把其他问题当作澄清答案。")
            return question if selected else None
        if session.status in FAILURE_COPY:
            st.warning(FAILURE_COPY[session.status])
            return None  # No implicit retry or repair action.
        if session.status == Status.ANSWER_RECORDED:
            candidate = session.state.answer_candidates[-1]
            with st.chat_message("user"):
                st.markdown(escape(candidate.user_answer).replace("\n", "<br>"), unsafe_allow_html=True)
            st.write("已作为本轮候选记录；尚未修改画像或长期记忆。")
        if session.status == Status.NO_CLARIFICATION_NEEDED:
            st.write("目前没有值得继续追问的问题，可以先保持现有理解。")
            if not session.can_run(current_statement=text):
                return None
        st.caption("如继续澄清，会向 Qwen 发送精简的简历候选、当前已确认画像摘要、相关历史记忆和近期对话。"
                   "此操作不确认或修改画像/记忆，也不推荐职业。")
        try:
            expected = binding_for(session._inputs(), session.state.version)
        except Exception:
            st.warning(FAILURE_COPY[Status.CLARIFICATION_CONTEXT_FAILED])
            return None
        # Only the latest explicit direction span is current intent; no assistant
        # inference or arbitrary old transcript becomes a current user fact.
        st.button("同意并继续澄清职业情况", key="orange_clarification_start", disabled=disabled,
            on_click=session.run, args=(TurnIntent.RESUME_REVIEW,),
            kwargs={"expected_binding": expected, "current_statement": text})
    return None
