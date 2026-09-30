"""Deterministic presentation mappings; no Orange business semantics live here."""

from __future__ import annotations

from dataclasses import dataclass

from data.models import (
    ActionItem,
    ActionType,
    JobIntelligenceRecord,
    JobRecord,
    MatchInsight,
    MatchRelationType,
    MatchResult,
    UserProfile,
)
from memory.models import MemoryRecord, MemoryType
from ui.conversation import ConversationStage, GuidedConversation


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


@dataclass(frozen=True)
class ProfileChipView:
    label: str
    authority: str


@dataclass(frozen=True)
class CareerProfileView:
    demonstrated_capabilities: tuple[ProfileChipView, ...]
    interests_and_work_style: tuple[ProfileChipView, ...]
    exploration_directions: tuple[ProfileChipView, ...]
    evidence_needs: tuple[ProfileChipView, ...]
    current_goals: tuple[ProfileChipView, ...]


@dataclass(frozen=True)
class CareerDirectionCardView:
    job_id: str
    title: str
    one_line: str
    why_explore: str
    validated_overlaps: tuple[str, ...]
    clarification_need: str


@dataclass(frozen=True)
class MatchInsightGroupView:
    relation_type: MatchRelationType
    label: str
    explanation: str
    insights: tuple[InsightView, ...]


@dataclass(frozen=True)
class ActionTaskView:
    action_id: str
    action_type: ActionType
    why: str
    what_to_do: tuple[str, ...]
    target: str
    expected_evidence: str
    related_insight_ids: tuple[str, ...]
    status: str
    needs_evidence_review: bool = False


@dataclass(frozen=True)
class ExplorationMapView:
    continue_exploring: tuple[str, ...]
    keep_open: tuple[str, ...]
    deprioritized: tuple[str, ...]
    questions_to_validate: tuple[str, ...]


@dataclass(frozen=True)
class MemorySummaryView:
    current_directions: tuple[str, ...]
    confirmed_capabilities: tuple[str, ...]
    work_preferences: tuple[str, ...]
    current_goals: tuple[str, ...]
    user_feedback: tuple[str, ...]
    recent_changes: tuple[str, ...]
    profile_history: tuple[str, ...]


AUTHORITY_EVIDENCE = "已有证据"
AUTHORITY_EXPRESSED = "用户刚刚表达"
AUTHORITY_PENDING = "待确认"
AUTHORITY_UNKNOWN = "尚不确定"

ROLE_ONE_LINE = {
    "job_001": "帮助团队理解用户问题，并把 AI 想法整理成可验证产品方案的人。",
    "job_007": "把 AI 能力真正接入产品和软件系统的人。",
    "job_013": "整理和分析数据，用清晰证据支持业务判断的人。",
}

ROLE_CLARIFICATION_PROMPTS = {
    "job_001": "你会不会愿意花较多时间理解需求、整理信息并写清楚产品方案？",
    "job_007": "你会不会享受反复调 API、处理边界情况、测试 AI 行为？",
    "job_013": "你会不会享受长时间整理数据、验证口径并从数据中寻找规律？",
}

ROLE_CLARIFICATION_OPTIONS = ("很喜欢", "可以接受", "不太喜欢", "没做过，不知道")

ASK_ORANGE_QUESTIONS = (
    "这个岗位平时到底做什么？",
    "我目前已经有哪些相关能力？",
    "我还缺哪些证据？",
    "我应该先做什么来验证自己是否喜欢它？",
    "和另一个方向最大的工作方式区别是什么？",
)

ACTION_STATUS_OPTIONS = ("未开始", "进行中", "已完成", "暂时跳过")


def _chips(values: list[str], authority: str) -> tuple[ProfileChipView, ...]:
    return tuple(ProfileChipView(label=value, authority=authority) for value in dict.fromkeys(values))


