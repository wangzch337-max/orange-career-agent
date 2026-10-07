"""Whole-item confirmed authority and exact D.4 field projections, no retrieval."""

from career_discovery.context import fingerprint
from data.models import UserProfile, PROFILE_OPTIONAL_SECTIONS, InferenceType, EvidenceSourceType
from specific_role.sources import SpecificRoleRegistry
from specific_role.service import SpecificRoleService
from specific_role.models import Dimension
from ui.conversation_store import _no_credentials
from evidence_match.models import UserEvidence, UserSignal, UserProjection, WorkEvidence, WorkSignal, WorkProjection

IDS = {"skills":"skill_id", "interests":"interest_id", "values":"value_id", "goals":"goal_id",
       "strengths":"statement_id", "development_areas":"statement_id", "career_preferences":"preference_id"}


def project_user(profile):
    profile = UserProfile.model_validate(profile.model_dump())
    if not profile.confirmed:
        raise ValueError("D5_CONFIRMED_PROFILE_REQUIRED")
    _no_credentials(profile.model_dump_json())
    signals, ids, characters, partial = [], set(), 0, False
    evidence = {e.id: e for e in profile.evidence}
    if len(evidence) != len(profile.evidence):
        raise ValueError("D5_DUPLICATE_EVIDENCE")
    for category in (*IDS, *PROFILE_OPTIONAL_SECTIONS):
        for entry in getattr(profile, category):
            if not entry.confirmed_by_user:
                raise ValueError("D5_UNCONFIRMED_SIGNAL")
            identifier = getattr(entry, IDS.get(category, "entry_id"))
            signal_id = "user:" + category + ":" + identifier
            if signal_id in ids:
                raise ValueError("D5_DUPLICATE_SIGNAL")
            ids.add(signal_id)
            label = getattr(entry, "text", None) or entry.label
            scope = tuple(getattr(entry, "details", ())) or tuple(filter(None, (getattr(entry, "description", None),)))
            provenance = profile.field_provenance.get(category + "." + identifier)
            origins = tuple(r.origin + ":" + r.reference for r in provenance.source_refs) if provenance else ()
            uncertainty = provenance.uncertainty if provenance else "none"
            # Human-reviewed resume fields can retain MODEL_INFERENCE in the
            # legacy enum. Admit ONLY their explicit retained resume provenance;
            # a model_inference origin never becomes a reported fact by a flag.
            explicit = (entry.inference_type == InferenceType.EXPLICIT_FACT and
                        entry.source_type != EvidenceSourceType.MODEL_INFERENCE)
            resume_report = bool(provenance and all(r.origin == "resume_evidence" for r in provenance.source_refs))
            owned = tuple(entry.evidence_ids)
            if len(set(owned)) != len(owned): raise ValueError("D5_DUPLICATE_OWNERSHIP")
            model_origin = bool(provenance and any(r.origin == "model_inference" for r in provenance.source_refs))
            eligible = (uncertainty == "none" and category != "uncertainties" and not model_origin and
                        (explicit or resume_report) and all(
                            evidence[e].source_type != EvidenceSourceType.MODEL_INFERENCE or resume_report for e in owned))
            size = len(label) + sum(map(len, scope)) + sum(len(evidence[e].statement) for e in owned)
            if (not owned or any(len(t) > 600 for t in (label, *(evidence[e].statement for e in owned))) or
                    size > 2200 or characters + size > 16000 or len(signals) >= 40):
                partial = True
                continue
            characters += size
            signals.append(UserSignal(signal_id=signal_id, category=category, label=label, scope=scope,
                source_type=entry.source_type.value, inference_type=entry.inference_type.value,
                origins=origins, uncertainty=uncertainty, eligible=eligible, evidence_ids=owned))
    included = {e for s in signals for e in s.evidence_ids}
    return UserProjection(profile_id=profile.profile_id, profile_version=profile.version,
        profile_fingerprint=fingerprint(profile.model_dump(mode="json")), partial=partial, signals=tuple(signals),
        evidence=tuple(UserEvidence(evidence_id=e.id, text=e.statement, source_type=e.source_type.value,
            source_name=e.source_name) for e in profile.evidence if e.id in included))


def project_work(source):
    # Never trust an arbitrary typed instance or changed in-memory prose.
    canonical = next((s for s in SpecificRoleRegistry().inventory().records
                      if s.representative_role_id == source.representative_role_id), None)
    if canonical is None or canonical != source:
        raise ValueError("D5_INVALID_D4_SOURCE")
    service, signals, evidence = SpecificRoleService(), [], []
    for dimension in list(Dimension)[1:]:
        reply = service.reply(source, dimension)
        service.validate(reply, source)
        for block in reply.blocks:
            signals.append(WorkSignal(signal_id="work:" + block.source_ref, field=block.field,
                label=block.text, authority=block.authority, evidence_ids=(block.source_ref,)))
            evidence.append(WorkEvidence(evidence_id=block.source_ref, text=block.text,
                source_type=source.source_type, membership_refs=block.membership_refs))
    return WorkProjection(role_id=source.representative_role_id, role_label=source.display_name,
        source_id=source.source_id, source_version=source.version,
        source_fingerprint=fingerprint(source.model_dump(mode="json")), scope=source.scope,
        variation=source.organizational_variation, unknowns=source.unknowns,
        signals=tuple(signals), evidence=tuple(evidence))
