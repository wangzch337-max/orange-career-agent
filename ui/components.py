"""Reusable Streamlit renderers for validated Orange presentation data."""

from __future__ import annotations

from typing import Iterable

import streamlit as st

from data.models import JobIntelligenceRecord, JobRecord, MatchRelationType, MatchResult
from ui.presentation import (
    GOAL_TYPE_LABELS,
    RELATION_LABELS,
    grouped_insights,
    insight_view,
    role_location,
)


def render_public_demo_banner() -> None:
    st.info(
        "当前为公开演示模式：使用虚构数据和离线模型，不包含真实个人信息。",
        icon="🛡️",
    )


def render_progress(current_step: int, total_steps: int = 7) -> None:
    st.caption(f"步骤 {current_step} / {total_steps}")
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


def render_profile_review(payload: dict[str, object]) -> None:
    profile = payload["profile"]
    if not isinstance(profile, dict):
        raise ValueError("Invalid safe profile review payload")
    st.header("认识自己 · 画像确认")
    st.caption(f"UserProfile v{profile['version']} · 等待你的明确确认")
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
    st.caption("这里展示的是安全画像摘要，不展示原始输入、Prompt 或隐藏推理。")


def render_role_card(job: JobRecord, record: JobIntelligenceRecord, *, key: str) -> bool:
    with st.container(border=True):
        st.subheader(job.title)
        st.caption(f"{job.role_family.value} · {role_location(job)}")
        if record.actual_work:
            st.write(record.actual_work[0].label)
        return st.button("查看岗位", key=key, use_container_width=True)


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
    st.header(f"{result.role_title} · 匹配洞察")
    st.caption("以下是独立的证据关系，不是总体匹配分或岗位排名。")
    for relation, insights in grouped_insights(result):
        st.subheader(RELATION_LABELS[relation])
        if not insights:
            st.caption("当前没有此类已验证关系。")
            continue
        if relation == MatchRelationType.EVIDENCE_MISSING:
            st.info("当前没有足够证据证明这一能力，不代表你不具备它。")
        for insight in insights:
            view = insight_view(insight, profile, record)
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
                    st.write(
                        "画像证据 ID："
                        + ("、".join(view.profile_evidence_ids) or "无")
                    )
                    st.write(
                        "岗位证据 ID：" + ("、".join(view.job_evidence_ids) or "无")
                    )


def render_actions(result: MatchResult) -> None:
    st.header(f"{result.role_title} · 行动计划")
    st.caption("行动文字来自已验证的确定性 ActionRenderer 输出，UI 不重新生成建议。")
    if not result.action_items:
        st.info("当前没有需要展示的已验证行动。")
        return
    for action in result.action_items:
        with st.container(border=True):
            st.markdown(f"#### {action.action_type.value}")
            st.write(action.description)
            st.write(f"**目标：** {action.target_label}")
            st.write(f"**预期证据：** {action.expected_evidence}")
            st.caption("关联洞察：" + "、".join(action.related_insight_ids))


def render_developer_trace(events: list[dict[str, object]]) -> None:
    with st.expander("开发者执行轨迹（安全）"):
        if not events:
            st.caption("工作流尚未开始。")
            return
        for event in events:
            details = [str(event["event_type"])]
            for key in ("node", "status", "profile_version", "checkpoint_mode", "count"):
                if event.get(key) is not None:
                    details.append(f"{key}={event[key]}")
            st.code(" · ".join(details), language=None)
