"""Bounded whole-fact projection of CURRENT confirmed authority only."""

from dataclasses import dataclass, field
import hashlib
import json
import re

from data.models import ProfileStatus, UserProfile
from memory.integration import MemoryContextCoordinator
from memory.models import MemoryConsumer, MemoryStatus, MemoryUseCase
from profile_refinement.context import entry_id
from clarification.context import explicit_intent, explicitly_uncertain
from resume_evidence.context import minimize_text, normalize
from ui.conversation_store import _no_credentials
from career_discovery.models import (Binding, CareerDiscoveryContext, ClarificationNeed,
    DiscoveryError, Readiness, Source, Status)

MAX_PROFILE_FACTS = 44
MAX_PROFILE_CHARS = 12000
MAX_MEMORY_CHARS = 1800
MAX_CURRENT_CHARS = 1200
MAX_RECENT_MESSAGES = 4
MAX_RECENT_CHARS = 1600
MAX_SOURCE_CHARS = 1200
MAX_JSON_CHARS = 20000
# Optional projects; no university, technical stack or early-career priority.
PROFILE_CATEGORIES = ("goals", "transition_intent", "constraints",
    "location_preferences", "work_style_preferences", "work_experience", "skills", "domain_knowledge",
    "achievements", "certifications", "professional_qualifications", "languages",
    "interests", "career_preferences", "role_interests", "industry_interests", "values", "education",
    "tools", "strengths", "projects", "collaboration", "leadership", "research", "uncertainties")
BACKGROUND = {"work_experience", "education", "skills", "domain_knowledge", "achievements",
              "certifications", "professional_qualifications", "projects", "tools", "strengths"}
INTENT = {"goals", "interests", "career_preferences", "role_interests", "industry_interests", "transition_intent"}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def clean(text):
    _no_credentials(text)
    value, changed = minimize_text(text)
    return value.strip(), changed


@dataclass(frozen=True)
class DiscoveryInputs:
    owner_scope_id: str
    conversation_id: str
    subject_id: str
    profile: UserProfile | None = field(default=None, repr=False)
    memory: object | None = field(default=None, repr=False)
    recent: tuple[tuple[str, str], ...] = field(default=(), repr=False)
    current_statement: str = field(default="", repr=False)


def workspace_inputs(workspace, *, current_statement="", include_memory=False):
    if workspace._closed:
        raise DiscoveryError(Status.STALE)
    workspace.store.get_thread(workspace.owner_scope_id, workspace.thread.thread_id)
    profile = workspace.memory_service.get_current_confirmed_profile(workspace.subject_id)
    memory = None
    if include_memory and profile is not None:
        query, _ = clean(current_statement)
        # Never slice a material statement into a changed claim.
        query = query if 0 < len(query) <= 500 else "职业目标 职业偏好 职业探索"
        memory = MemoryContextCoordinator(workspace.memory_service).retrieve(
            subject_id=workspace.subject_id, use_case=MemoryUseCase.CAREER_DIRECTION_DISCOVERY,
            consumer=MemoryConsumer.CAREER_DIRECTION_DISCOVERY_SERVICE, query=query)
    # Only user messages from the active owned conversation, never full history.
    recent = tuple((m.role, m.content) for m in workspace.chat.messages[-MAX_RECENT_MESSAGES:])
    return DiscoveryInputs(workspace.owner_scope_id, workspace.thread.thread_id, workspace.subject_id,
                           profile, memory, recent, current_statement)


def bind(inputs, request_id, memory_fingerprints=()):
    profile = inputs.profile
    if profile is None:
        raise DiscoveryError(Status.INVALID_CONTEXT)
    try:
        profile = UserProfile.model_validate(profile.model_dump())
    except Exception:
        raise DiscoveryError(Status.INVALID_CONTEXT) from None
    if not profile.confirmed or profile.status != ProfileStatus.CONFIRMED:
        raise DiscoveryError(Status.INVALID_CONTEXT)
    return Binding(owner_scope_id=inputs.owner_scope_id, conversation_id=inputs.conversation_id,
        subject_id=inputs.subject_id, request_id=request_id, profile_id=profile.profile_id,
        profile_version=profile.version, profile_fingerprint=fingerprint(profile.model_dump(mode="json")),
        statement_fingerprint=fingerprint(inputs.current_statement), recent_fingerprint=fingerprint(inputs.recent),
        memory_fingerprints=memory_fingerprints)


