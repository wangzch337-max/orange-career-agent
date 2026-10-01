"""Reusable Streamlit renderers for validated Orange presentation data."""

from __future__ import annotations

from typing import Iterable

import streamlit as st

from data.models import JobIntelligenceRecord, JobRecord, MatchResult
from ui.presentation import (
    ACTION_STATUS_OPTIONS,
    GOAL_TYPE_LABELS,
    ActionTaskView,
    CareerDirectionCardView,
    CareerProfileView,
    ExplorationMapView,
    MemorySummaryView,
    RoleMemoryView,
    action_task_view,
    match_insight_groups,
    role_location,
)
from ui.visual_system import render_badges, render_panel, stylesheet


def apply_demo_style() -> None:
    st.markdown(stylesheet(), unsafe_allow_html=True)


def render_public_demo_banner() -> None:
    render_badges(("公开演示模式", "neutral"), ("虚构数据", "neutral"), ("离线 AI", "neutral"))


def render_progress(current_step: int, total_steps: int = 7) -> None:
    st.caption(f"探索步骤 · {current_step} / {total_steps}（不是画像完整度）")


def _render_labels(title: str, values: Iterable[str], *, empty: str = "暂无") -> None:
    items = list(values)
    with st.container(border=True):
        st.markdown(f"#### {title}")
        if items:
            for item in items:
                st.write(item)
        else:
            st.caption(empty)


def _render_profile_chips(title: str, values, *, empty: str) -> None:
    with st.container(border=True):
        st.markdown(f"#### {title}")
        if not values:
            st.caption(empty)
            return
        for item in values:
            st.write(item.label)
            # Read-only display of the existing authority label, never infer a new one.
            tone = {"已有证据": "evidence", "用户刚刚表达": "expressed", "待确认": "pending", "尚不确定": "unknown"}.get(item.authority, "neutral")
            label = "你刚刚表达" if item.authority == "用户刚刚表达" else item.authority
            render_badges((label, tone))


def render_dynamic_profile(view: CareerProfileView) -> None:
    st.markdown("### 你的动态职业画像")
    st.caption("它会随对话更新，但只有明确确认的信息才会进入长期理解。")
    if not any((view.demonstrated_capabilities, view.interests_and_work_style,
                view.exploration_directions, view.current_goals)):
        render_panel("我们从这里开始", "随着对话进行，这里会逐渐形成 Orange 对你的理解。未知项会保持开放，不作为能力弱点。")
    _render_profile_chips(
        "已经表现出的能力",
        view.demonstrated_capabilities,
        empty="继续聊项目后，这里会出现有依据的能力或本次表达。",
    )
    _render_profile_chips(
        "比较感兴趣 / 投入的事情",
        view.interests_and_work_style,
        empty="还没有表达具体偏好。",
    )
    _render_profile_chips(
        "当前值得继续探索的方向",
        view.exploration_directions,
        empty="Orange 还不会过早给出方向。",
    )
    _render_profile_chips(
        "还需要了解 / 证据不足",
        view.evidence_needs,
        empty="当前没有新增待确认项。",
    )
    _render_profile_chips(
        "当前目标",
        view.current_goals,
        empty="目标还没有明确。",
    )


def render_profile_review(payload: dict[str, object]) -> None:
    profile = payload["profile"]
    if not isinstance(profile, dict):
        raise ValueError("Invalid safe profile review payload")
    st.header("这是我目前对你的理解。你觉得准确吗？")
    render_badges((f"职业画像 v{profile['version']}", "neutral"), ("待确认", "pending"))
    st.write("这是 Orange 目前对你的理解。请确认、修改或保留不确定；确认不等于做出最终职业选择。")
    with st.expander("查看完整画像分类", expanded=False):
        left, right = st.columns(2)
        with left:
            _render_labels("技能", profile.get("skills", []))
            _render_labels("兴趣", profile.get("interests", []))
            _render_labels("价值观", profile.get("values", []))
            goals = [
                f"{item['label']} · {GOAL_TYPE_LABELS.get(item['goal_type'], item['goal_type'])}"
                for item in profile.get("goals", [])
            ]
            _render_labels("目标", goals)
        with right:
            _render_labels("优势", profile.get("strengths", []))
            _render_labels("发展方向", profile.get("development_areas", []))
            _render_labels("职业偏好", profile.get("career_preferences", []))
            _render_labels("不确定项", profile.get("uncertainties", []))
            _render_labels("澄清问题", profile.get("clarification_questions", []))
    st.caption("安全摘要不展示原始输入、Prompt 或隐藏推理。")


