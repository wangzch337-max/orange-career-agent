"""One semantic proposal; deterministic references, safety, IDs and presentation."""

import json
from pathlib import Path
import re
import unicodedata

from providers.models import GenerationOptions, LLMMessage, MessageRole
from resume_evidence.context import normalize
from career_discovery.context import BACKGROUND, INTENT, clean, fingerprint
from career_discovery.models import (CapabilityKind, CareerDirectionCandidate, Confidence,
    ConsiderationKind, DiscoveryError, DiscoveryProposal, GoalRelation, Status,
    TransferableCapability, TransitionConsideration)

PROMPT_NAME = "career_direction_discovery"
PROMPT_VERSION = "v1"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "config/prompts/career_direction_discovery_v1.md"
CAPABILITY_LABELS = {
    CapabilityKind.DOCUMENTATION: "结构化记录与文档整理",
    CapabilityKind.COMMUNICATION: "利益相关方沟通",
    CapabilityKind.ANALYSIS: "分析与推理",
    CapabilityKind.COORDINATION: "流程协调",
    CapabilityKind.DOMAIN: "领域知识的潜在迁移",
    CapabilityKind.LEARNING: "学习基础的潜在迁移",
    CapabilityKind.CUSTOMER: "理解服务对象",
    CapabilityKind.QUALITY: "质量与细节关注",
}
CONSIDERATION_LABELS = {
    ConsiderationKind.DOMAIN_TRANSFER: "领域迁移仍需验证",
    ConsiderationKind.EXPERIENCE_DEPTH: "相关经验深度尚待了解",
    ConsiderationKind.QUALIFICATION: "来源中的资格条件需要进一步核实",
    ConsiderationKind.INDUSTRY_CHANGE: "跨行业情境需要比较",
    ConsiderationKind.RESPONSIBILITY: "职责变化需要了解",
    ConsiderationKind.WORK_STYLE: "工作方式需要比较",
    ConsiderationKind.LOCATION: "需要保留当前地点限制",
    ConsiderationKind.INTENT: "探索意向仍可改变",
    ConsiderationKind.EVIDENCE: "可进一步收集相关证据",
}
# Reject unsafe text, do not repair it. Not a general natural-language truth judge.
_UNSAFE = re.compile(r"(?i)https?://|www\.|salary|薪资|年薪|成功率|success.probability|best.fit|\bbest\b|最适合|最佳|首选|推荐指数|排名|\b(?:score|rating|ranking|recommended)\b|overall.score|匹配分|评分|分数|适配度|\d+(?:\.\d+)?\s*%|\d+\s*/\s*\d+|[★☆⭐]|#\s*1|confirmed.gap|确认缺口|缺乏|缺少|不足|薄弱|不会|不擅长|不具备|无法胜任|guarantee|保证就业|没有能力|\b(?:missing|insufficient|weakness|shortfall)\b|deficien|lack(?:s|ing)?\b|can.t\b")
_ROLE = re.compile(r"(?i)\b(?:intern|internship|manager|engineer|analyst|associate|director|officer|nurse)\b|实习生|工程师|分析师|经理|专员|总监|护士")
_INFLATION = re.compile(r"(?i)\b(?:advanced|expert|mastery|senior|led|lead|owned|ownership|enterprise|production|pytorch|tensorflow|mlops|kpi|p&l|roadmap)\b|精通|高级|资深|主导|负责战略|商业化|大规模|生产级|端到端|领导|掌握")
_NEGATIVE = re.compile(r"(?i)\b(?:not|never|no|without|limited|supported|assisted)\b|未|没有|不|协助|支持|有限")


def checked_text(text, *, sources=(), direction=False):
    value, changed = clean(text)
    if changed or value != text.strip() or _UNSAFE.search(value):
        raise DiscoveryError(Status.INVALID_OUTPUT)
    if direction and (_ROLE.search(value) or re.search(r"(?i)company|公司|职位|招聘|job(?:s|_id)?\b|有限公司", value)):
        raise DiscoveryError(Status.INVALID_OUTPUT)
    if _INFLATION.search(value) and not any(
        s.origin == "confirmed_profile" and s.category in BACKGROUND and any(
            normalize(value) == normalize(atom) and not _NEGATIVE.search(atom)
            for atom in s.text.split(" · ")) for s in sources):
        raise DiscoveryError(Status.INVALID_OUTPUT)
    return value


def identity(proposal):
    # Normalize only identity, never rewrite an unsupported material claim.
    family = " ".join(unicodedata.normalize("NFKC", proposal.direction_family).casefold().split())
    title = " ".join(unicodedata.normalize("NFKC", proposal.title).casefold().split())
    return family, title


