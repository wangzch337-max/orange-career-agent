"""Small chat-native, separate resume consent/action, no evidence dashboard."""

import streamlit as st

from resume_intake.models import ResumeParseStatus
from resume_evidence.session import ResumeAnalysisStatus as Status

FAILURE_COPY = {
    Status.CONTEXT_BUILD_FAILED: "无法安全整理分析输入，请检查或重新上传简历。",
    Status.PROVIDER_FAILED: "本次简历分析未完成，没有保存候选证据。",
    Status.INVALID_STRUCTURED_OUTPUT: "分析结果格式无效，没有保存候选证据。",
    Status.INVALID_SOURCE_REFERENCE: "分析结果的来源引用无效，没有保存候选证据。",
    Status.EVIDENCE_VALIDATION_FAILED: "分析结果未通过来源校验，没有保存候选证据。",
}


def render_resume_analysis(workspace) -> None:
    intake = workspace.resume_intake
    if intake.result is None or intake.result.status != ResumeParseStatus.READY:
        return
    session = workspace.resume_analysis
    allowed = session.has_consent
    disabled = workspace.agent_session.busy
    with st.container(key="orange_resume_analysis"):
        st.caption("如继续分析，会把经过精简的简历文字发送给 Qwen；原始文件不会发送或长期保存。"
                   "自动移除联系方式不能保证识别所有个人信息。此同意只用于当前简历，不等于普通聊天同意。")
        if not allowed:
            try:
                identity = session._identity()
            except Exception:
                st.warning(FAILURE_COPY[Status.CONTEXT_BUILD_FAILED])
                return
            if identity is None:
                return
            st.button("同意这份简历的 AI 分析", key="orange_resume_ai_consent",
                      on_click=session.grant, disabled=disabled,
                      kwargs={"owner_scope_id": identity.owner_scope_id, "thread_id": identity.thread_id,
                              "source_id": identity.source_id, "fingerprint": identity.fingerprint})
            return
        st.button("撤回简历分析同意", key="orange_resume_ai_revoke", on_click=session.revoke, disabled=disabled)
        if session.status == Status.READY and session.bundle is not None:
            st.write(f"我已经整理出这份简历中的主要职业证据（{len(session.bundle.items)} 项候选，尚未写入画像或记忆）。")
            if session.usage and session.usage.provider == "fake":
                st.caption("本地离线验证：使用 Fake provider，未发送给 Qwen。")
            if session.bundle.context_partial:
                st.caption("本次只分析了部分简历内容。")
        elif session.status in FAILURE_COPY:
            st.warning(FAILURE_COPY[session.status])
            st.caption("不会自动重试；如需重新分析，请先撤回，再明确同意。")
        elif st.button("分析这份简历", key="orange_resume_ai_analyze", disabled=disabled or session.used):
            with st.spinner("正在整理简历来源证据…"):
                session.analyze()
            st.rerun()
