"""Small presentation adapter: executes no model policy or canonical mutations."""

from html import escape

import streamlit as st
from memory.errors import MemoryLayerError

from career_runtime.models import ACTIVITY_LABELS, Activity


def render_activity(items, *, key):
    if not items:
        return
    with st.container(key="orange_agent_activity_" + key), st.expander("Orange 的处理进度", expanded=False):
        latest = {}
        for item in items:
            activity = Activity.model_validate(item)
            latest[activity.stage] = activity
        for activity in latest.values():
            state = {"started": "开始", "succeeded": "完成", "failed": "未完成", "skipped": "未执行"}[activity.status]
            st.caption(ACTIVITY_LABELS[activity.stage] + " · " + state)


def render_consent(workspace):
    if workspace.agent_session.busy:
        st.session_state["orange_agent_allow_proposal"] = False
    st.markdown("""<style>
    .st-key-orange_agent_controls {color:var(--oc-text-primary); overflow-wrap:anywhere;}
    .st-key-orange_agent_controls [data-testid="stExpander"] details {background:var(--oc-surface); border-color:var(--oc-border);}
    .st-key-orange_agent_controls summary, .st-key-orange_agent_controls p {color:var(--oc-text-primary);}
    .st-key-orange_agent_controls [data-testid="stCaptionContainer"] p {color:var(--oc-text-secondary);}
    .st-key-orange_agent_controls button {color:var(--oc-text-primary); background:var(--oc-surface); border-color:var(--oc-border); white-space:normal;}
    .st-key-orange_agent_controls button:hover {background:var(--oc-accent-soft); border-color:var(--oc-accent);}
    .st-key-orange_agent_candidate_controls button {color:var(--oc-text-primary); background:var(--oc-surface); border-color:var(--oc-border); white-space:normal;}
    [class*="st-key-orange_agent_activity_"] [data-testid="stExpander"] details {background:var(--oc-surface); border-color:var(--oc-border);}
    [class*="st-key-orange_agent_activity_"] [data-testid="stExpander"] summary {background:var(--oc-surface); color:var(--oc-text-primary);}
    [class*="st-key-orange_agent_activity_"] [data-testid="stExpander"] summary:hover {background:var(--oc-accent-soft);}
    [class*="st-key-orange_agent_activity_"] [data-testid="stExpander"] summary p {color:var(--oc-text-primary);}
    [class*="st-key-orange_agent_activity_"] [data-testid="stCaptionContainer"] p {color:var(--oc-text-secondary);}
    </style>""", unsafe_allow_html=True)
    with st.container(key="orange_agent_controls"):
        _consent_controls(workspace)


def _consent_controls(workspace):
    session = workspace.agent_session
    with st.expander("AI 对话与数据使用", expanded=False):
        if session.consent:
            st.caption("AI 对话已启用。仅发送本轮需要的上下文，不会自动确认画像或记忆。")
            st.button("停止向 Qwen 发送上下文", key="orange_agent_revoke", on_click=session.set_consent,
                      kwargs={"granted": False})
        else:
            st.write("启用 AI 对话后，本轮消息、少量近期聊天，以及回答所需的已确认画像或相关记忆会发送给阿里云 Qwen。长期信息仍需你明确确认。")
            st.button("同意并启用 AI 对话", key="orange_agent_consent", on_click=session.set_consent,
                      kwargs={"granted": True})
            st.caption("未同意时保留本地引导演示，不会调用在线模型。")
        if session.consent:
            st.checkbox("允许本轮生成待复核候选（不自动确认）", key="orange_agent_allow_proposal", value=False, disabled=session.busy)
    if not session.consent:
        st.caption("当前为本地引导演示 · 非在线 AI 对话")


def render_pending(workspace):
    session = workspace.agent_session
    progress = session.progress()
    if not session.busy or progress is None:
        return
    pending, text, activities, cancelled = progress
    if pending.thread_id != workspace.thread.thread_id:
        return
    with st.chat_message("user"):
        st.markdown(escape(pending.text).replace("\n", "<br>"), unsafe_allow_html=True)
    with st.chat_message("assistant"):
        if text:
            st.write(text)
        if cancelled:
            st.caption("已停止生成")
        elif activities:
            latest = activities[-1]
            st.caption(ACTIVITY_LABELS[latest["stage"]] + ("…" if latest["status"] == "started" else ""))
        render_activity(activities, key=pending.turn_id)


def render_candidates(workspace):
    session = workspace.agent_session
    result = session.last_result
    if session.busy or result is None or not result.registry.proposals:
        return
    with st.container(key="orange_agent_candidate_controls"), st.expander("待你复核的候选", expanded=False):
        for index, proposal in enumerate(tuple(result.registry.proposals)):
            st.write(proposal.user_quote)
            change = result.registry.memory_changes.get(proposal.model_dump_json())
            st.caption("职业偏好候选，不是能力认定。" + ("将生成并确认下一版画像，保留旧版。" if proposal.kind == "profile" else "尚未保存为长期记忆。"))
            choice = None
            if change is not None:
                from memory.models import MemoryChangeChoice
                st.write("这个维度已有不同的已确认历史值：" + "、".join(change.previous_values))
                labels = {MemoryChangeChoice.UPDATE_LONG_TERM: "更新长期记忆（替代该维度旧记录）",
                    MemoryChangeChoice.KEEP_BOTH: "两项都保留", MemoryChangeChoice.DEFER: "暂时不保存",
                    MemoryChangeChoice.UNCERTAIN: "还不确定"}
                choice = st.selectbox("如何处理这项变化", change.allowed_user_choices,
                    format_func=labels.get, key=f"orange_candidate_choice_{index}")
            if st.button("确认这项画像修订" if proposal.kind == "profile" else "确认保存这项记忆",
                         key=f"orange_candidate_confirm_{index}"):
                try:
                    result.registry.confirm_proposal(proposal, confirmed_by_user=True, memory_choice=choice)
                except (ValueError, MemoryLayerError):
                    st.warning("长期信息已变化，请重新生成候选后复核。")
                else:
                    st.rerun()
