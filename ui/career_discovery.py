"""Chat-native read-only direction review, never a role-search or save action."""

from uuid import uuid4
import streamlit as st

from career_discovery.models import Readiness, Status


def render_career_discovery(workspace):
    session = workspace.career_discovery
    # An ordinary QA render never builds discovery context or reads Profile/Memory.
    result = session.current_result() if session.result is not None else None
    disabled = workspace.agent_session.busy or session.busy
    with st.container(key="orange_career_discovery"):
        if result and result.readiness == Readiness.NEEDS_CLARIFICATION:
            with st.chat_message("assistant"):
                st.write(result.clarification_need.question)
                st.caption("只需补充这个会影响方向范围的问题；尚未生成方向。")
        if session.status in {Status.INVALID_CONTEXT, Status.INVALID_OUTPUT, Status.INVALID_REFERENCE,
                              Status.PROVIDER_FAILED, Status.STALE}:
            st.warning("本次探索未通过安全检查；没有生成或自动修复方向，也未自动重试。状态：" + session.status.value)
        if result and result.readiness == Readiness.READY and session.status in {Status.CREATED, Status.SELECTED}:
            with st.chat_message("assistant"):
                st.write("以下是值得审阅的探索方向，不是具体岗位或已确认职业目标。")
                st.caption("顺序不代表排名。")
                if result.partial:
                    st.caption("本次上下文为有限投影，部分完整条目因预算未纳入。")
                if not result.directions:
                    st.write("本次没有足够依据提出方向；未补造候选。")
                token = session.token()
                for direction in result.directions:
                    st.subheader(direction.title)
                    st.write(direction.why_explore)
                    st.caption("目标关系：" + direction.goal_relation.value + " · 探索依据：" + direction.confidence.value)
                    st.write("可迁移能力（待验证解释）")
                    for capability in direction.transferable_capabilities:
                        st.write(capability.label)
                        st.caption(capability.safe_explanation)
                    if not direction.transferable_capabilities:
                        st.caption("尚未提出可验证的能力迁移解释。")
                    st.write("迁移考量（不是确认缺口）")
                    for consideration in direction.transition_considerations:
                        st.write(consideration.description)
                    st.write("不确定项 / 需要补充的证据")
                    for item in (*direction.uncertainties, *direction.evidence_gaps):
                        st.write(item)
                    st.button("继续探索这个方向", key="orange_direction_" + result.request_id + "_" + direction.direction_id,
                        disabled=disabled or token is None, on_click=session.select, args=(token, direction.direction_id))
                if session.selected_direction_id:
                    st.caption("已选择本轮探索方向；未确认职业目标、保存记忆或启动岗位搜索。")
            return
        with st.expander("探索职业方向", expanded=bool(result)):
            st.write("按已确认的理解和本轮意向，看看哪些方向值得继续探索。")
            st.caption("D.1 离线基础：不连接真实模型；只提出候选，不写入画像或长期记忆。")
            statement = st.text_input("本轮探索意向（可选）", max_chars=1200,
                key="orange_discovery_statement_" + workspace.thread.thread_id, disabled=disabled)
            consent = st.checkbox("同意本次使用精简的已确认画像、相关已确认记忆和本轮上下文进行方向探索",
                key="orange_discovery_consent_" + workspace.thread.thread_id, disabled=disabled)
            # Fresh operation identity is captured by one explicit UI action;
            # repeated renders never execute the callback.
            st.button("开始探索", key="orange_discovery_start", disabled=disabled or not consent,
                on_click=session.start, kwargs={"explicitly_requested": True, "consent": consent,
                    "current_statement": statement, "request_id": "discovery_" + uuid4().hex,
                    "expected_owner_scope_id": workspace.owner_scope_id, "expected_conversation_id": workspace.thread.thread_id})
