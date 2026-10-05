"""Build only reviewed deltas; optional single curated signal is post-commit."""

from data.models import (
    CandidateSkill, CareerPreference, EvidenceBackedStatement, EvidenceItem, EvidenceSourceType,
    Goal, InterestSignal, InferenceType, ProfileFieldProvenance, ProfileSectionEntry,
    ProfileSourceReference, ProfileStatus, UserProfile, ValueSignal, utc_now,
)
from memory.models import MemoryType
from profile_refinement.context import ID_FIELDS, digest, entry_id
from profile_refinement.models import ChangeType, RefinementError, Resolution, Status
from profile_refinement.service import check_value

MODEL_FIELDS = {"skills": CandidateSkill, "interests": InterestSignal, "values": ValueSignal,
    "goals": Goal, "strengths": EvidenceBackedStatement, "development_areas": EvidenceBackedStatement,
    "career_preferences": CareerPreference}
MEMORY_FIELDS = {"goals": MemoryType.GOAL, "career_preferences": MemoryType.CAREER_PREFERENCE,
                 "transition_intent": MemoryType.CAREER_PREFERENCE}
ACCEPTED = {Resolution.CONFIRM, Resolution.EDIT, Resolution.UNCERTAIN}


def accepted_value(change):
    return change.edited_value or change.proposed_value


def build_confirmed_profile(draft, base, context):
    """Unchanged fields copied byte-for-value; no whole-Profile reconfirm/LLM call."""
    if any(c.user_resolution == Resolution.PENDING for c in draft.changes):
        raise RefinementError(Status.INVALID_DRAFT)
    data = base.model_dump() if base else UserProfile(profile_id=draft.profile_id).model_dump()
    source_map = {s.ref: s for s in context.sources}
    now, material = utc_now(), False
    for change in draft.changes:
        if change.user_resolution not in ACCEPTED:
            continue
        value = accepted_value(change)
        uncertain = "explicit_uncertainty" if change.user_resolution == Resolution.UNCERTAIN else change.uncertainty
        old_provenance = data["field_provenance"].get(f"{change.category}.{change.target_id}")
        if value == change.old_value and (old_provenance["uncertainty"] if old_provenance else "none") == uncertain:
            continue
        rows = data[change.category]
        id_field = ID_FIELDS.get(change.category, "entry_id")
        index = next((i for i, row in enumerate(rows) if row[id_field] == change.target_id), None)
        if change.old_value is not None and index is None:
            raise RefinementError(Status.INVALID_REFERENCE)
        key = f"{change.category}.{change.target_id}"
        if change.change_type == ChangeType.REMOVE:
            if value is not None or change.user_resolution in {Resolution.EDIT, Resolution.UNCERTAIN}:
                raise RefinementError(Status.INVALID_DRAFT)
            rows.pop(index)
            data["field_provenance"].pop(key, None)
            material = True
            continue
        if value is None:
            raise RefinementError(Status.INVALID_DRAFT)
        check_value(change.category, value)
        sources = [source_map[ref] for ref in change.source_refs if source_map[ref].origin != "confirmed_profile"]
        if change.edited_value is not None:
            refs = [ProfileSourceReference(origin="explicit_user_edit", reference=f"{draft.draft_id}:{change.change_id}")]
        else:
            refs = [ProfileSourceReference(origin=s.origin, reference=reference) for s in sources for reference in s.origin_refs][:16]
        evidence_id = "profile_evidence_" + digest([draft.draft_id, change.change_id])[:32]
        explicit = change.edited_value is not None or any(s.origin in {"explicit_user_input", "clarification_answer"} for s in sources)
        source_type = EvidenceSourceType.EXPLICIT_USER_INPUT if explicit else EvidenceSourceType.MODEL_INFERENCE
        provenance = ProfileFieldProvenance(source_refs=refs, uncertainty=uncertain, last_confirmed_at=now)
        data["field_provenance"][key] = provenance.model_dump()
        # Evidence statement is the reviewed normalized label, NOT source text.
        data["evidence"].append(EvidenceItem(id=evidence_id, source_type=source_type,
            source_name="profile_refinement", statement=value.label, confidence=1.0 if explicit else 0.7,
            metadata={"source_refs": [r.model_dump() for r in refs], "uncertainty": uncertain}).model_dump())
        existing = dict(rows[index]) if index is not None else {}
        existing.update({id_field: change.target_id, "evidence_ids": list(dict.fromkeys([
            *existing.get("evidence_ids", []), evidence_id])), "source_type": source_type,
            "inference_type": InferenceType.EXPLICIT_FACT if explicit else InferenceType.EVIDENCE_SUPPORTED_INFERENCE,
            "confidence": 1.0 if explicit else 0.7, "needs_confirmation": False, "confirmed_by_user": True})
        if change.category in {"strengths", "development_areas"}:
            existing["text"] = value.label
        else:
            existing["label"] = value.label
        if change.category in MODEL_FIELDS:
            if change.category not in {"strengths", "development_areas"}:
                existing["description"] = "\n".join(value.details) or None
            if change.category == "skills":
                existing["level"] = value.level
            if change.category == "goals":
                existing["goal_type"] = value.goal_type
        else:
            existing.update(details=list(value.details), organization=value.organization, time_range=value.time_range)
        model = MODEL_FIELDS.get(change.category, ProfileSectionEntry)
        entry = model.model_validate(existing).model_dump()
        if index is None:
            rows.append(entry)
        else:
            rows[index] = entry
        material = True
    if not material:
        return None
    data.update(profile_id=draft.profile_id, version=draft.proposed_profile_version, status=ProfileStatus.CONFIRMED,
                confirmed=True, confirmed_at=now, updated_at=now)
    return UserProfile.model_validate(data)