def render_role_card(view: CareerDirectionCardView, *, key: str) -> bool:
    with st.container(border=True):
        render_badges(("值得探索", "neutral"))
        st.subheader(view.title)
        st.write(view.one_line)
        st.markdown("**为什么值得继续了解**")
        st.write(view.why_explore)
        st.markdown("**你已经有的交集**")
        st.write("、".join(view.validated_overlaps) or "当前还没有直接证据")
        st.markdown("**Orange 还想确认**")
        st.write(view.clarification_need)
        return st.button("深入了解", key=key, use_container_width=True)


def render_job_intelligence(job: JobRecord, record: JobIntelligenceRecord) -> None:
    st.header(job.title)
    st.caption(f"岗位探索 · {role_location(job)} · 虚构公开岗位")
    render_panel("岗位事实", "以下来自公开虚构岗位资料，与用户画像和长期理解分开展示。")
    groups = (
        ("实际工作", record.actual_work),
        ("必需能力", record.required_capabilities),
        ("加分能力", record.preferred_capabilities),
        ("技术接触", record.technology_signals),
        ("工作方式", record.work_style),
        ("协作环境", record.collaboration_context),
        ("成长机会", record.growth_exposure),
        ("潜在摩擦", record.potential_friction),
    )
    _render_labels("这个岗位通常在做什么 · 实际工作", (item.label for item in record.actual_work))
    _render_labels("通常需要什么 · 必需能力", (item.label for item in record.required_capabilities))
    _render_labels("工作方式", (item.label for item in record.work_style))
    with st.expander("更多岗位信息 · 加分能力、协作与成长"):
        for title, signals in groups:
            if title not in ("实际工作", "必需能力", "工作方式"):
                _render_labels(title, (item.label for item in signals))
        _render_labels("仍未知", (item.topic for item in record.uncertainties))


def render_match_insights(result: MatchResult, profile, record) -> None:
    st.header(f"{result.role_title} · Match Insights")
    st.caption("这些是多维证据关系，不是结论、总体匹配分或岗位排名。")
    render_panel("理解证据关系，而不是一个分数", "已有交集、需要补证据、偏好上的交集、值得继续确认的摩擦，以及目前还不知道的部分，共同帮助你安排下一轮探索。")
    st.info("当前没有足够证据，不代表你不具备它。")
    for group in match_insight_groups(result, profile, record):
        with st.expander(
            f"{group.label} · {len(group.insights)}",
            expanded=bool(group.insights),
        ):
            display_label = {
                "strong_alignment": "已有明显交集", "partial_alignment": "已有部分交集",
                "evidence_missing": "需要补证据", "preference_alignment": "偏好上的交集",
                "potential_friction": "值得继续确认的摩擦", "unknown": "目前还不知道",
            }.get(group.relation_type.value, group.label)
            render_badges((display_label, "unknown" if group.relation_type.value == "unknown" else "neutral"))
            st.caption(group.explanation)
            if not group.insights:
                st.caption("当前没有此类已验证关系。")
            for view in group.insights:
                with st.container(border=True):
                    st.markdown(f"#### {view.title}")
                    st.caption(f"{view.relation_label} · {view.dimension_label}")
                    st.write(view.description)
                    if view.profile_signal_labels:
                        st.write("画像信号：" + "、".join(view.profile_signal_labels))
                    if view.job_signal_labels:
                        st.write("岗位信号：" + "、".join(view.job_signal_labels))
                    with st.expander("查看证据来源"):
                        st.caption(f"Insight ID：{view.insight_id}")
                        st.write("画像证据 ID：" + ("、".join(view.profile_evidence_ids) or "无"))
                        st.write("岗位证据 ID：" + ("、".join(view.job_evidence_ids) or "无"))


