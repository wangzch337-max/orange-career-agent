"""Deterministic bounded projection + local full-state binding, no authority writes."""

from dataclasses import dataclass, field
import hashlib
import json

from clarification.context import binding_for, explicit_intent, explicitly_uncertain, safe_excerpt
from clarification.models import ClarificationAnswerCandidate
from data.models import PROFILE_OPTIONAL_SECTIONS, ProfileStatus, UserProfile
from memory.integration import MemoryContextCoordinator
from memory.models import MemoryConsumer, MemoryStatus, MemoryType, MemoryUseCase
from profile_refinement.models import Binding, MAX_CONTEXT_CHARS, MAX_SOURCES, ProfileRefinementContext, RefinementError, Source, Status, Value
from resume_evidence.models import ResumeEvidenceBundle

LEGACY_CATEGORIES = ("skills", "interests", "values", "goals", "strengths", "development_areas", "career_preferences")
CATEGORIES = (*LEGACY_CATEGORIES, *PROFILE_OPTIONAL_SECTIONS)
ID_FIELDS = {"skills": "skill_id", "interests": "interest_id", "values": "value_id", "goals": "goal_id",
             "strengths": "statement_id", "development_areas": "statement_id", "career_preferences": "preference_id"}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def entry_id(category, entry):
    return getattr(entry, ID_FIELDS.get(category, "entry_id"))


def value_for(category, entry):
    label = getattr(entry, "label", getattr(entry, "text", ""))
    details = getattr(entry, "details", None)
    if details is None:
        description = getattr(entry, "description", None)
        details = (description,) if description else ()
    return Value(label=label[:160], details=tuple(text[:240] for text in details[:4]),
        level=getattr(entry, "level", None), goal_type=getattr(entry, "goal_type", None),
        organization=getattr(entry, "organization", None), time_range=getattr(entry, "time_range", None))


@dataclass(frozen=True)
class RefinementInputs:
    owner_scope_id: str
    conversation_id: str
    subject_id: str
    resume: ResumeEvidenceBundle = field(repr=False)
    profile: UserProfile | None = field(default=None, repr=False)
    answers: tuple[ClarificationAnswerCandidate, ...] = field(default=(), repr=False)
    clarification_version: int = 0
    current_statement: str = field(default="", repr=False)
    memory: object | None = field(default=None, repr=False)


def binding_for_refinement(inputs):
    bundle = ResumeEvidenceBundle.model_validate(inputs.resume.model_dump(warnings=False))
    if bundle.owner_scope_id != inputs.owner_scope_id:
        raise RefinementError(Status.OWNER_SCOPE_MISMATCH)
    if bundle.thread_id != inputs.conversation_id:
        raise RefinementError(Status.CONVERSATION_NOT_FOUND)
    profile = inputs.profile
    if profile:
        profile = UserProfile.model_validate(profile.model_dump(warnings=False))
        if not profile.confirmed or profile.status != ProfileStatus.CONFIRMED:
            raise RefinementError(Status.INVALID_DRAFT)
    resume_digest = digest(bundle.canonical_payload())
    # Both consumers bind canonical facts/sources, never provider display words.
    clarification_resume_digest = hashlib.sha256(bundle.canonical_json().encode()).hexdigest()
    if len(inputs.answers) > 8:
        raise RefinementError(Status.INVALID_DRAFT)
    seen = set()
    for candidate in inputs.answers:
        answer = ClarificationAnswerCandidate.model_validate(candidate.model_dump(warnings=False))
        b = answer.binding
        if (answer.candidate_id in seen or b.owner_scope_id != inputs.owner_scope_id or
            b.conversation_id != inputs.conversation_id or b.resume_source_id != bundle.source_id or
            b.resume_evidence_version != clarification_resume_digest or b.state_version > inputs.clarification_version or
            b.profile_id != (profile.profile_id if profile else None) or
            b.profile_version != (profile.version if profile else None)):
            raise RefinementError(Status.INVALID_REFERENCE)
        seen.add(answer.candidate_id)
    return Binding(owner_scope_id=inputs.owner_scope_id, conversation_id=inputs.conversation_id,
        subject_id=inputs.subject_id, base_profile_id=profile.profile_id if profile else None,
        base_profile_version=profile.version if profile else None,
        base_profile_fingerprint=digest(profile.model_dump(mode="json") if profile else None),
        resume_source_id=bundle.source_id, resume_evidence_fingerprint=resume_digest,
        clarification_state_version=inputs.clarification_version,
        clarification_fingerprint=digest([a.model_dump(mode="json") for a in inputs.answers]),
        current_statement_fingerprint=digest(inputs.current_statement))


def workspace_inputs(workspace, *, current_statement="", include_memory=False):
    analysis = workspace.resume_analysis
    # Read-only guard: has_consent may invoke C.2/C.3 invalidation callbacks.
    # Never acquire the clarification lock while a Profile review lock is held.
    consent_valid = analysis.consent is not None and analysis.consent == analysis._identity()
    if workspace._closed or not consent_valid or analysis.bundle is None:
        raise RefinementError(Status.STALE_DRAFT)
    thread = workspace.thread.thread_id
    # An externally deleted thread cannot be revived by late review/worker output.
    workspace.store.get_thread(workspace.owner_scope_id, thread)
    memory = None
    if include_memory:
        memory = MemoryContextCoordinator(workspace.memory_service).retrieve(
            subject_id=workspace.subject_id, use_case=MemoryUseCase.PROFILE_REFINEMENT,
            consumer=MemoryConsumer.PROFILE_REFINEMENT_SERVICE,
            query=safe_excerpt(current_statement, 500) or "职业目标 职业偏好 当前职业情况")
    return RefinementInputs(workspace.owner_scope_id, thread, workspace.subject_id,
        workspace.resume_analysis.bundle, workspace.memory_service.get_current_confirmed_profile(workspace.subject_id),
        tuple(workspace.clarification.state.answer_candidates), workspace.clarification.state.version,
        current_statement, memory)


