"""Chat-native read-only direction review, never a role-search or save action."""

from uuid import uuid4
import streamlit as st

from career_discovery.models import Readiness, Status
from career_discovery.demo import PUBLIC_DEMO_NOTICE
from ui.chat_runtime import WorkspaceMode


def render_career_discovery(workspace):
    session = workspace.career_discovery
    # An ordinary QA render never builds discovery context or reads Profile/Memory.
    result = session.current_result() if session.result is not None else None
    disabled = workspace.agent_session.busy or session.busy
    with st.container(key="orange_career_discovery"):
        if workspace.runtime_mode == WorkspaceMode.PUBLIC_SYNTHETIC_DEMO:
            st.caption(PUBLIC_DEMO_NOTICE)
        if result and result.readiness == Readiness.NEEDS_CLARIFICATION:
            with st.chat_message("assistant"):
                st.write(result.clarification_need.question)
                st.caption("这会影响我接下来给你看的方向范围。如果还没想好，也可以直接说“都可以看看”。")
        if session.status in {Status.INVALID_CONTEXT, Status.INVALID_OUTPUT, Status.INVALID_REFERENCE,
                              Status.PROVIDER_FAILED, Status.STALE}:
            st.warning("这次探索暂时没有成功；已有理解没有被修改，也未自动重试或补造方向。")
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
                        disabled=disabled or token is None, on_click=workspace.explore_direction, args=(token, direction.direction_id))
                if session.selected_direction_id:
                    st.caption("已选择本轮探索方向；工作理解在主聊天继续，未确认职业目标、保存记忆或启动岗位搜索。")
            return
        with st.expander("探索职业方向", expanded=bool(result) or session.status == Status.CONSENT_REQUIRED):
            st.write("按已确认的理解和本轮意向，看看哪些方向值得继续探索。")
            st.caption("只提出值得继续了解的方向，不替你做最终职业决定。")
            statement = st.text_input("本轮探索意向（可选）", max_chars=1200,
                key="orange_discovery_statement_" + workspace.thread.thread_id, disabled=disabled)
            st.caption("Orange 只会参考你已经确认过的信息。本次探索不会自动修改你的职业画像或长期记忆。")
            consent = st.checkbox("参考我之前确认过的信息",
                key="orange_discovery_consent_" + workspace.thread.thread_id, disabled=disabled)
            # Fresh operation identity is captured by one explicit UI action;
            # repeated renders never execute the callback.
            st.button("开始探索", key="orange_discovery_start", disabled=disabled or not consent,
                on_click=session.start, kwargs={"explicitly_requested": True, "consent": consent,
                    "current_statement": statement, "request_id": "discovery_" + uuid4().hex,
                    "expected_owner_scope_id": workspace.owner_scope_id, "expected_conversation_id": workspace.thread.thread_id})
