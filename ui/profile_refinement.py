"""Minimal diff-first explicit review inside the existing chat workspace."""

import streamlit as st

from profile_refinement.confirmation import ACCEPTED, MEMORY_FIELDS
from profile_refinement.context import binding_for_refinement, workspace_inputs
from profile_refinement.models import ChangeType, Resolution, Status

REASONS = {"new_supported_evidence": "新增来源支持的内容", "current_user_update": "本轮明确输入",
           "clarification_update": "本轮澄清回答", "source_conflict": "与旧理解有差异，需你决定",
           "uncertainty_preserved": "保留不确定性", "same_understanding": "理解未变化"}
FAILURES = {Status.INVALID_DRAFT, Status.INVALID_REFERENCE, Status.STALE_DRAFT, Status.PROFILE_VERSION_CONFLICT,
            Status.PROFILE_CONFIRMATION_FAILED, Status.OWNER_SCOPE_MISMATCH, Status.CONVERSATION_NOT_FOUND, Status.PROVIDER_FAILED}


def render_profile_refinement(workspace):
    analysis = workspace.resume_analysis
    if not analysis.has_consent or analysis.bundle is None:
        return
    session = workspace.profile_refinement
    draft = session.current_draft()
    disabled = workspace.agent_session.busy or session.busy
    with st.container(key="orange_profile_refinement"):
        if session.status in FAILURES:
            st.warning("本次画像操作未通过安全检查；未自动重试。状态：" + session.status.value)
        if draft and draft.status == Status.CONFIRMED:
            st.write(f"已更新职业理解，画像 v{session.confirmed_profile.version} 已确认。")
            if session.memory_status == Status.MEMORY_SIDE_EFFECT_FAILED.value:
                st.warning("画像已保存；可选长期记忆未完成，不影响画像。")
            return
        if draft and draft.status == Status.NO_MATERIAL_CHANGE:
            st.write("没有实质变化；未创建新画像版本或重复记忆。")
            return
        if draft and draft.status in {Status.DRAFT, Status.REVIEWING}:
            token = session.token()
            st.write(f"画像变更草案 v{draft.proposed_profile_version} · 尚未确认")
            st.caption("只审核变化；未选择的建议不会写入。每项需明确接受、编辑、保留旧值或拒绝。")
            for change in draft.changes:
                key = f"orange_profile_{draft.draft_id}_{token.draft_fingerprint}_{change.change_id}"
                with st.chat_message("assistant"):
                    st.write(change.category + " · " + change.change_type.value)
                    st.text("原理解：" + (change.old_value.label if change.old_value else "无"))
                    value = change.edited_value or change.proposed_value
                    st.text("新候选：" + (value.label if value else "移除该项"))
                    if value and value.details:
                        for detail in value.details:
                            st.text(detail)
                    if value:
                        for name, label in (("level", "熟练度"), ("goal_type", "目标类型"), ("organization", "机构"), ("time_range", "时间")):
                            if getattr(value, name):
                                st.text(label + "：" + getattr(value, name))
                    st.caption("来源：" + "、".join(change.source_refs) + " · " + REASONS.get(change.reason_summary, "来源支持的候选"))
                    if change.conflict_state != "none" or change.uncertainty != "none":
                        st.caption("存在差异/不确定性；你的逐项选择决定最终内容。")
                    st.caption("本项选择：" + change.user_resolution.value)
                st.button("确认建议值", key=key + "_accept", disabled=disabled,
                    on_click=session.resolve, args=(token, change.change_id, Resolution.CONFIRM))
                if change.proposed_value is not None:
                    label = st.text_input("编辑候选标签", value=value.label, max_chars=160, key=key + "_label", disabled=disabled)
                    details = st.text_area("编辑候选要点（最多四行）", value="\n".join(value.details), max_chars=963,
                                           key=key + "_details", disabled=disabled)
                    edited = value.model_dump()
                    edited.update(label=label, details=details.splitlines())
                    if change.category == "skills":
                        edited["level"] = st.text_input("熟练度（可留空）", value=value.level or "", max_chars=60,
                                                       key=key + "_level", disabled=disabled) or None
                    if change.category == "goals":
                        kinds = ["career_goal", "project_goal", "learning_goal"]
                        edited["goal_type"] = st.selectbox("目标类型", kinds, index=kinds.index(value.goal_type),
                                                           key=key + "_goal_type", disabled=disabled)
                    if change.category in {"work_experience", "education"}:
                        for name, label, limit in (("organization", "机构", 160), ("time_range", "时间", 80)):
                            edited[name] = st.text_input(label, value=getattr(value, name) or "", max_chars=limit,
                                                         key=key + "_" + name, disabled=disabled) or None
                    st.button("使用我的编辑", key=key + "_edit", disabled=disabled,
                        on_click=session.resolve, args=(token, change.change_id, Resolution.EDIT), kwargs={"edited_value": edited})
                    st.button("确认仍不确定", key=key + "_uncertain", disabled=disabled,
                        on_click=session.resolve, args=(token, change.change_id, Resolution.UNCERTAIN))
                st.button("保留旧值" if change.old_value else "拒绝此项", key=key + "_keep", disabled=disabled,
                    on_click=session.resolve, args=(token, change.change_id, Resolution.KEEP_OLD if change.old_value else Resolution.REJECT))
            eligible = [c for c in draft.changes if c.category in MEMORY_FIELDS and c.user_resolution in ACCEPTED and c.change_type != ChangeType.REMOVE]
            memory_id = None
            if eligible:
                selected = st.selectbox("可选：确认后同步一条长期记忆", [None, *[c.change_id for c in eligible]],
                    format_func=lambda choice: "不同步长期记忆" if choice is None else next(
                        (c.edited_value or c.proposed_value).label for c in eligible if c.change_id == choice),
                    key=f"orange_profile_memory_{token.draft_fingerprint}", disabled=disabled)
                memory_id = selected
            pending = any(c.user_resolution == Resolution.PENDING for c in draft.changes)
            st.button("确认所选变更并保存画像", key=f"orange_profile_confirm_{token.draft_fingerprint}",
                disabled=disabled or pending, on_click=session.confirm, args=(token,),
                kwargs={"confirmed_by_user": True, "memory_change_id": memory_id})
            st.button("拒绝本草案", key=f"orange_profile_reject_{token.draft_fingerprint}", disabled=disabled,
                on_click=session.reject, args=(token,))
            return
        # An unrelated chat rerender does not trigger refinement or confirmation.
        statement = st.text_input("本轮画像补充（可选）", key="orange_profile_current_statement_" + workspace.thread.thread_id,
                                  max_chars=2000, disabled=disabled)
        st.caption("仅在点击后向 Qwen 发送精简候选、当前已确认字段与相关记忆；只生成变更草案，不确认画像，不推荐职业。")
        try:
            expected = binding_for_refinement(workspace_inputs(workspace, current_statement=statement))
        except Exception:
            st.warning("候选或已确认画像状态已变化；暂不创建新草案。")
            return
        st.button("同意并整理画像变更草案", key="orange_profile_refinement_start", disabled=disabled,
            on_click=session.start, kwargs={"explicit_review": True, "current_statement": statement, "expected_binding": expected})
