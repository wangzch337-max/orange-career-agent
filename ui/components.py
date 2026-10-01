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


def apply_demo_style() -> None:
    st.markdown(
        """
        <style>
        .block-container {padding-top: 1.6rem; padding-bottom: 3rem;}
        [data-testid="stSidebar"] {background: #fff8ef;}
        div[data-testid="stVerticalBlockBorderWrapper"] {background: #fffdf9;}
        .orange-kicker {color: #c65f13; font-weight: 700; letter-spacing: .04em;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_public_demo_banner() -> None:
    st.info(
        "当前为公开演示模式：使用虚构数据和离线模型，不包含真实个人信息。",
        icon="🛡️",
    )


def render_progress(current_step: int, total_steps: int = 7) -> None:
    st.caption(f"探索进度 · {current_step} / {total_steps}")
    st.progress(current_step / total_steps)


def _render_labels(title: str, values: Iterable[str], *, empty: str = "暂无") -> None:
    items = list(values)
    with st.container(border=True):
        st.markdown(f"#### {title}")
        if items:
            for item in items:
                st.markdown(f"- {item}")
        else:
            st.caption(empty)


def _render_profile_chips(title: str, values, *, empty: str) -> None:
    with st.container(border=True):
        st.markdown(f"#### {title}")
        if not values:
            st.caption(empty)
            return
        for item in values:
            st.markdown(f"**{item.label}**")
            st.caption(item.authority)


def render_dynamic_profile(view: CareerProfileView) -> None:
    st.markdown("### 你的动态职业画像")
    st.caption("它会随对话更新，但只有明确确认的信息才会进入长期理解。")
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
    st.caption(f"UserProfile v{profile['version']} · 等待你的明确确认")
    with st.expander("查看完整画像分类", expanded=True):
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
    left, right = st.columns(2)
    for index, (title, signals) in enumerate(groups):
        target = left if index % 2 == 0 else right
        with target:
            _render_labels(title, (item.label for item in signals))
    _render_labels("仍未知", (item.topic for item in record.uncertainties))


def render_match_insights(result: MatchResult, profile, record) -> None:
    st.header(f"{result.role_title} · Match Insights")
    st.caption("这些是多维证据关系，不是结论、总体匹配分或岗位排名。")
    for group in match_insight_groups(result, profile, record):
        with st.expander(
            f"{group.label} · {len(group.insights)}",
            expanded=bool(group.insights),
        ):
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
        badge.caption(view.status)
        st.markdown("**WHY · 为什么现在做**")
        st.write(view.why)
        st.markdown("**WHAT · 具体怎么做**")
        for step in view.what_to_do:
            st.markdown(f"- {step}")
        st.markdown("**EVIDENCE · 要留下什么证据**")
        st.write(view.expected_evidence)
        st.caption("关联洞察：" + "、".join(view.related_insight_ids))
        if view.needs_evidence_review:
            st.info("你表示已经做过；Orange 先标记为需要证据复核，不会自动确认能力。")
        selected = st.selectbox(
            "STATUS · 当前状态",
            ACTION_STATUS_OPTIONS,
            index=ACTION_STATUS_OPTIONS.index(view.status),
            key=f"{key}_status",
        )
        already_done = st.button("我其实已经做过", key=f"{key}_done")
        return selected, already_done


def render_actions(
    result: MatchResult,
    statuses: dict[str, str],
    evidence_review_ids: set[str],
) -> list[tuple[str, str, bool]]:
    st.header(f"{result.role_title} · 行动计划")
    st.caption("每项任务都来自已验证 ActionItem；界面只增加确定性的执行结构。")
    events: list[tuple[str, str, bool]] = []
    if not result.action_items:
        st.info("当前没有需要展示的已验证行动。")
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
        _render_labels("继续深入探索", view.continue_exploring)
    with columns[1]:
        _render_labels("保持开放", view.keep_open)
    with columns[2]:
        _render_labels("暂时不优先", view.deprioritized)
    _render_labels("还需要验证的问题", view.questions_to_validate)


def render_memory_summary(view: MemorySummaryView) -> None:
    st.header("Orange 对你的长期理解")
    st.info("Orange 只会把经过你明确确认的信息作为长期职业理解的一部分。")
    left, right = st.columns(2)
    with left:
        _render_labels("当前职业方向", view.current_directions)
        _render_labels("已确认能力", view.confirmed_capabilities)
        _render_labels("工作偏好", view.work_preferences)
        _render_labels("当前目标", view.current_goals)
    with right:
        _render_labels("你后来告诉 Orange", view.user_feedback, empty="还没有保存反馈")
        _render_labels("最近发生的变化", view.recent_changes, empty="暂无已确认变化")
        _render_labels("画像历史", view.profile_history)
    _render_labels("当前已确认的长期偏好", view.current_memory_preferences)
    _render_labels("历史偏好", view.historical_memory_preferences, empty="暂无被替代的历史偏好")
    if view.pending_profile_revision:
        st.warning(view.pending_profile_revision + "；长期 Memory 的更新不会自动确认画像。")


def render_role_memory(view: RoleMemoryView) -> None:
    if not view.statements:
        return
    with st.container(border=True):
        st.markdown("### 🍊 Orange 记得")
        st.caption("来自你之前确认的信息；它不会改变岗位事实或当前 MatchResult。")
        for statement in view.statements:
            st.markdown(f"- {statement}")
        with st.expander("查看依据"):
            for item in view.evidence:
                st.markdown(f"**{item.memory_type}** · {item.status}")
                st.write(item.content)
                st.caption("确认时间：" + item.confirmed_at)


def render_developer_trace(events: list[dict[str, object]]) -> None:
    with st.expander("开发者执行轨迹（安全）", expanded=False):
        if not events:
            st.caption("工作流尚未开始。")
            return
        for event in events:
            details = [str(event["event_type"])]
            for key in ("node", "status", "profile_version", "checkpoint_mode", "count"):
                if event.get(key) is not None:
                    details.append(f"{key}={event[key]}")
            st.code(" · ".join(details), language=None)