class CareerDiscoveryContextBuilder:
    def build(self, inputs, request_id):
        bind(inputs, request_id)
        sources, partial = [], False
        prefix = fingerprint((inputs.owner_scope_id, inputs.conversation_id, request_id))[:16]

        def add(origin, category, text, *, origin_refs=(), evidence_refs=(), uncertainty="none", goal_type=None):
            nonlocal partial
            value, changed = clean(text)
            partial |= changed
            if not value or len(value) > MAX_SOURCE_CHARS:
                partial = True
                return False
            source = Source(ref=f"src_{prefix}_{len(sources):03d}", origin=origin, category=category,
                text=value, origin_refs=origin_refs, evidence_refs=evidence_refs, uncertainty=uncertainty,
                goal_type=goal_type)
            candidate = CareerDiscoveryContext(request_id=request_id, sources=tuple([*sources, source]), partial=partial)
            if len(json.dumps(candidate.provider_payload(), ensure_ascii=False, separators=(",", ":"))) > MAX_JSON_CHARS:
                partial = True
                return False
            sources.append(source)
            return True

        if inputs.current_statement:
            if len(inputs.current_statement) <= MAX_CURRENT_CHARS:
                add("current_explicit", "current_intent", inputs.current_statement,
                    uncertainty="explicit_uncertainty" if explicitly_uncertain(inputs.current_statement) else "none")
            else:
                raise DiscoveryError(Status.INVALID_CONTEXT)
            if not any(s.origin == "current_explicit" for s in sources):
                raise DiscoveryError(Status.INVALID_CONTEXT)
        profile_chars, profile_count = 0, 0
        for category in PROFILE_CATEGORIES:
            for item in getattr(inputs.profile, category):
                if not item.confirmed_by_user:
                    continue
                label = getattr(item, "label", None) or getattr(item, "text", "")
                parts = [label, *getattr(item, "details", [])]
                # Organization identity is unnecessary; chronology/level are material.
                for key in ("description", "level", "time_range"):
                    if getattr(item, key, None):
                        parts.append(getattr(item, key))
                value = " · ".join(parts)
                if profile_count >= MAX_PROFILE_FACTS or profile_chars + len(value) > MAX_PROFILE_CHARS:
                    partial = True
                    continue
                identifier = entry_id(category, item)
                key = f"{category}.{identifier}"
                provenance = inputs.profile.field_provenance.get(key)
                if add("confirmed_profile", category, value, origin_refs=(key,),
                       evidence_refs=tuple(item.evidence_ids),
                       uncertainty=provenance.uncertainty if provenance else (
                           "explicit_uncertainty" if explicitly_uncertain(value) else "none"),
                       goal_type=item.goal_type.value if category == "goals" else None):
                    profile_chars += len(value)
                    profile_count += 1
        memory_chars = 0
        if inputs.memory is not None:
            if inputs.memory.subject_id != inputs.subject_id:
                raise DiscoveryError(Status.INVALID_REFERENCE)
            partial |= inputs.memory.truncated
            for item in inputs.memory.items:
                if (item.status != MemoryStatus.CONFIRMED or item.memory_type.value not in
                    {"career_preference", "goal", "user_feedback"}):
                    raise DiscoveryError(Status.INVALID_REFERENCE)
                if memory_chars + len(item.content) > MAX_MEMORY_CHARS or sum(s.origin == "confirmed_memory" for s in sources) >= 3:
                    partial = True
                    continue
                if add("confirmed_memory", item.memory_type.value, item.content, origin_refs=(item.memory_id,),
                       uncertainty="explicit_uncertainty" if explicitly_uncertain(item.content) else "none"):
                    memory_chars += len(item.content)
        recent_chars = 0
        for index, (role, content) in enumerate(inputs.recent[-MAX_RECENT_MESSAGES:]):
            if role != "user":
                continue  # Assistant prose can never become a user fact.
            if recent_chars + len(content) > MAX_RECENT_CHARS:
                partial = True
                continue
            if add("recent_user_context", "situational", content, origin_refs=(f"recent_{index}",)):
                recent_chars += len(content)
        return CareerDiscoveryContext(request_id=request_id, sources=tuple(sources), partial=partial)


_OPEN = re.compile(r"相邻|邻近|现有经验|已有经验|adjacent|stay in|cross.industry|跨行业|留在|继续.{1,40}|(?:探索|比较|看看|转向|转做).{1,60}(?:方向|领域)|explor(?:e|ing).{1,60}(?:direction|analytics|product|career)", re.I)
_UNKNOWN = re.compile(r"没有明确|没想好|方向.*(?:未确定|不知道)|不知道.*方向|unknown|undecided|not sure", re.I)


def scoped_exploration(text):
    if re.fullmatch(r"(?i)(?:我想|请|let.s |i want to )?(?:探索|比较|看看|explore )(?:职业)?(?:方向|career directions?)[。.! ]*", text.strip()):
        return False
    if _OPEN.search(text):
        return True
    match = re.search(r"(?:探索|比较|看看)([^。！？!?]{1,100})", text)
    if not match:
        return False
    target = re.split(r"[,，;；]|但|还|尚", match.group(1), maxsplit=1)[0].strip(" 的")
    return bool(target and target not in {"职业方向", "方向", "职业", "工作", "其他方向", "什么方向", "适合我的方向"})


def readiness(context):
    background = [s for s in context.sources if s.origin == "confirmed_profile" and s.category in BACKGROUND]
    current = next((s.text for s in context.sources if s.origin == "current_explicit"), "")
    intents = [s for s in context.sources if s.origin == "confirmed_profile" and s.category in INTENT and
               (s.category != "goals" or s.goal_type == "career_goal")]
    if not background:
        return Readiness.NEEDS_CLARIFICATION, ClarificationNeed(need_id="background",
            question="这次探索可以从哪段已确认的工作、学习或实践经历开始？", reason="insufficient_relevant_background")
    # Explicit exploration is not a finalized goal. Uncertainty with a bounded
    # exploration scope is useful input, not a forced-profile-completion failure.
    intent = explicit_intent(current)
    scoped = scoped_exploration(current) or bool(intent and normalize(intent) not in {
        "转行", "换工作", "换方向", "探索职业方向", "职业方向", "change careers", "change career", "switch careers",
        "switch career", "explore career directions", "explore career direction"})
    if not current:
        scoped = any((s.uncertainty == "none" and not _UNKNOWN.search(s.text)) or scoped_exploration(s.text) for s in intents)
    if not scoped:
        return Readiness.NEEDS_CLARIFICATION, ClarificationNeed(need_id="exploration_scope",
            question="这次更想从已有经验的相邻方向开始，还是也探索跨行业方向？", reason="material_direction_uncertainty")
    return Readiness.READY, None
