"""Small chat-native, separate resume consent/action, no evidence dashboard."""

import streamlit as st

from resume_evidence.models import ResumeEvidenceBundle, WorkExperienceEvidence, ProjectEvidence
from resume_intake.models import ResumeParseStatus
from resume_evidence.session import ResumeAnalysisStatus as Status

FAILURE_COPY = {
    Status.CONTEXT_BUILD_FAILED: "无法安全整理分析输入，请检查或重新上传简历。",
    Status.PROVIDER_FAILED: "本次简历分析未完成，没有保存候选证据。",
    Status.INVALID_STRUCTURED_OUTPUT: "分析结果格式无效，没有保存候选证据。",
    Status.INVALID_SOURCE_REFERENCE: "分析结果的来源引用无效，没有保存候选证据。",
    Status.EVIDENCE_VALIDATION_FAILED: "分析结果未通过来源校验，没有保存候选证据。",
}

CATEGORY_LABELS = {
    "education": "教育经历", "responsibilities": "职责", "achievements": "成果",
    "skills": "能力 / 技能", "tools": "工具", "domain_knowledge": "领域知识",
    "certifications": "证书", "professional_qualifications": "专业资格",
    "research": "研究经历", "leadership": "领导 / 协作经历", "collaboration": "协作经历",
    "languages": "语言", "portfolio": "作品集", "business_metrics": "业务成果 / 指标",
    "awards": "奖项", "publications": "发表", "other_evidence": "其他证据",
    "uncertainty": "待澄清证据",
}
UNCERTAINTY_TOPICS = {
    "dates": "时间", "organization": "机构", "proficiency": "熟练度", "ownership": "责任归属",
    "career_goal": "职业目标", "role_overlap": "角色重叠",
    "project_work_boundary": "项目 / 工作边界", "other": "其他待澄清事项",
}
UNCERTAINTY_STATUSES = {"unclear": "尚不明确", "not_stated": "简历未说明"}


def _render_details(label: str, values: tuple[str, ...]) -> None:
    if values:
        st.caption(label)
        for value in values:
            st.text("• " + value)


def render_evidence_summary(bundle: ResumeEvidenceBundle) -> None:
    """Present an admitted candidate bundle, without source fields or write actions."""
    with st.container(key="orange_resume_evidence_summary"):
        st.subheader("Orange 从简历中整理出的职业证据", anchor=False)
        st.caption("这些内容来自简历，并已通过来源与结构校验；目前仍是候选证据，尚未写入职业画像或长期记忆。")
        if not bundle.items:
            st.write("这份简历暂时没有形成可展示的职业证据候选。")
        work = [item for item in bundle.items if isinstance(item, WorkExperienceEvidence)]
        if work:
            st.markdown("**工作经历**")
            for item in work:
                with st.container(border=True):
                    if item.role_title:
                        st.text(item.role_title)
                    identity = tuple(value for value in (item.organization, item.time_range) if value)
                    if identity:
                        st.text(" · ".join(identity))
                    for label, values in (("职责", item.responsibilities), ("成果", item.achievements),
                                          ("领域线索", item.domain_signals), ("工具", item.tools),
                                          ("业务成果 / 指标", item.business_metrics)):
                        _render_details(label, values)
                    if not item.material_fields:
                        st.text(item.canonical_text)
        projects = [item for item in bundle.items if isinstance(item, ProjectEvidence)]
        if projects:
            st.markdown("**项目经历**")
            for item in projects:
                with st.container(border=True):
                    if item.project_name:
                        st.text(item.project_name)
                    _render_details("职责", item.responsibilities)
                    _render_details("成果", item.achievements)
                    if not item.material_fields:
                        st.text(item.canonical_text)
        for category, label in CATEGORY_LABELS.items():
            items = [item for item in bundle.items if item.category == category]
            if items:
                st.markdown("**" + label + "**")
                for item in items:
                    st.text("• " + item.canonical_text)
        if bundle.uncertainties:
            st.markdown("**仍不确定**")
            for item in bundle.uncertainties:
                st.text("• " + UNCERTAINTY_TOPICS[item.topic] + "：" + UNCERTAINTY_STATUSES[item.status])
        st.caption("简历证据 ≠ 已确认职业画像。只有经过后续澄清、画像修订和你的明确确认后，"
                   "相关信息才可能进入已确认职业画像。")


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
            if session.usage and session.usage.provider == "fake":
                st.caption("本地离线验证：使用 Fake provider，未发送给 Qwen。")
            if session.bundle.context_partial:
                st.caption("本次只分析了部分简历内容。")
            render_evidence_summary(session.bundle)
        elif session.status in FAILURE_COPY:
            st.warning(FAILURE_COPY[session.status])
            st.caption("不会自动重试；如需重新分析，请先撤回，再明确同意。")
        elif st.button("分析这份简历", key="orange_resume_ai_analyze", disabled=disabled or session.used):
            with st.spinner("正在整理简历来源证据…"):
                session.analyze()
            st.rerun()
