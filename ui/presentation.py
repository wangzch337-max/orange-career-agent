"""Deterministic presentation mappings; no Orange business semantics live here."""

from __future__ import annotations

from dataclasses import dataclass

from data.models import (
    JobIntelligenceRecord,
    JobRecord,
    MatchInsight,
    MatchRelationType,
    MatchResult,
    UserProfile,
)


RELATION_LABELS = {
    MatchRelationType.STRONG_ALIGNMENT: "明确契合",
    MatchRelationType.PARTIAL_ALIGNMENT: "部分契合",
    MatchRelationType.EVIDENCE_MISSING: "证据缺失",
    MatchRelationType.CONFIRMED_GAP: "已确认差距",
    MatchRelationType.EXPERIENCE_DEPTH_GAP: "经验深度差距",
    MatchRelationType.PREFERENCE_ALIGNMENT: "偏好契合",
    MatchRelationType.POTENTIAL_FRICTION: "潜在摩擦",
    MatchRelationType.UNKNOWN: "尚不确定",
}

MATCH_GROUPS = (
    ("alignments", MatchRelationType.STRONG_ALIGNMENT),
    ("partial_alignments", MatchRelationType.PARTIAL_ALIGNMENT),
    ("evidence_gaps", MatchRelationType.EVIDENCE_MISSING),
    ("confirmed_gaps", MatchRelationType.CONFIRMED_GAP),
    ("experience_depth_gaps", MatchRelationType.EXPERIENCE_DEPTH_GAP),
    ("preference_alignments", MatchRelationType.PREFERENCE_ALIGNMENT),
    ("potential_frictions", MatchRelationType.POTENTIAL_FRICTION),
    ("unknowns", MatchRelationType.UNKNOWN),
)

GOAL_TYPE_LABELS = {
    "career_goal": "职业目标",
    "project_goal": "项目目标",
    "learning_goal": "学习目标",
}


@dataclass(frozen=True)
class InsightView:
    insight_id: str
    relation_label: str
    dimension_label: str
    title: str
    description: str
    confidence: float
    profile_signal_labels: tuple[str, ...]
    job_signal_labels: tuple[str, ...]
    profile_evidence_ids: tuple[str, ...]
    job_evidence_ids: tuple[str, ...]


def profile_signal_labels(profile: UserProfile) -> dict[str, str]:
    result: dict[str, str] = {}
    groups = (
        (profile.skills, "skill_id", "label"),
        (profile.interests, "interest_id", "label"),
        (profile.values, "value_id", "label"),
        (profile.goals, "goal_id", "label"),
        (profile.strengths, "statement_id", "text"),
        (profile.development_areas, "statement_id", "text"),
        (profile.career_preferences, "preference_id", "label"),
    )
    for items, id_field, label_field in groups:
        for item in items:
            result[getattr(item, id_field)] = getattr(item, label_field)
    return result


def job_signal_labels(record: JobIntelligenceRecord) -> dict[str, str]:
    result = {
        signal.signal_id: signal.label
        for signals in (
            record.actual_work,
            record.required_capabilities,
            record.preferred_capabilities,
            record.technology_signals,
            record.work_style,
            record.collaboration_context,
            record.growth_exposure,
            record.potential_friction,
        )
        for signal in signals
    }
    result.update(
        {
            item.uncertainty_id: item.topic
            for item in record.uncertainties
            if item.uncertainty_id is not None
        }
    )
    return result


def insight_view(
    insight: MatchInsight,
    profile: UserProfile,
    record: JobIntelligenceRecord,
) -> InsightView:
    profile_labels = profile_signal_labels(profile)
    job_labels = job_signal_labels(record)
    link = insight.evidence_link
    return InsightView(
        insight_id=insight.insight_id,
        relation_label=RELATION_LABELS[insight.relation_type],
        dimension_label=insight.dimension.display_name_zh,
        title=insight.title,
        description=insight.description,
        confidence=insight.confidence,
        profile_signal_labels=tuple(
            profile_labels[item]
            for item in link.profile_signal_ids
            if item in profile_labels
        ),
        job_signal_labels=tuple(
            job_labels[item] for item in link.job_signal_ids if item in job_labels
        ),
        profile_evidence_ids=tuple(link.profile_evidence_ids),
        job_evidence_ids=tuple(link.job_evidence_ids),
    )


def grouped_insights(
    result: MatchResult,
) -> list[tuple[MatchRelationType, list[MatchInsight]]]:
    return [
        (relation, list(getattr(result, field_name)))
        for field_name, relation in MATCH_GROUPS
    ]


def role_location(job: JobRecord) -> str:
    return f"{job.city} · {job.region.value}"


def safe_error_message(category: str) -> str:
    return {
        "workflow_failure": "职业探索流程未能完成，请重新开始 Demo。",
        "validation_failure": "演示数据未通过验证，请重新开始 Demo。",
        "unexpected_failure": "Demo 暂时无法继续，请重新开始。",
    }.get(category, "Demo 暂时无法继续，请重新开始。")