def validate(proposal, context):
    proposal = DiscoveryProposal.model_validate(proposal.model_dump())
    by_ref = {s.ref: s for s in context.sources}
    current = {s.ref for s in context.sources if s.origin == "current_explicit"}
    candidates, seen = [], {}

    def refs(values):
        if any(ref not in by_ref for ref in values):
            raise DiscoveryError(Status.INVALID_REFERENCE)
        return [by_ref[ref] for ref in dict.fromkeys(values)]

    def anchor(value):
        source = refs((value.source_ref,))[0]
        # Whole normalized field only: a contained substring could remove
        # negation, support level, chronology or ownership qualifiers.
        if value.excerpt != source.text and value.excerpt not in source.text.split(" · "):
            raise DiscoveryError(Status.INVALID_REFERENCE)
        return source

    for item in proposal.directions:
        sources = refs(item.source_refs)
        referenced = {s.ref for s in sources}
        if not current.issubset(referenced) or not any(s.origin == "confirmed_profile" and s.category in BACKGROUND for s in sources):
            raise DiscoveryError(Status.INVALID_REFERENCE)
        checked_text(item.title, sources=sources, direction=True)
        checked_text(item.direction_family, sources=sources, direction=True)
        key = identity(item)
        if key in seen:
            if item.model_dump() != seen[key].model_dump():
                raise DiscoveryError(Status.INVALID_OUTPUT)
            continue  # Exact duplicate only; conflicting duplicate is not repaired.
        seen[key] = item
        direction_id = "direction_" + fingerprint(key)[:24]
        capabilities, cap_seen = [], {}
        for capability in item.transferable_capabilities:
            anchored = [anchor(a) for a in capability.anchors]
            if any(s.ref not in referenced or s.origin != "confirmed_profile" or s.category not in BACKGROUND for s in anchored):
                raise DiscoveryError(Status.INVALID_REFERENCE)
            # Canonical evidence is displayed separately from tentative interpretation.
            explanation = "来源记录：“" + "；".join(a.excerpt for a in capability.anchors) + "”。这只是待验证的迁移解释，不表示已证明该方向的任职能力。"
            cap_refs = tuple(sorted({s.ref for s in anchored}))
            rendered = TransferableCapability(
                capability_id="capability_" + fingerprint((direction_id, capability.interpretation.value, cap_refs))[:24],
                label=CAPABILITY_LABELS[capability.interpretation], derived_from_refs=cap_refs,
                relevance_to_direction=capability.relevance_to_direction,
                uncertainty=capability.uncertainty, safe_explanation=explanation)
            if rendered.capability_id in cap_seen and cap_seen[rendered.capability_id] != rendered:
                raise DiscoveryError(Status.INVALID_OUTPUT)
            cap_seen[rendered.capability_id] = rendered
            capabilities.append(rendered)
        considerations, associated = [], list(sources)
        for consideration in item.transition_considerations:
            linked = refs(consideration.source_refs)
            if not set(consideration.source_refs).issubset(referenced):
                raise DiscoveryError(Status.INVALID_REFERENCE)
            checked_text(consideration.topic, sources=linked)
            if consideration.anchor and (consideration.anchor.source_ref not in consideration.source_refs):
                raise DiscoveryError(Status.INVALID_REFERENCE)
            backed = anchor(consideration.anchor) if consideration.anchor else None
            if consideration.state == "source_supported" and backed is None:
                raise DiscoveryError(Status.INVALID_OUTPUT)
            if consideration.kind == ConsiderationKind.QUALIFICATION:
                if (backed is None or backed.category not in {"constraints", "professional_qualifications", "certifications"} or
                    not re.search(r"(?i)require|licen[cs]|资格|执照|必须|需持|限制", consideration.anchor.excerpt)):
                    raise DiscoveryError(Status.INVALID_OUTPUT)
            if re.search(r"(?i)project|github|项目", consideration.topic) and backed is None:
                raise DiscoveryError(Status.INVALID_OUTPUT)
            description = CONSIDERATION_LABELS[consideration.kind] + "：" + (
                "来源记录“" + consideration.anchor.excerpt + "”" if backed else "尚待了解“" + consideration.topic + "”")
            considerations.append(TransitionConsideration(kind=consideration.kind,
                source_refs=tuple(sorted(set(consideration.source_refs))), description=description, state=consideration.state))
        # User constraints cannot silently disappear from a provider proposal.
        for source in context.sources:
            if source.origin == "confirmed_profile" and source.category in {"constraints", "location_preferences", "work_style_preferences"}:
                if source.ref not in {s.ref for s in associated}:
                    associated.append(source)
                kind = {"constraints": ConsiderationKind.RESPONSIBILITY, "location_preferences": ConsiderationKind.LOCATION,
                        "work_style_preferences": ConsiderationKind.WORK_STYLE}[source.category]
                considerations.append(TransitionConsideration(kind=kind, source_refs=(source.ref,),
                    description="需在后续探索中保留的已确认条件：“" + source.text + "”", state="source_supported"))
        historical_intent = [s for s in context.sources if (s.origin == "confirmed_profile" and (
                             s.category == "transition_intent" or s.category == "goals" and s.goal_type == "career_goal")) or
                             (s.origin == "confirmed_memory" and s.category in {"goal", "career_preference"})][:4]
        if current and historical_intent:
            explicit = [by_ref[r] for r in sorted(current)]
            associated.extend(s for s in historical_intent if s.ref not in {a.ref for a in associated})
            considerations.append(TransitionConsideration(kind=ConsiderationKind.INTENT,
                source_refs=tuple(s.ref for s in [*explicit, *historical_intent]), state="unknown",
                description="本轮探索表述：“" + "；".join(s.text for s in explicit) + "”；历史已确认目标/偏好：“" +
                    "；".join(s.text for s in historical_intent) + "”。分别保留，不自动合并；是否代表长期意向改变尚未确认。"))
        topics = []
        for values in (item.uncertainties, item.evidence_gaps):
            for value in values:
                checked_text(value, sources=sources)
                if re.search(r"(?i)project|github|项目", value):
                    raise DiscoveryError(Status.INVALID_OUTPUT)
            topics.append(tuple("尚待核实：" + value for value in values))
        intents = [s for s in sources if s.origin == "current_explicit" or s.category in INTENT and
                   (s.category != "goals" or s.goal_type == "career_goal")]
        if item.goal_relation in {GoalRelation.ALIGNED, GoalRelation.PARTIALLY_ALIGNED} and not intents:
            raise DiscoveryError(Status.INVALID_OUTPUT)
        if item.goal_relation == GoalRelation.TENSION and not (current and any(s.origin in {"confirmed_profile", "confirmed_memory"} and s.category in INTENT | {"goal", "career_preference"} for s in sources)):
            raise DiscoveryError(Status.INVALID_OUTPUT)
        if item.confidence == Confidence.GROUNDED and (context.partial or any(s.uncertainty != "none" for s in sources)):
            raise DiscoveryError(Status.INVALID_OUTPUT)
        p_refs = tuple(sorted({r for s in associated if s.origin == "confirmed_profile" for r in s.origin_refs}))
        m_refs = tuple(sorted({r for s in associated if s.origin == "confirmed_memory" for r in s.origin_refs}))
        why = "可从已确认记录“" + "；".join(s.text for s in sources if s.origin == "confirmed_profile" and s.category in BACKGROUND) + "”出发探索此方向；迁移关系仍待你审阅。"
        if capabilities:
            why += "候选解释是把“" + "、".join(sorted({c.label for c in capabilities})) + "”作为这一方向的潜在迁移线索，不表示已证明该方向的任职能力。"
        if current:
            why += "本轮探索意向优先；历史目标和记忆仅作背景，不代表它们已被更新。"
        candidates.append(CareerDirectionCandidate(direction_id=direction_id, title=item.title,
            direction_family=item.direction_family, summary="这是待审阅的方向候选，不是具体岗位或已确认职业目标。",
            why_explore=why, supporting_profile_refs=p_refs, supporting_memory_refs=m_refs,
            current_signal_refs=tuple(sorted(current)), recent_context_refs=tuple(sorted(s.ref for s in sources if s.origin == "recent_user_context")),
            transferable_capabilities=tuple(sorted({c.capability_id: c for c in capabilities}.values(), key=lambda c: c.capability_id)),
            transition_considerations=tuple(considerations), uncertainties=topics[0], evidence_gaps=topics[1],
            goal_relation=item.goal_relation, confidence=item.confidence))
    return tuple(sorted(candidates, key=lambda d: (normalize(d.direction_family), normalize(d.title), d.direction_id)))


class CareerDiscoveryService:
    def discover(self, provider, context):
        messages = [LLMMessage(role=MessageRole.SYSTEM, content=PROMPT_PATH.read_text(encoding="utf-8")),
                    LLMMessage(role=MessageRole.USER, content=json.dumps(context.provider_payload(), ensure_ascii=False, separators=(",", ":")))]
        response = provider.generate_structured(messages, DiscoveryProposal,
            GenerationOptions(model="qwen3.8-flash", thinking_enabled=False, max_retries=0, max_output_tokens=4000),
            prompt_name=PROMPT_NAME, prompt_version=PROMPT_VERSION)
        if (response.retry_count or response.thinking_enabled or response.provider not in {"fake", "qwen"} or
            response.model != "qwen3.8-flash" or response.prompt_name != PROMPT_NAME or response.prompt_version != PROMPT_VERSION):
            raise DiscoveryError(Status.INVALID_OUTPUT)
        return validate(response.data, context), response.safe_metadata()
