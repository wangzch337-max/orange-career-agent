"""Ephemeral chat presentation. No calls, confirmation or store writes on render."""

from html import escape

import streamlit as st

from career_runtime.profile_conversation import InterviewStage
from profile_refinement.context import CATEGORIES, entry_id, value_for
from profile_refinement.models import ChangeType, Resolution, Status
from ui.onboarding.assets import sphere_markup
from ui.presentation import GOAL_TYPE_LABELS

CONTINUE = "继续完善我的职业画像"
INTERVIEW_CONSENT = (
    "继续后，我会结合这份简历、你已确认的信息、相关长期记忆和接下来的回答来理解你的职业情况。"
    "必要的精简内容会发送给 Qwen，问题和画像只暂存在本次会话中；只有你确认后才会保存职业画像。"
    "这不会启用普通 AI 聊天，也不会自动保存长期记忆。"
)
REVIEW_COPY = ("这是 Orange 根据你的简历和我们刚才的对话整理出的理解。"
               "只有你确认后，它才会成为之后职业探索所使用的已确认职业画像。")
CATEGORY_LABELS = {
    "work_experience": "职业经历", "education": "教育经历", "skills": "已有证据的能力",
    "interests": "职业兴趣 / 方向意向", "career_preferences": "职业偏好", "values": "价值观",
    "goals": "目标", "strengths": "优势线索", "development_areas": "发展方向",
    "uncertainties": "仍不确定", "clarification_questions": "仍需了解",
    "projects": "项目经历", "constraints": "限制", "location_preferences": "地点偏好",
    "work_style_preferences": "工作偏好", "tools": "工具", "domain_knowledge": "领域知识",
    "certifications": "证书", "professional_qualifications": "专业资格", "research": "研究经历",
    "leadership": "领导 / 协作经历", "collaboration": "协作经历", "languages": "语言",
    "achievements": "成果",
    "role_interests": "角色兴趣", "industry_interests": "行业兴趣",
    "transition_intent": "职业转向意向", "other_evidence": "其他职业信息",
}


def render_resume_transition(workspace):
    from resume_evidence.session import ResumeAnalysisStatus
    from ui.resume_evidence import render_resume_analysis
    if workspace.resume_analysis.status == ResumeAnalysisStatus.READY and workspace.resume_analysis.bundle is not None:
        st.write("我已经先从你的简历里整理出了一些职业信息。")
    render_resume_analysis(workspace)
    render_invitation(workspace)


def render_invitation(workspace):
    interview = workspace.profile_conversation
    if interview.stage != InterviewStage.IDLE or not interview.available():
        return
    st.write("简历能告诉我你做过什么，但不一定能告诉我你接下来想去哪里。"
             "如果你愿意，我们可以聊几个真正会影响职业探索的问题，一步一步补全理解。")
    st.caption(INTERVIEW_CONSENT)
    st.button(CONTINUE, key="orange_clarification_start", disabled=workspace.agent_session.busy,
        on_click=interview.start, kwargs={"consent": True, "expected_consent": workspace.resume_analysis.consent})


def _render_value(value):
    st.text(value.label)
    for detail in value.details:
        st.text("• " + detail)
    for field, label in (("organization", "机构"), ("time_range", "时间"), ("level", "熟练度")):
        if getattr(value, field):
            st.text(label + "：" + getattr(value, field))
    if value.goal_type:
        st.caption("目标类型：" + GOAL_TYPE_LABELS[value.goal_type])