class ProfileRefinementContextBuilder:
    def build(self, inputs):
        binding_for_refinement(inputs)
        sources = []
        partial = bool(inputs.resume.context_partial)

        def add(prefix, origin, category, text="", *, value=None, target=None, refs=(), uncertain=False, goal=False, uncertainty_status="none"):
            nonlocal partial
            clean = safe_excerpt(text, 800) if text else ""
            if len(clean) < len(text):
                partial = True
            candidate = Source(ref=f"{prefix}_{1 + sum(s.origin == origin for s in sources):03d}", origin=origin,
                category=category, text=clean, value=value, target_id=target, origin_refs=refs[:8],
                uncertainty=uncertain, explicit_goal=goal, uncertainty_status=uncertainty_status)
            size = len(json.dumps([s.model_dump(mode="json") for s in (*sources, candidate)], ensure_ascii=False))
            if len(sources) >= MAX_SOURCES or size > MAX_CONTEXT_CHARS - 200:
                partial = True
                return
            sources.append(candidate)

        if inputs.current_statement:
            add("cu", "explicit_user_input", "current_statement", inputs.current_statement,
                refs=("current_statement_" + digest(inputs.current_statement),),
                uncertain=explicitly_uncertain(inputs.current_statement), goal=explicit_intent(inputs.current_statement) is not None)
        for answer in inputs.answers:
            add("an", "clarification_answer", answer.topic, answer.user_answer, refs=(answer.candidate_id,),
                uncertain=answer.uncertainty != "none", goal=answer.topic == "career_direction")
        if inputs.profile:
            # Budget only controls visibility, never truncates the base stored in RAM.
            for category in ("goals", "career_preferences", "skills", *[c for c in CATEGORIES if c not in {"goals", "career_preferences", "skills"}]):
                for entry in getattr(inputs.profile, category):
                    try:
                        value = value_for(category, entry)
                    except Exception:
                        partial = True
                        continue
                    original_details = getattr(entry, "details", None)
                    if original_details is None:
                        original_details = [getattr(entry, "description", "") or ""]
                    if (len(getattr(entry, "label", getattr(entry, "text", ""))) > 160 or
                        len(original_details) > 4 or any(len(text) > 240 for text in original_details)):
                        partial = True
                    add("pf", "confirmed_profile", category, value=value, target=entry_id(category, entry),
                        refs=(entry_id(category, entry), *entry.evidence_ids[:7]),
                        uncertainty_status=(inputs.profile.field_provenance[f"{category}.{entry_id(category, entry)}"].uncertainty
                            if f"{category}.{entry_id(category, entry)}" in inputs.profile.field_provenance else "none"))
        for evidence in inputs.resume.items:
            category = {"responsibilities": "work_experience", "portfolio": "projects",
                        "business_metrics": "achievements", "awards": "achievements",
                        "publications": "research", "uncertainty": "uncertainties"}.get(evidence.category, evidence.category)
            details = tuple(dict.fromkeys(text for key in ("responsibilities", "achievements", "domain_signals", "tools", "business_metrics")
                                         for text in getattr(evidence, key, ())))
            # Existing budgets stay fixed. Omit whole over-budget facts rather
            # than slicing a material suffix/qualifier into a different fact.
            if len(evidence.canonical_label) > 160:
                partial = True
                continue
            bounded_details = tuple(text for text in details if len(text) <= 240)[:4]
            partial = partial or bounded_details != details
            organization = getattr(evidence, "organization", None)
            time_range = getattr(evidence, "time_range", None)
            if organization and len(organization) > 160:
                organization, partial = None, True
            if time_range and len(time_range) > 80:
                time_range, partial = None, True
            value = Value(label=safe_excerpt(evidence.canonical_label, 160),
                details=tuple(safe_excerpt(text, 240) for text in bounded_details),
                organization=organization, time_range=time_range)
            add("rs", "resume_evidence", category, value=value,
                refs=(f"{inputs.resume.source_id}:{evidence.evidence_id}", *evidence.source_block_ids[:7]),
                uncertain=evidence.uncertainty != "none", goal=evidence.claim_type == "explicit_career_statement")
        if inputs.memory:
            if inputs.memory.subject_id != inputs.subject_id:
                raise RefinementError(Status.OWNER_SCOPE_MISMATCH)
            for memory in inputs.memory.items[:6]:
                if memory.status != MemoryStatus.CONFIRMED or memory.memory_type not in {
                        MemoryType.CAREER_PREFERENCE, MemoryType.GOAL, MemoryType.USER_FEEDBACK}:
                    raise RefinementError(Status.INVALID_REFERENCE)
                add("mm", "confirmed_memory", memory.memory_type.value, memory.content, refs=(memory.memory_id,))
        context = ProfileRefinementContext(sources=tuple(sources), partial=partial)
        if len(context.model_dump_json()) > MAX_CONTEXT_CHARS:
            raise RefinementError(Status.INVALID_DRAFT)
        return context
