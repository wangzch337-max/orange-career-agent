"""Deterministic supported candidates, coarse priorities and semantic identities."""

import hashlib
import re

from clarification.context import direction_value, explicit_intent
from clarification.models import ClarificationNeed
from clarification.policy import MAX_NEEDS, ReasonCode as RC
from resume_evidence.context import normalize

PRIORITIES = {"conflict": 0, "direction": 1, "ownership": 2, "capability": 3, "detail": 4}


def _key(value):
    return hashlib.sha256(value.encode()).hexdigest()[:20]


def _anchor(source):
    # Context wording, not a new job/skill label. Strip prompt-like punctuation.
    return re.sub(r"[\n\r「」<>!?？]\s*", " ", source.text.split(" · ")[0])[:65].strip()


def generate_needs(context, *, closed_need_ids=(), closed_topics=()):
    sources, candidates = context.sources, []
    explicit = [s for s in sources if s.explicit_goal and s.authority == "explicit_user_input"]
    profile_goals = [s for s in sources if s.kind == "profile" and s.explicit_goal]
    resume_goals = [s for s in sources if s.kind == "resume" and s.explicit_goal]
    historical = [s for s in sources if s.kind == "memory" and s.category in {"goal", "career_preference"}]

    def add(reason, topic, refs, priority, uncertainty, question, replies=(), conflict="none", revision=""):
        need_id = "need_" + _key(topic + "|" + reason.value + "|" + revision)
        # Only a genuinely different supported conflict can reopen a closed topic.
        if need_id in closed_need_ids or (topic in closed_topics and reason != RC.PROFILE_RESUME_CONFLICT):
            return
        candidates.append(ClarificationNeed(need_id=need_id, topic=topic, reason_code=reason,
            source_refs=tuple(dict.fromkeys(refs))[:8], priority=priority, uncertainty=uncertainty,
            conflict_summary=conflict, allowed_questions=(question,), allowed_replies=tuple(replies)))

    current = [s for s in explicit if s.kind == "current"][:1] or explicit[-1:] or resume_goals[-1:]
    if current and profile_goals:
        now = current[0]
        current_value = direction_value(now.text)
        previous = profile_goals[0]
        old_value = direction_value(previous.text)
        already_supported = any(current_value == direction_value(goal.text) or
            current_value in direction_value(goal.text) or direction_value(goal.text) in current_value for goal in profile_goals)
        # Exact structured/explicit difference, not semantic similarity. A
        # difference is only a possible change; we do not choose the truth.
        if not already_supported:
            revision = "|".join((current_value, old_value))
            question = (f"你当前提到「{_anchor(now)}」，之前确认的是「{_anchor(previous)}」，"
                        "现在的意向有变化，还是仍在同时考虑？")
            add(RC.PROFILE_RESUME_CONFLICT, "career_direction", [now.ref, previous.ref], "conflict",
                "possible_change", question, ("当前意向有变化", "两个方向都在考虑", "我还不确定"),
                "different_explicit_intents", revision)
    elif explicit and historical:
        now, old = explicit[-1], historical[0]
        now_value, old_value = direction_value(now.text), direction_value(old.text)
        if now_value != old_value and now_value not in old_value and old_value not in now_value:
            add(RC.OUTDATED_INFORMATION, "career_direction", [now.ref, old.ref], "conflict",
                "possible_change", "你当前表达了新的意向，之前的历史偏好目前还适用吗？",
                ("已不适用", "仍在同时考虑", "我还不确定"), "historical_information_may_be_stale")
    explicit_uncertainty = any(s.ambiguity == "explicit_uncertainty" and
        (s.kind == "current" or (s.kind == "answer" and s.category == "career_direction")) for s in sources)
    current_source = next((s for s in sources if s.kind == "current"), None)
    transition = current_source is not None and not current_source.explicit_goal and bool(
        re.search(r"转行|职业转换|换方向|career change", current_source.text, re.I))
    if transition:
        add(RC.AMBIGUOUS_TRANSITION_INTENT, "career_direction", [current_source.ref], "direction", "ambiguous",
            "你提到职业转向，目前是明确的转换计划，还是仍在探索不同方向？",
            ("已经有明确计划", "仍在探索", "我还不确定"))
    if current_source and current_source.ambiguity == "explicit_uncertainty" and re.search(
            r"工作偏好|工作环境|工作方式|work preference", current_source.text, re.I):
        add(RC.CURRENT_PREFERENCE_UNKNOWN, "current_work_preference", [current_source.ref], "direction", "unknown",
            "对于工作方式或环境，你目前更看重什么，还是还没有明确偏好？", ("还没有明确偏好",))
    if not (explicit or profile_goals or resume_goals or explicit_uncertainty or transition):
        background = next((s for s in sources if s.kind == "resume" and s.category == "work_experience"), None)
        background = background or next((s for s in sources if s.kind == "resume"), None)
        if background:
            add(RC.MISSING_GOAL, "career_direction", [background.ref], "direction", "unknown",
                f"结合简历里的「{_anchor(background)}」，你现在希望继续原领域、探索转向，还是还没确定方向？",
                ("想继续原领域", "正在探索转向", "我还没想好"))
    # No completeness checklist. Only explicitly flagged ambiguity gets a need.
    for source in sources:
        if source.kind != "resume" or source.ambiguity == "none":
            continue
        label = _anchor(source)
        # Semantic topic is evidence scope/category, never question wording.
        topic = f"{source.category}:{source.semantic_scope}"
        if source.ambiguity in {"unclear_ownership", "ambiguous_project_work_boundary"}:
            achievement = source.category in {"achievements", "business_metrics"}
            reason = RC.UNCLEAR_ACHIEVEMENT_OWNERSHIP if achievement else RC.AMBIGUOUS_RESPONSIBILITY
            question = (f"「{label}」这项结果中，你个人承担的工作和团队贡献分别是什么？" if achievement else
                        f"在「{label}」这段经历中，你主要负责哪些工作，属于主导、共同实施还是配合支持？")
            add(reason, topic, [source.ref], "ownership", "ambiguous", question,
                ("主要负责", "共同参与", "配合支持", "我还不确定"))
        elif source.ambiguity == "unclear_proficiency":
            # Mere mention is insufficient. Require another source explicitly
            # linking this capability to a goal, question or actual responsibility.
            material = any(label and normalize(label) in normalize(other.text) for other in sources
                if other.ref != source.ref and (other.explicit_goal or other.kind == "current" or
                                               other.category in {"work_experience", "responsibilities"}))
            known_depth = any(other.kind == "profile" and other.category == "skills" and other.detail_known and
                              normalize(other.text) == normalize(label) for other in sources)
            if material and not known_depth:
                reason = RC.UNCLEAR_DOMAIN_DEPTH if source.category == "domain_knowledge" else RC.UNCLEAR_SKILL_DEPTH
                add(reason, topic, [source.ref], "capability", "ambiguous",
                    f"对于「{label}」，你目前能独立完成哪些具体工作？", ("能独立完成", "在指导下完成", "我还不确定"))
        elif source.ambiguity == "unclear_dates":
            add(RC.OUTDATED_INFORMATION, topic, [source.ref], "detail", "ambiguous",
                f"「{label}」这项经历的时间和目前状态是怎样的？")
        elif source.ambiguity in {"overlapping_roles", "other", "unclear_organization"}:
            add(RC.INSUFFICIENT_ROLE_CONTEXT, topic, [source.ref], "detail", "ambiguous",
                f"「{label}」这段经历里，你的实际角色和工作范围是什么？")
    unique = {candidate.need_id: candidate for candidate in candidates}
    return tuple(sorted(unique.values(), key=lambda n: (PRIORITIES[n.priority], n.need_id))[:MAX_NEEDS])


def highest_value_needs(needs):
    if not needs:
        return ()
    best = min(PRIORITIES[need.priority] for need in needs)
    return tuple(need for need in needs if PRIORITIES[need.priority] == best)
