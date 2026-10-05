"""Bounded source projection. Read-only retrieval and durable authority stay separate."""

from dataclasses import dataclass, field
import hashlib
import json
import re

from career_runtime.context import recent_turns
from clarification.models import ClarificationContext, ClarificationSource, QuestionBinding
from clarification.policy import MAX_CONTEXT_CHARS, MAX_SOURCE_CHARS, MAX_SOURCES
from data.models import EvidenceSourceType, GoalType, InferenceType, ProfileStatus, UserProfile
from memory.integration import MemoryContextCoordinator
from memory.models import MemoryConsumer, MemoryStatus, MemoryType, MemoryUseCase
from resume_evidence.context import minimize_text, normalize
from resume_evidence.models import ResumeEvidenceBundle

_GOAL = re.compile(r"(?i)(?:我(?:现在|目前|最近)?(?:更)?(?:想|希望|打算|倾向)(?:要)?(?:转做|转向|转|做|从事|继续)?|(?:i\s+)?(?:want to|aim to|seeking|career goal\s*[:：]|career objective\s*[:：])|求职意向[:：]|职业目标[:：])([^\n。！？!?;；]{1,160})")
_UNKNOWN = re.compile(r"(?i)没想好|未确定|还没定|不确定|不知道|还在考虑|都在考虑|haven.t decided|not sure|don.t know|undecided")


def explicit_intent(text: str) -> str | None:
    """Conservative explicit text span, never inferred from a major or job title."""
    if _UNKNOWN.search(text):
        return None
    found = _GOAL.search(text)
    if not found:
        return None
    value = normalize(found.group(1)).strip(" .，,")
    if re.match(r"了解|看看|知道|问|学习|吃|喝|understand|learn|ask", value, re.I):
        return None
    if value in {"行", "型", "换方向", "换工作", "其他方向"}:
        return None  # Transition without a target is not a known career goal.
    return value or None


def direction_value(text: str) -> str:
    value = explicit_intent(text) or normalize(text)
    return re.sub(r"(?:方向|领域|工作|岗位|职业)$", "", value).strip()


def explicitly_uncertain(text: str) -> bool:
    return bool(_UNKNOWN.search(text))


def safe_excerpt(text: str, limit=MAX_SOURCE_CHARS) -> str:
    from ui.conversation_store import _no_credentials
    _no_credentials(text)
    return minimize_text(text)[0][:limit].strip()


@dataclass(frozen=True)
class ClarificationInputs:
    owner_scope_id: str
    conversation_id: str
    subject_id: str
    resume: ResumeEvidenceBundle = field(repr=False)
    profile: UserProfile | None = field(default=None, repr=False)
    memory: object | None = field(default=None, repr=False)
    recent: tuple = field(default=(), repr=False)
    current_statement: str = field(default="", repr=False)


def binding_for(inputs: ClarificationInputs, version: int) -> QuestionBinding:
    bundle = ResumeEvidenceBundle.model_validate(inputs.resume.model_dump(warnings=False))
    if bundle.owner_scope_id != inputs.owner_scope_id or bundle.thread_id != inputs.conversation_id:
        raise ValueError("CLARIFICATION_CONTEXT_FAILED")
    profile = inputs.profile
    if profile is not None:
        profile = UserProfile.model_validate(profile.model_dump(warnings=False))
        if not profile.confirmed or profile.status != ProfileStatus.CONFIRMED:
            raise ValueError("CLARIFICATION_CONTEXT_FAILED")
    digest = hashlib.sha256(bundle.canonical_json().encode()).hexdigest()
    return QuestionBinding(owner_scope_id=inputs.owner_scope_id, conversation_id=inputs.conversation_id,
        state_version=version, resume_source_id=bundle.source_id, resume_evidence_version=digest,
        profile_id=profile.profile_id if profile else None, profile_version=profile.version if profile else None)


def workspace_inputs(workspace, *, current_statement="") -> ClarificationInputs:
    analysis = workspace.resume_analysis
    if workspace._closed or not analysis.has_consent or analysis.bundle is None:
        raise ValueError("CLARIFICATION_CONTEXT_FAILED")
    profile = workspace.memory_service.get_current_confirmed_profile(workspace.subject_id)
    # The existing PROFILE_REFINEMENT read policy is reused for understanding,
    # not its refinement/write service. No third Memory use case or embeddings.
    query = safe_excerpt(current_statement, 500) or "职业目标 职业偏好 当前职业情况"
    memory = MemoryContextCoordinator(workspace.memory_service).retrieve(
        subject_id=workspace.subject_id, use_case=MemoryUseCase.PROFILE_REFINEMENT,
        consumer=MemoryConsumer.PROFILE_REFINEMENT_SERVICE, query=query)
    messages = workspace.store.list_messages(workspace.owner_scope_id, workspace.thread.thread_id, limit=12)
    return ClarificationInputs(workspace.owner_scope_id, workspace.thread.thread_id, workspace.subject_id,
        analysis.bundle, profile, memory, tuple(messages), current_statement)