def render_action_task(view: ActionTaskView, *, key: str) -> tuple[str, bool]:
    with st.container(border=True):
        header, badge = st.columns([3, 1])
        header.markdown(f"#### {view.target}")
        with badge:
            render_badges((view.status, "neutral"))
        st.markdown("**WHY · 为什么现在做**")
        st.write(view.why)
        st.markdown("**WHAT · 具体怎么做**")
        for step in view.what_to_do:
            st.markdown(f"- {step}")
        st.markdown("**EVIDENCE · 要留下什么证据**")
        st.write(view.expected_evidence)
        with st.expander("查看行动依据"):
            st.caption("关联洞察：" + "、".join(view.related_insight_ids))
        if view.needs_evidence_review:
            st.info("你表示已经做过；Orange 先标记为需要证据复核，不会自动确认能力。")
        selected = st.selectbox(
            "STATUS · 当前状态",
            ACTION_STATUS_OPTIONS,
            index=ACTION_STATUS_OPTIONS.index(view.status),
            key=f"{key}_status",
        )
        st.caption("状态只用于本次会话安排；已完成不等于能力已确认。")
        already_done = st.button("我其实已经做过", key=f"{key}_done")
        return selected, already_done


def render_actions(
    result: MatchResult,
    statuses: dict[str, str],
    evidence_review_ids: set[str],
) -> list[tuple[str, str, bool]]:
    st.header(f"{result.role_title} · 行动计划")
    st.caption("把值得验证的问题变成可执行的小任务，留下能支持下一次判断的证据。")
    events: list[tuple[str, str, bool]] = []
    if not result.action_items:
        render_panel("暂时没有下一步行动", "当前没有需要展示的已验证行动。可以回到岗位理解，查看仍需澄清的问题；不会为了填满页面生成任务。")
        return events
    for action in result.action_items:
        view = action_task_view(
            action,
            result,
            status=statuses.get(action.action_id, "未开始"),
            needs_evidence_review=action.action_id in evidence_review_ids,
        )
        status, already_done = render_action_task(view, key=f"action_{action.action_id}")
        events.append((action.action_id, status, already_done))
    return events


def render_exploration_map(view: ExplorationMapView) -> None:
    st.header("你的当前 Career Exploration Map")
    st.info("这不是最终职业决定，而是基于目前证据整理出的下一轮探索方向。")
    columns = st.columns(3)
    with columns[0]:
        _render_labels("继续深入探索", view.continue_exploring, empty="还未标记优先深入的方向；可以在岗位探索中表达你的安排。")
    with columns[1]:
        _render_labels("保持开放", view.keep_open)
    with columns[2]:
        _render_labels("暂时不优先", view.deprioritized, empty="还未暂缓任何方向；保持开放不代表你必须都选。")
    _render_labels("还需要验证的问题", view.questions_to_validate)


def render_memory_summary(view: MemorySummaryView) -> None:
    st.header("Orange 对你的长期理解")
    st.info("Orange 只会把经过你明确确认的信息作为长期职业理解的一部分。")
    render_badges(("当前理解", "confirmed"))
    for version in view.profile_history:
        if version.endswith(" · 当前版本"):
            render_badges((version, "confirmed"))
    left, right = st.columns(2)
    with left:
        _render_labels("当前职业方向", view.current_directions)
        _render_labels("已确认能力", view.confirmed_capabilities)
        _render_labels("工作偏好", view.work_preferences)
        _render_labels("当前目标", view.current_goals)
    with right:
        _render_labels("你后来告诉 Orange", view.user_feedback, empty="还没有保存反馈")
        _render_labels("最近发生的变化", view.recent_changes, empty="暂无独立变化摘要；当前偏好与历史记录见下方。")
    _render_labels("当前已确认的长期偏好", view.current_memory_preferences)
    with st.expander("画像版本与历史 · 查看过往理解", expanded=False):
        render_badges(("历史记录", "neutral"))
        _render_labels("画像历史", view.profile_history)
        _render_labels("历史偏好", view.historical_memory_preferences, empty="暂无被替代的历史偏好")
    if view.pending_profile_revision:
        st.warning(view.pending_profile_revision + "；长期 Memory 的更新不会自动确认画像。")


def render_role_memory(view: RoleMemoryView) -> None:
    if not view.statements:
        render_panel("🍊 Orange 记得", "目前没有与这个岗位相关的已确认历史信息。不会将刚刚的回答自动当作长期理解。")
        return
    with st.container(border=True):
        st.markdown("### 🍊 Orange 记得")
        st.caption("来自你之前确认的信息；它不会改变岗位事实或当前 MatchResult。")
        render_badges(("来自你之前确认的信息", "confirmed"))
        for statement in view.statements:
            st.markdown(f"- {statement}")
        with st.expander("查看依据"):
            for item in view.evidence:
                type_label = {"career_preference": "工作偏好", "user_feedback": "你后来告诉 Orange", "confirmed_profile": "已确认职业画像", "career_goal": "职业目标"}.get(item.memory_type, item.memory_type)
                st.markdown(f"**{type_label}** · {item.status}")
                st.write(item.content)
                st.caption("确认时间：" + item.confirmed_at)