def career_profile_view(
    conversation: GuidedConversation,
    profile_payload: dict[str, object] | None = None,
) -> CareerProfileView:
    """Transform evidence-backed profile and session expressions without conflating them."""

    demonstrated: list[ProfileChipView] = []
    if profile_payload:
        demonstrated.extend(
            ProfileChipView(str(label), AUTHORITY_EVIDENCE)
            for label in profile_payload.get("skills", [])
        )
        demonstrated.extend(
            ProfileChipView(str(label), AUTHORITY_EVIDENCE)
            for label in profile_payload.get("strengths", [])
        )
    elif conversation.answer_for(ConversationStage.PROJECT_EVIDENCE) == "Campus Helper Prototype":
        demonstrated.append(ProfileChipView("校园信息问答原型", AUTHORITY_EVIDENCE))

    contributions = conversation.answer_for(ConversationStage.PROJECT_CONTRIBUTION)
    if isinstance(contributions, tuple):
        demonstrated.extend(
            ProfileChipView(value, AUTHORITY_EXPRESSED) for value in contributions
        )

    interests: list[str] = []
    for stage in (
        ConversationStage.ACTIVITY_PREFERENCE,
        ConversationStage.IMPLEMENTATION_DETAIL,
        ConversationStage.WORK_STYLE,
    ):
        value = conversation.answer_for(stage)
        if isinstance(value, str) and "不知道" not in value and "说不清楚" not in value:
            interests.append(value)
    ai_interests = conversation.answer_for(ConversationStage.AI_INTEREST)
    if isinstance(ai_interests, tuple):
        interests.extend(value for value in ai_interests if value != "我还不知道")

    direction_map = {
        "用现有 AI / LLM 做真正的应用": "AI 应用 / LLM 应用",
        "训练、优化模型本身": "机器学习工程",
        "分析数据和规律": "数据分析 / AI-enabled data",
        "研究新的算法或技术方法": "算法与应用研究",
        "思考 AI 应该解决什么用户问题": "AI 产品",
    }
    directions = [direction_map[value] for value in (ai_interests or ()) if value in direction_map]

    unknowns: list[str] = []
    if conversation.answer_for(ConversationStage.AI_INTEREST) in (None, ("我还不知道",)):
        unknowns.append("更具体的 AI 工作方式偏好")
    if conversation.answer_for(ConversationStage.WORK_STYLE) in (None, "目前还不知道"):
        unknowns.append("更适合投入的工作方式")
    if not demonstrated:
        unknowns.append("能够代表当前能力的项目证据")
    if profile_payload:
        unknowns.extend(str(value) for value in profile_payload.get("uncertainties", []))

    goal = conversation.answer_for(ConversationStage.CAREER_GOAL)
    goals = [] if goal is None or goal == "还没有明确答案" else [str(goal)]
    if profile_payload:
        goals.extend(
            str(item.get("label"))
            for item in profile_payload.get("goals", [])
            if isinstance(item, dict) and item.get("label")
        )
    return CareerProfileView(
        demonstrated_capabilities=tuple(dict.fromkeys(demonstrated)),
        interests_and_work_style=_chips(interests, AUTHORITY_EXPRESSED),
        exploration_directions=_chips(directions, AUTHORITY_PENDING),
        evidence_needs=_chips(unknowns, AUTHORITY_UNKNOWN),
        current_goals=_chips(goals, AUTHORITY_EXPRESSED),
    )


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


def match_insight_groups(
    result: MatchResult,
    profile: UserProfile,
    record: JobIntelligenceRecord,
) -> tuple[MatchInsightGroupView, ...]:
    explanations = {
        MatchRelationType.STRONG_ALIGNMENT: "已有直接证据支持这项交集。",
        MatchRelationType.PARTIAL_ALIGNMENT: "已有部分交集，但范围或深度仍需核对。",
        MatchRelationType.EVIDENCE_MISSING: "当前没有足够证据，不代表你不具备它。",
        MatchRelationType.CONFIRMED_GAP: "只有明确限制证据存在时才使用这一类。",
        MatchRelationType.EXPERIENCE_DEPTH_GAP: "已有基础证据，但岗位可能要求更深实践。",
        MatchRelationType.PREFERENCE_ALIGNMENT: "这是工作偏好的交集，不代表能力已经得到证明。",
        MatchRelationType.POTENTIAL_FRICTION: "这是值得进一步确认的工作方式，不代表你不适合。",
        MatchRelationType.UNKNOWN: "现有双方证据还不能支持结论。",
    }
    return tuple(
        MatchInsightGroupView(
            relation_type=relation,
            label=RELATION_LABELS[relation],
            explanation=explanations[relation],
            insights=tuple(insight_view(item, profile, record) for item in insights),
        )
        for relation, insights in grouped_insights(result)
    )


def career_direction_card_view(
    job: JobRecord,
    record: JobIntelligenceRecord,
    result: MatchResult,
    profile: UserProfile,
) -> CareerDirectionCardView:
    """Build a role card only from UI copy and validated domain relations."""

    overlap_insights = (
        list(result.alignments)
        + list(result.partial_alignments)
        + list(result.preference_alignments)
    )
    overlaps: list[str] = []
    for insight in overlap_insights[:3]:
        view = insight_view(insight, profile, record)
        labels = view.profile_signal_labels or view.job_signal_labels
        overlaps.extend(labels[:1])
    clarification = (
        list(result.evidence_gaps)
        + list(result.unknowns)
        + list(result.potential_frictions)
    )
    clarification_need = (
        clarification[0].title if clarification else "目前没有额外的已验证澄清项"
    )
    why_explore = (
        overlap_insights[0].title
        if overlap_insights
        else "可以继续了解岗位工作方式，再判断是否值得投入"
    )
    return CareerDirectionCardView(
        job_id=job.job_id,
        title=job.title,
        one_line=ROLE_ONE_LINE[job.job_id],
        why_explore=why_explore,
        validated_overlaps=tuple(dict.fromkeys(overlaps)),
        clarification_need=clarification_need,
    )