class ClarificationContextBuilder:
    def build(self, inputs: ClarificationInputs, *, answers=()) -> ClarificationContext:
        binding_for(inputs, 0)
        sources, partial = [], bool(inputs.resume.context_partial)
        current_ref = None

        def add(prefix, kind, authority, category, text, ambiguity="none", goal=False, scope="", origins=(), known=False):
            nonlocal partial
            clean = safe_excerpt(text)
            if not clean:
                return None
            if len(sources) >= MAX_SOURCES:
                partial = True
                return None
            ref = f"{prefix}_{1 + sum(s.kind == kind for s in sources):03d}"
            source = ClarificationSource(ref=ref, kind=kind, authority=authority, category=category,
                text=clean, ambiguity=ambiguity, explicit_goal=goal,
                semantic_scope=hashlib.sha256((scope or category).encode()).hexdigest()[:20], origin_refs=origins,
                detail_known=known)
            if len(clean) < len(text):
                partial = True
            sources.append(source)
            return ref

        # Protect highest-authority current text and bounded recent answers first.
        if inputs.current_statement:
            current_ref = add("cu", "current", "explicit_user_input", "current_statement",
                              inputs.current_statement, "explicit_uncertainty" if explicitly_uncertain(inputs.current_statement) else "none",
                              goal=explicit_intent(inputs.current_statement) is not None,
                              origins=("current_explicit_statement",))
        for answer in answers[-8:]:
            if answer.binding.conversation_id != inputs.conversation_id or answer.binding.owner_scope_id != inputs.owner_scope_id:
                raise ValueError("CLARIFICATION_CONTEXT_FAILED")
            add("an", "answer", "explicit_user_input", answer.topic, answer.user_answer,
                "explicit_uncertainty" if answer.uncertainty != "none" else "none",
                goal=answer.topic == "career_direction" and explicit_intent(answer.user_answer) is not None,
                origins=(answer.candidate_id,))
        if inputs.profile:
            for category, field_name in (("career_direction", "goals"), ("preference", "career_preferences"), ("skills", "skills")):
                for item in getattr(inputs.profile, field_name)[:4]:
                    # Inference in a confirmed container still is not an explicit user fact.
                    if (item.inference_type != InferenceType.EXPLICIT_FACT or not item.confirmed_by_user or
                            item.source_type == EvidenceSourceType.MODEL_INFERENCE):
                        continue
                    career_goal = ((category == "career_direction" and item.goal_type == GoalType.CAREER_GOAL) or
                                   (category == "preference" and bool(re.search(r"方向|career|职业|转向|继续|希望", item.label, re.I))))
                    signal_id = getattr(item, "goal_id", getattr(item, "preference_id", getattr(item, "skill_id", "")))
                    actual_category = "goal:" + item.goal_type.value if field_name == "goals" and not career_goal else category
                    add("pf", "profile", "confirmed_profile", actual_category, item.label, goal=career_goal,
                        origins=(signal_id, *item.evidence_ids[:7]), known=bool(getattr(item, "level", None)))
        resume_sources = {}
        for item in inputs.resume.items:
            text, omitted = item.canonical_projection(MAX_SOURCE_CHARS)
            partial = partial or omitted
            ref = add("rs", "resume", "resume_provided", item.category, text, item.uncertainty,
                goal=item.claim_type == "explicit_career_statement" and explicit_intent(item.canonical_text) is not None,
                scope=item.category + "|" + "|".join(sorted(item.source_block_ids)),
                origins=(item.evidence_id, *item.source_block_ids))
            if ref:
                resume_sources[ref] = item
        for uncertainty in inputs.resume.uncertainties:
            # Absence itself is not a capability gap or a need to fill every field.
            if uncertainty.status != "unclear":
                continue
            for source in list(sources):
                if source.kind != "resume":
                    continue
                item = resume_sources.get(source.ref)
                if item is not None and set(uncertainty.source_block_ids) & set(item.source_block_ids):
                    topics = {"ownership": "unclear_ownership", "proficiency": "unclear_proficiency",
                              "project_work_boundary": "ambiguous_project_work_boundary", "dates": "unclear_dates"}
                    updated = source.model_copy(update={"ambiguity": topics.get(uncertainty.topic, "other")})
                    sources[sources.index(source)] = updated
        memory = inputs.memory
        if memory is not None:
            if memory.subject_id != inputs.subject_id:
                raise ValueError("CLARIFICATION_CONTEXT_FAILED")
            allowed = {MemoryType.GOAL, MemoryType.CAREER_PREFERENCE, MemoryType.USER_FEEDBACK}
            used = 0
            chars = 0
            for item in memory.items[:8]:
                if item.status != MemoryStatus.CONFIRMED or item.authority != "active_confirmed" or item.memory_type not in allowed:
                    continue
                if used >= 6 or chars + len(item.content) > 3600:
                    partial = True
                    continue
                add("mm", "memory", "confirmed_historical_memory", item.memory_type.value, item.content, origins=(item.memory_id,))
                used += 1
                chars += len(item.content)
        recent = recent_turns(list(inputs.recent))
        for item in recent:
            add("cv", "conversation", "conversation_context", item.role, item.text,
                goal=False, origins=(item.message_id,))  # Never promoted to current user facts.
        context = ClarificationContext(sources=tuple(sources), needs=(), current_source_ref=current_ref, partial=partial)
        # Includes escaped JSON, not merely visible text. Lower-priority tail is dropped.
        while len(context.model_dump_json()) > 12_000 and context.sources:
            context = context.model_copy(update={"sources": context.sources[:-1], "partial": True})
        return context