def write_curated_memory(service, subject_id, profile, draft, change_id):
    """Explicit opt-in, max ONE allowlisted changed signal; no full-profile dump.

    Existing canonical Memory APIs commit independently. Profile+pointer have
    already committed. No automatic retry/outbox. Derived vectors remain the
    existing service's independently repairable index, not an authority gate.
    """
    change = next((c for c in draft.changes if c.change_id == change_id), None)
    if (change is None or change.category not in MEMORY_FIELDS or change.user_resolution not in ACCEPTED or
        change.change_type == ChangeType.REMOVE):
        raise RefinementError(Status.INVALID_DRAFT)
    value = accepted_value(change)
    kind = MEMORY_FIELDS[change.category]
    dimension = f"profile.{change.category}.{change.target_id}"
    # Normalize deterministically, never similarity-based conflict inference.
    normalized = " ".join(value.label.split()).casefold()
    active = service.memory_store.list_active(subject_id, memory_types=[kind])
    uncertainty = profile.field_provenance[f"{change.category}.{change.target_id}"].uncertainty
    if any(" ".join(m.content.split()).casefold() == normalized and
           m.metadata.get("uncertainty", "none") == uncertainty for m in active):
        return "DEDUPLICATED"
    same_dimension = [m for m in active if m.metadata.get("signal_dimension") == dimension]
    if len(same_dimension) > 1:
        raise RefinementError(Status.MEMORY_SIDE_EFFECT_FAILED)
    refs = next(item.evidence_ids for item in getattr(profile, change.category)
                if entry_id(change.category, item) == change.target_id)
    metadata = {"signal_dimension": dimension, "signal_value": normalized,
                "uncertainty": uncertainty, "profile_version": profile.version}
    kwargs = dict(content=value.label, source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
        confirmed_by_user=True, evidence_refs=refs, metadata=metadata)
    memory_id = "memory_" + digest([subject_id, profile.profile_id, profile.version, change.change_id])[:32]
    if same_dimension:
        service.supersede(subject_id, same_dimension[0].memory_id, new_memory_id=memory_id, **kwargs)
        return "SUPERSEDED"
    service.create_confirmed(subject_id=subject_id, memory_type=kind, memory_id=memory_id, **kwargs)
    return "CREATED"
