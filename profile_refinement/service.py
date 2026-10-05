"""One bounded proposal call + deterministic delta validation; never stores authority."""

from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field, create_model

from data.models import utc_now
from profile_refinement.models import ChangeType as CT, ProfileFieldChange, ProfileRefinementDraft, Proposal, RefinementError, RefinementOutput, Status
from profile_refinement.context import digest
from providers.models import GenerationOptions, LLMMessage, LLMUsage
from resume_evidence.context import minimize_text
from resume_evidence.service import ResumeUsage, private_transport_logging

PROMPT_PATH = Path(__file__).resolve().parents[1] / "config/prompts/profile_refinement_v1.md"
PREFERENCE_FIELDS = {"career_preferences", "role_interests", "industry_interests", "location_preferences", "work_style_preferences", "transition_intent"}


def scoped_output(context):
    refs = tuple(source.ref for source in context.sources)
    if not refs:
        raise RefinementError(Status.INVALID_DRAFT)
    targets = tuple(s.target_id for s in context.sources if s.origin == "confirmed_profile")
    target_type = Literal[targets] | None if targets else type(None)
    scoped = create_model("ScopedProfileProposal", __base__=Proposal,
        source_refs=(tuple[Literal[refs], ...], Field(..., min_length=1, max_length=8)),
        target_id=(target_type, Field(...)))
    return create_model("ScopedProfileRefinement", __base__=RefinementOutput,
        changes=(tuple[scoped, ...], Field(..., max_length=20, repr=False)))


def check_value(category, value):
    if value is None:
        return
    from ui.conversation_store import _no_credentials
    import re
    for text in (value.label, *value.details, value.level, value.organization, value.time_range):
        if text:
            _no_credentials(text)
            # Canonical career fields are not a new contact store. Reuse the
            # conservative C.2 boundary; reject, never silently rewrite review.
            if minimize_text(text)[1]:
                raise RefinementError(Status.INVALID_DRAFT)
            if re.search(r"(?i)(?:file://|/(?:Users|home)/|[A-Z]:\\|\.env|<script|chain.of.thought|system prompt|provider completion)", text):
                raise RefinementError(Status.INVALID_DRAFT)
    if ((category == "goals") != (value.goal_type is not None) or
        (value.level is not None and category != "skills") or
        (category not in {"education", "work_experience"} and (value.organization is not None or value.time_range is not None))):
        raise RefinementError(Status.INVALID_DRAFT)