def render_profile_review(workspace):
    interview, session = workspace.profile_conversation, workspace.profile_refinement
    draft = session.current_draft()
    if interview.stage != InterviewStage.REVIEW or draft is None:
        return
    if draft.status not in {Status.DRAFT, Status.REVIEWING, Status.NO_MATERIAL_CHANGE}:
        st.write("这份理解对应的信息已经变化，暂时不能确认。请重新核对已有信息，再继续完善。")
        return
    st.subheader("我的职业画像", anchor=False)
    st.caption(REVIEW_COPY)
    if draft.status == Status.NO_MATERIAL_CHANGE:
        st.write("目前没有需要更新的内容；已确认的理解保持不变。")
    if interview.skipped:
        st.caption("有问题暂时跳过，相关信息仍待了解，没有替你补出答案。")
    if interview.bound_reached:
        st.caption("我们先整理这一版；还有一些细节待了解，不需要现在回答所有问题。")
    # Read-only preview: retain unchanged base fields; show each proposed change
    # and any old value, without constructing a prematurely confirmed Profile.
    categories = ("work_experience", *[c for c in CATEGORIES if c != "work_experience"])
    for category in categories:
        changes = [change for change in draft.changes if change.category == category]
        targets = {change.target_id for change in changes}
        retained = [value_for(category, entry) for entry in getattr(session.base, category, ())
                    if entry_id(category, entry) not in targets]
        if not changes and not retained:
            continue
        st.markdown("**" + CATEGORY_LABELS[category] + "**")
        for value in retained:
            _render_value(value)
        for change in changes:
            if change.old_value:
                st.text("原理解：" + change.old_value.label)
            if change.user_resolution in {Resolution.REJECT, Resolution.KEEP_OLD}:
                if change.old_value:
                    _render_value(change.old_value)
                else:
                    st.caption("这项暂不采纳。")
                continue
            value = change.edited_value or change.proposed_value
            if value:
                _render_value(value)
            elif change.change_type == ChangeType.REMOVE:
                st.caption("建议移除这项原理解，等待你确认。")
            if change.uncertainty != "none":
                st.caption("这一点仍不确定，会保留这种不确定性。")
            # Preserve selective rejection without a detached form or enum labels.
            st.button("保留这项原理解" if change.old_value else "暂不采纳这项",
                key="orange_profile_keep_" + change.change_id, disabled=workspace.agent_session.busy,
                on_click=session.resolve, args=(session.token(), change.change_id,
                    Resolution.KEEP_OLD if change.old_value else Resolution.REJECT))
    st.caption("确认表示接受上面展示的整份理解，包括明确标注的不确定性；不会自动保存长期记忆。")
    st.button("确认这份职业画像", key="orange_profile_confirm", disabled=workspace.agent_session.busy or
        draft.status not in {Status.DRAFT, Status.REVIEWING}, on_click=interview.confirm,
        args=(interview.token(), session.token()))
    st.button("我想修改", key="orange_profile_edit", on_click=interview.continue_talking,
        args=(interview.token(),), kwargs={"edit": True}, disabled=workspace.agent_session.busy)
    st.button("继续聊聊", key="orange_profile_continue", on_click=interview.continue_talking,
        args=(interview.token(),), disabled=workspace.agent_session.busy)


def render_interview_messages(workspace, anchor):
    interview = workspace.profile_conversation
    for message in interview.messages:
        if message.anchor != anchor:
            continue
        # Old review blocks no longer carry usable authority after edit/continue.
        if message.kind == "review" and (interview.stage != InterviewStage.REVIEW or
                message is not next((m for m in reversed(interview.messages) if m.kind == "review"), None)):
            continue
        with st.chat_message(message.role, avatar=sphere_markup() if message.role == "assistant" else None):
            if message.role == "user":
                st.markdown(escape(message.text).replace("\n", "<br>"), unsafe_allow_html=True)
            elif message.kind == "review":
                render_profile_review(workspace)
            else:
                st.text(message.text)
                question = workspace.clarification.current_question()
                if message.kind == "question" and question and message is next(
                        (m for m in reversed(interview.messages) if m.kind == "question"), None):
                    st.caption("可以直接在下面回答，不确定或暂时跳过也没关系。")
                    for index, text in enumerate(("我还不确定", "先跳过")):
                        st.button(text, key=f"orange_profile_reply_{interview.generation}_{index}",
                            on_click=interview.submit, args=(text,),
                            kwargs={"token": interview.token(), "question_token": question},
                            disabled=workspace.agent_session.busy)
    if interview.stage == InterviewStage.FAILED and anchor == len(workspace.chat.messages):
        st.button("继续聊聊", key="orange_profile_failure_continue", on_click=interview.continue_talking,
                  args=(interview.token(),), disabled=workspace.agent_session.busy)