def render_developer_trace(events: list[dict[str, object]], diagnostics=None) -> None:
    with st.expander("开发者执行轨迹（安全）", expanded=False):
        if diagnostics is not None:
            from observability.diagnostics import safe_event_view
            from observability.models import DiagnosticComponent as DC, DiagnosticRunSummary
            # Validate the entire envelope before rendering even the first diagnostic value.
            validated_views = [safe_event_view(e) for e in diagnostics["events"]]
            summary = DiagnosticRunSummary.model_validate(diagnostics["summary"].model_dump())
            st.markdown("#### Run Summary")
            st.caption(f"run_id={summary.run_id} · {summary.status.value} · events={summary.event_count}")
            if not validated_views:
                render_panel("诊断尚未开始", "完成一次职业探索操作后，这里会出现安全执行事件；正常的未知并不是失败。")
            summary_columns = st.columns(3)
            summary_columns[0].metric("Provider calls", summary.provider_call_count)
            summary_columns[1].metric("Memory retrievals", summary.memory_retrieval_count)
            duration = round(summary.duration_ms, 2) if summary.duration_ms is not None else "尚未测量"
            summary_columns[2].metric("Measured duration · ms", duration)
            st.caption(f"workflow_status={summary.workflow_status} · recording_failures={summary.recording_failure_count}")
            st.markdown("#### Workflow Timeline")
            rows = [{key: item[key] for key in ("component", "operation", "status", "duration_ms")}
                    for item in validated_views]
            if rows:
                st.dataframe(rows, hide_index=True, width="stretch")
            else:
                st.caption("尚无执行事件。")
            for event in validated_views:
                if event["source_event_type"] and event["component"] == "WORKFLOW":
                    st.code(f"{event['source_event_type']} · {event['component']} · {event['status']}", language=None)
            st.markdown("#### Component Activity")
            if summary.component_counts:
                st.dataframe([{"component": key.value, "events": value} for key, value in summary.component_counts.items()], hide_index=True, width="stretch")
            else:
                st.caption("尚无组件活动。")
            st.markdown("#### Memory Activity")
            memory_components = {DC.MEMORY, DC.MEMORY_RETRIEVAL, DC.MEMORY_CONTEXT, DC.VECTOR_INDEX, DC.PROFILE_REFINEMENT, DC.ROLE_EXPLORATION}
            memory_rows = [{key: view[key] for key in ("component", "operation", "status", "counts")}
                           for view in validated_views if DC(view["component"]) in memory_components and view["status"] != "STARTED"]
            if memory_rows:
                st.dataframe(memory_rows, hide_index=True, width="stretch")
            else:
                st.caption("尚无 Memory 活动。")
            st.markdown("#### Match Diagnostics")
            matches = [safe_event_view(e) for e in diagnostics["events"] if e.component == DC.MATCH_INSIGHT and e.operation == "match_run" and e.status.value == "SUCCEEDED"]
            for match in matches:
                st.write(match["counts"])
            if not matches:
                st.caption("尚无已完成 Match 诊断。")
            st.markdown("#### Warnings / Failures")
            flagged = [safe_event_view(e) for e in diagnostics["events"] if e.status.value == "FAILED" or "warning" in e.safe_metadata]
            if not flagged and not summary.recording_failure_count:
                st.caption("无诊断 warning/failure；正常的未知不作为 warning。")
            for event in flagged:
                st.write({"component": event["component"], "operation": event["operation"], "status": event["status"],
                          "error_category": event["error_category"], "safe_metadata": event["safe_metadata"]})
            with st.expander("Raw Safe Events", expanded=False):
                for event in diagnostics["events"]:
                    st.json(safe_event_view(event))
            return
        if not events:
            st.caption("工作流尚未开始。")
            return
        for event in events:
            details = [str(event["event_type"])]
            for key in ("node", "status", "profile_version", "checkpoint_mode", "count"):
                if event.get(key) is not None:
                    details.append(f"{key}={event[key]}")
            st.code(" · ".join(details), language=None)