def validate_changes(output, context, binding):
    sources = {s.ref: s for s in context.sources}
    changes, targets_seen = [], set()
    for p in output.changes:
        if len(set(p.source_refs)) != len(p.source_refs) or any(ref not in sources for ref in p.source_refs):
            raise RefinementError(Status.INVALID_REFERENCE)
        refs = [sources[ref] for ref in p.source_refs]
        target = next((s for s in sources.values() if s.origin == "confirmed_profile" and
                       s.category == p.category and s.target_id == p.target_id), None) if p.target_id else None
        if p.target_id is not None and target is None:
            raise RefinementError(Status.INVALID_REFERENCE)
        if target and target.ref not in p.source_refs:
            raise RefinementError(Status.INVALID_REFERENCE)
        if p.change_type == CT.ADD and target or p.change_type in {CT.UPDATE, CT.REMOVE, CT.KEEP_OLD, CT.UNCHANGED} and not target:
            raise RefinementError(Status.INVALID_DRAFT)
        if (p.change_type == CT.REMOVE) != (p.proposed_value is None):
            raise RefinementError(Status.INVALID_DRAFT)
        check_value(p.category, p.proposed_value)
        old = target.value if target else None
        if target and (p.category, p.target_id) in targets_seen:
            raise RefinementError(Status.INVALID_DRAFT)
        targets_seen.add((p.category, p.target_id)) if target else None
        if p.change_type in {CT.UNCHANGED, CT.KEEP_OLD}:
            if p.change_type == CT.UNCHANGED and old != p.proposed_value:
                raise RefinementError(Status.INVALID_DRAFT)
            continue
        evidence = [s for s in refs if s.origin != "confirmed_profile"]
        if not evidence:
            raise RefinementError(Status.INVALID_REFERENCE)
        current = [s for s in evidence if s.origin == "explicit_user_input"]
        answers = [s for s in evidence if s.origin == "clarification_answer"]
        user_sources = current or answers
        if p.category == "development_areas" and (not user_sources or any(s.uncertainty for s in user_sources)):
            raise RefinementError(Status.INVALID_DRAFT)  # Unknown is not a weakness/gap.
        if p.change_type == CT.REMOVE and not user_sources:
            raise RefinementError(Status.INVALID_DRAFT)
        if p.change_type == CT.REMOVE:
            import re
            if not any(re.search(r"(?i)删除|移除|取消|不再|放弃|\bremove\b|\bretire\b|\bdelete\b", s.text) for s in user_sources):
                raise RefinementError(Status.INVALID_DRAFT)
        # The strongest relevant current source cannot be omitted in favor of
        # an older answer/resume. Still expose differences, never auto-resolve.
        strongest = [s for s in context.sources if s.origin == "explicit_user_input" and s.explicit_goal]
        if p.category in {"goals", *PREFERENCE_FIELDS} and strongest and not all(s.ref in p.source_refs for s in strongest):
            raise RefinementError(Status.INVALID_REFERENCE)
        for source in evidence:
            if source.origin == "resume_evidence":
                allowed = {source.category}
                if source.explicit_goal:
                    allowed |= {"goals", "career_preferences", "transition_intent"}
                if p.category not in allowed:
                    raise RefinementError(Status.INVALID_REFERENCE)
            if source.origin == "clarification_answer":
                if source.category == "career_direction" and p.category not in {"goals", *PREFERENCE_FIELDS, "uncertainties"}:
                    raise RefinementError(Status.INVALID_REFERENCE)
        if p.category == "goals" and p.change_type != CT.REMOVE and not any(s.explicit_goal or s.uncertainty for s in evidence):
            raise RefinementError(Status.INVALID_REFERENCE)
        if not user_sources and p.category == "skills" and p.proposed_value.level is not None:
            # Resume/Memory mention cannot create or upgrade proficiency.
            if old is None or p.proposed_value.level != old.level:
                raise RefinementError(Status.INVALID_DRAFT)
        if p.category == "skills" and target is None:
            same_skill = [s for s in context.sources if s.origin == "confirmed_profile" and s.category == "skills" and
                          s.value.label.casefold() == p.proposed_value.label.casefold()]
            if same_skill:
                if not user_sources and all(p.proposed_value.level in {None, s.value.level} for s in same_skill):
                    continue  # Mention only: preserve known proficiency, no duplicate skill.
                raise RefinementError(Status.INVALID_DRAFT)  # Bind an UPDATE, never substitute an ID.
        uncertainty = p.uncertainty
        if any(s.uncertainty for s in evidence) and uncertainty == "none":
            uncertainty = "explicit_uncertainty" if user_sources else "unknown"
        conflict = bool(old is not None and old != p.proposed_value)
        # Historical Memory cannot add certainty or overwrite a current preference.
        if all(s.origin == "confirmed_memory" for s in evidence):
            uncertainty = "unknown"
        if old == p.proposed_value and target and target.uncertainty_status == uncertainty:
            continue
        change_type = CT.CONFLICT if conflict else (CT.UNCERTAIN if uncertainty != "none" else CT.ADD)
        if p.change_type == CT.REMOVE:
            change_type = CT.REMOVE
        if not target and any(c.category == p.category and c.proposed_value == p.proposed_value for c in changes):
            raise RefinementError(Status.INVALID_DRAFT)
        # Repeated ADD of a semantically identical existing item is no-change.
        if not target and any(s.origin == "confirmed_profile" and s.category == p.category and s.value == p.proposed_value for s in sources.values()):
            continue
        changes.append(ProfileFieldChange(change_id="change_" + uuid4().hex, category=p.category,
            target_id=p.target_id or f"{p.category}_" + uuid4().hex, change_type=change_type,
            old_value=old, proposed_value=p.proposed_value, source_refs=p.source_refs,
            reason_summary=p.reason_summary, uncertainty=uncertainty,
            conflict_state="requires_review" if conflict else "none"))
    return tuple(changes)


def fingerprint_draft(draft):
    return digest(draft.model_dump(mode="json", exclude={"draft_fingerprint"}))


class ProfileDeltaProposer:
    def propose(self, provider, context, binding):
        options = GenerationOptions(model="qwen3.8-flash", thinking_enabled=False, max_retries=0,
                                    temperature=0, max_output_tokens=4096, timeout_seconds=30)
        messages = [LLMMessage(role="system", content=PROMPT_PATH.read_text(encoding="utf-8")),
                    LLMMessage(role="user", content=context.model_dump_json())]
        with private_transport_logging():
            response = provider.generate_structured(messages, scoped_output(context), options,
                prompt_name="profile_refinement", prompt_version="v1")
        try:
            output = RefinementOutput.model_validate(response.data.model_dump(mode="json", warnings=False))
            usage = LLMUsage.model_validate(response.usage.model_dump(warnings=False))
            if (response.provider not in {"fake", "qwen"} or response.model != options.model or response.thinking_enabled or
                response.retry_count != 0 or response.prompt_name != "profile_refinement" or response.prompt_version != "v1" or
                type(response.latency_ms) is not int or not 0 <= response.latency_ms <= 120_000 or
                any(n is not None and (type(n) is not int or n > 1_000_000) for n in
                    (usage.input_tokens, usage.output_tokens, usage.total_tokens))):
                raise ValueError("INVALID_DRAFT")
        except Exception:
            raise RefinementError(Status.INVALID_DRAFT) from None
        changes = validate_changes(output, context, binding)
        draft = ProfileRefinementDraft(draft_id="profile_draft_" + uuid4().hex, binding=binding,
            profile_id=binding.base_profile_id or "profile_" + uuid4().hex,
            proposed_profile_version=(binding.base_profile_version or 0) + 1, changes=changes,
            created_at=utc_now(), status=Status.DRAFT if changes else Status.NO_MATERIAL_CHANGE, draft_fingerprint="")
        draft = draft.model_copy(update={"draft_fingerprint": fingerprint_draft(draft)})
        return draft, ResumeUsage(response.provider, usage.input_tokens, usage.output_tokens, usage.total_tokens, response.latency_ms)