ACTION_RECIPES = {
    ActionType.VERIFY_EXISTING_CAPABILITY: (
        "回顾现有课程和项目，寻找实际使用记录",
        "找到后整理一个可核验例子；没有则如实记录",
    ),
    ActionType.BUILD_PORTFOLIO_EVIDENCE: (
        "设计一个范围明确、可以完成的小型成果",
        "完成后保留可展示结果和过程说明",
    ),
    ActionType.DEEPEN_CAPABILITY: (
        "先写清当前基础，再选择一个更深的练习目标",
        "用一个边界明确的练习验证深度变化",
    ),
    ActionType.GAIN_PRACTICAL_EXPERIENCE: (
        "选择一个接近真实工作约束的小任务",
        "完成后记录你的具体贡献和可复核结果",
    ),
    ActionType.CLARIFY_PREFERENCE: (
        "通过一次小型体验观察自己的投入感受",
        "记录喜欢、不喜欢和仍不确定的部分",
    ),
    ActionType.INVESTIGATE_JOB_UNKNOWN: (
        "针对岗位未知项收集一条可靠信息",
        "区分已确认事实和仍待验证的问题",
    ),
}


def action_task_view(
    action: ActionItem,
    result: MatchResult,
    *,
    status: str = "未开始",
    needs_evidence_review: bool = False,
) -> ActionTaskView:
    """Present an authoritative ActionItem with deterministic task scaffolding."""

    if status not in ACTION_STATUS_OPTIONS:
        raise ValueError("Unsupported action status.")
    insight_ids = {item.insight_id for item in result.insights()}
    if not set(action.related_insight_ids).issubset(insight_ids):
        raise ValueError("Action references an insight outside its MatchResult.")
    return ActionTaskView(
        action_id=action.action_id,
        action_type=action.action_type,
        why=action.rationale,
        what_to_do=(action.description, *ACTION_RECIPES[action.action_type]),
        target=action.target_label,
        expected_evidence=action.expected_evidence,
        related_insight_ids=tuple(action.related_insight_ids),
        status=status,
        needs_evidence_review=needs_evidence_review,
    )


def ask_orange_answer(
    question: str,
    record: JobIntelligenceRecord,
    result: MatchResult,
    profile: UserProfile,
) -> str:
    """Answer a predefined role question without any provider call."""

    if question not in ASK_ORANGE_QUESTIONS:
        raise ValueError("Only predefined role questions are supported.")
    if question == ASK_ORANGE_QUESTIONS[0]:
        labels = [item.label for item in record.actual_work[:2]]
        return "这个岗位的公开工作内容包括：" + "；".join(labels)
    if question == ASK_ORANGE_QUESTIONS[1]:
        labels: list[str] = []
        for insight in (
            *result.alignments,
            *result.partial_alignments,
            *result.preference_alignments,
        ):
            view = insight_view(insight, profile, record)
            labels.extend((view.profile_signal_labels or view.job_signal_labels)[:1])
        return "目前已验证的交集：" + ("、".join(dict.fromkeys(labels)) or "暂无直接证据")
    if question == ASK_ORANGE_QUESTIONS[2]:
        labels = [item.title for item in (*result.evidence_gaps, *result.unknowns)]
        return "还需要验证：" + ("；".join(labels[:3]) or "目前没有额外项")
    if question == ASK_ORANGE_QUESTIONS[3]:
        if result.action_items:
            return "可以先从这项已验证行动开始：" + result.action_items[0].description
        return "可以先做一次小型工作样本，再记录真实体验。"
    return "比较时只看已记录的实际工作、技术深度、产品互动、数据取向和协作方式，不做排名。"


def memory_summary_view(
    profile: UserProfile,
    active_memories: list[MemoryRecord],
    profile_history: list[UserProfile],
) -> MemorySummaryView:
    feedback = tuple(
        item.content
        for item in active_memories
        if item.memory_type == MemoryType.USER_FEEDBACK
    )
    return MemorySummaryView(
        current_directions=tuple(item.label for item in profile.interests),
        confirmed_capabilities=tuple(item.label for item in profile.skills),
        work_preferences=tuple(item.label for item in profile.career_preferences),
        current_goals=tuple(item.label for item in profile.goals),
        user_feedback=feedback,
        recent_changes=(),
        profile_history=tuple(
            f"画像 v{item.version}"
            + (" · 当前版本" if item.version == profile.version else " · 历史版本")
            for item in profile_history
        ),
    )


def role_location(job: JobRecord) -> str:
    return f"{job.city} · {job.region.value}"


def safe_error_message(category: str) -> str:
    return {
        "workflow_failure": "职业探索流程未能完成，请重新开始 Demo。",
        "validation_failure": "演示数据未通过验证，请重新开始 Demo。",
        "unexpected_failure": "Demo 暂时无法继续，请重新开始。",
    }.get(category, "Demo 暂时无法继续，请重新开始。")
