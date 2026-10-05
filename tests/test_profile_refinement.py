"""Focused C.4 authority, transaction and universal-shape tests, never broad eval."""

from contextlib import contextmanager
from dataclasses import asdict, replace
import json
from pathlib import Path
import sqlite3

import pytest
from pydantic import ValidationError

from data.models import (CandidateSkill, CareerPreference, EvidenceSourceType as EST, PROFILE_OPTIONAL_SECTIONS,
                         ProfileSectionEntry, UserProfile)
from memory.errors import ProfileVersionConflictError
from memory.models import MemoryContext, MemoryContextItem, MemoryType, ProfileReference
from memory.sqlite_store import _canonical_json, _hash_json
from profile_refinement.context import ProfileRefinementContextBuilder, binding_for_refinement, digest
from profile_refinement.models import ChangeType, RefinementError, RefinementOutput, Resolution, Status, Value
from profile_refinement.service import fingerprint_draft
from tests.clarification_doubles import profile_for, bundle_for
from tests.profile_refinement_doubles import Harness, goal_plan, proposal, work_plan


def test_initial_draft_is_v1_unconfirmed_and_only_explicit_confirmation_writes(tmp_path):
    h = Harness(tmp_path)
    draft = h.start()
    assert draft and draft.proposed_profile_version == 1 and draft.binding.base_profile_id is None
    assert not h.history() and not h.memories()
    assert h.session.confirm(h.session.token()) is None
    assert not h.history()
    h.review()
    final = h.confirm()
    assert final.confirmed and final.version == 1 and len(final.work_experience) == 1
    assert not final.projects and not final.education and not final.goals and not h.memories()


def test_refines_not_reconstructs_preserves_all_unchanged_fields_and_old_history(tmp_path):
    base = profile_for("继续审计")
    base.education_summary = "Synthetic accounting qualification"
    h = Harness(tmp_path, profile=base)
    before = base.model_dump(mode="json")
    assert h.start().proposed_profile_version == 2 and h.history() == [base]
    h.review()
    final = h.confirm()
    for key, value in before.items():
        if key not in {"version", "updated_at", "confirmed_at", "work_experience", "evidence", "field_provenance"}:
            assert final.model_dump(mode="json")[key] == value, key
    assert h.history() == [base, final]
    assert h.service.get_current_confirmed_profile(h.inputs.subject_id) == final
    assert h.service.profile_store.get_profile_version(h.inputs.subject_id, base.profile_id, 1) == base


@pytest.mark.parametrize("source", ["current", "answer"])
def test_current_or_clarification_update_is_explicit_conflict_until_review(tmp_path, source):
    h = Harness(tmp_path, profile=profile_for("继续审计"), plan=goal_plan,
                current="我最近更想转向数据分析。" if source == "current" else "")
    if source == "answer":
        h.answer()
    draft = h.start()
    c = draft.changes[0]
    assert c.old_value.label == "继续审计" and c.proposed_value.label == "正在探索数据分析"
    assert c.change_type == ChangeType.CONFLICT and c.conflict_state == "requires_review"
    assert h.confirm() is None and h.history()[0].goals[0].label == "继续审计"
    h.review(Resolution.UNCERTAIN)
    final = h.confirm()
    provenance = final.field_provenance["goals.goal_001"]
    assert provenance.uncertainty == "explicit_uncertainty" and provenance.confirmed_by_user
    assert provenance.source_refs[0].origin == ("explicit_user_input" if source == "current" else "clarification_answer")


def test_edit_remains_authoritative_after_later_confirm_or_uncertain(tmp_path):
    h = Harness(tmp_path, background="mechanical")
    h.start()
    c = h.session.draft.changes[0]
    edited = c.proposed_value.model_dump()
    edited.update(label="协助审核公差；未独立负责维修", details=["协助计划维护任务"])
    assert h.session.resolve(h.session.token(), c.change_id, Resolution.EDIT, edited_value=edited)
    assert not h.history() and not h.memories()
    assert h.session.resolve(h.session.token(), c.change_id, Resolution.UNCERTAIN)
    final = h.confirm()
    assert final.work_experience[0].label == edited["label"]
    refs = final.field_provenance[f"work_experience.{c.target_id}"].source_refs
    assert refs[0].origin == "explicit_user_edit"
    assert c.proposed_value.label != final.work_experience[0].label


@pytest.mark.parametrize("choice", [Resolution.KEEP_OLD, Resolution.REJECT])
def test_rejected_changes_do_not_reappear_or_write_memory(tmp_path, choice):
    h = Harness(tmp_path, profile=profile_for("继续审计"), plan=goal_plan, current="我最近更想转向数据分析")
    h.start()
    h.review(choice)
    assert h.confirm() is None
    assert h.session.status == Status.NO_MATERIAL_CHANGE and len(h.history()) == 1 and not h.memories()
    assert h.history()[0].goals[0].label == "继续审计"


def test_partial_acceptance_keeps_old_goal_and_accepts_work(tmp_path):
    def both(payload):
        return {"outcome": "CHANGES", "changes": [*goal_plan(payload)["changes"], *work_plan(payload)["changes"]]}
    h = Harness(tmp_path, profile=profile_for("继续审计"), plan=both, current="我最近更想转向数据分析")
    draft = h.start()
    for c in draft.changes:
        h.session.resolve(h.session.token(), c.change_id, Resolution.KEEP_OLD if c.category == "goals" else Resolution.CONFIRM)
    final = h.confirm()
    assert final.goals == h.history()[0].goals and len(final.work_experience) == 1
    assert len(final.field_provenance) == 1


@pytest.mark.parametrize("plan_type", ["empty", "unchanged", "same_add"])
def test_no_material_change_has_no_version_churn_or_duplicate_memory(tmp_path, plan_type):
    h = Harness(tmp_path)
    h.start(); h.review(); base = h.confirm()
    def plan(payload):
        if plan_type == "empty":
            return {"outcome": "NO_MATERIAL_CHANGE", "changes": []}
        pf = next(s for s in payload["sources"] if s["origin"] == "confirmed_profile")
        rs = next(s for s in payload["sources"] if s["origin"] == "resume_evidence")
        p = proposal(pf, target=pf["target_id"] if plan_type == "unchanged" else None,
            refs=[pf["ref"], rs["ref"]], change_type="UNCHANGED" if plan_type == "unchanged" else "ADD")
        return {"outcome": "CHANGES", "changes": [p]}
    h.fake.plan = plan
    h.service.create_confirmed(subject_id=h.inputs.subject_id, memory_type=MemoryType.GOAL,
        content="已确认的合成目标", source_type=EST.EXPLICIT_USER_INPUT, confirmed_by_user=True)
    memories = h.memories()
    assert h.start().status == Status.NO_MATERIAL_CHANGE
    assert h.confirm() is None and h.history() == [base] and h.memories() == memories


def skill_profile():
    return UserProfile(profile_id="synthetic_profile", skills=[CandidateSkill(skill_id="skill_001", label="Python",
        level="intermediate", confidence=1, source_type=EST.EXPLICIT_USER_INPUT)]).confirm()


def skill_plan(payload, level):
    pf = next((s for s in payload["sources"] if s["category"] == "skills" and s["origin"] == "confirmed_profile"), None)
    rs = next(s for s in payload["sources"] if s["origin"] == "resume_evidence")
    return {"outcome": "CHANGES", "changes": [proposal(rs, category="skills", target=pf["target_id"] if pf else None,
        value={"label": "Python", "level": level}, refs=[rs["ref"], *([pf["ref"]] if pf else [])], change_type="UPDATE" if pf else "ADD")]}


@pytest.mark.parametrize("base", [None, "existing"])
@pytest.mark.parametrize("level", ["advanced", "expert"])
def test_resume_only_cannot_create_or_inflate_proficiency(tmp_path, base, level):
    h = Harness(tmp_path, profile=skill_profile() if base else None, plan=lambda p: skill_plan(p, level))
    evidence = h.inputs.resume.items[0].model_dump()
    for key in ["role_title", "organization", "time_range", "responsibilities", "achievements", "domain_signals", "tools", "business_metrics"]:
        evidence.pop(key)
    evidence.update(category="skills", normalized_claim="Python")
    h.inputs = replace(h.inputs, resume=h.inputs.resume.model_copy(update={"items": (type(bundle_for(category="skills").items[0]).model_validate(evidence),)}))
    assert h.start() is None and h.session.status == Status.INVALID_DRAFT
    assert not h.memories()
    if base:
        assert h.history()[0].skills[0].level == "intermediate"


def test_resume_explicit_preference_is_conflict_not_overwrite(tmp_path):
    base = UserProfile(profile_id="synthetic_profile", career_preferences=[CareerPreference(
        preference_id="preference_001", label="审计", confidence=1, source_type=EST.EXPLICIT_USER_INPUT)]).confirm()
    def plan(payload):
        pf = next(s for s in payload["sources"] if s["origin"] == "confirmed_profile")
        rs = next(s for s in payload["sources"] if s["origin"] == "resume_evidence")
        return {"outcome": "CHANGES", "changes": [proposal(rs, category="career_preferences", target=pf["target_id"],
            value={"label": "数据分析"}, refs=[pf["ref"], rs["ref"]], change_type="UPDATE")]}
    h = Harness(tmp_path, profile=base, plan=plan)
    item = h.inputs.resume.items[0].model_copy(update={"claim_type": "explicit_career_statement"})
    h.inputs = replace(h.inputs, resume=h.inputs.resume.model_copy(update={"items": (item,)}))
    assert h.start().changes[0].conflict_state == "requires_review"
    assert h.history() == [base]
    h.review(Resolution.KEEP_OLD)
    assert h.confirm() is None and h.history() == [base]


def test_major_does_not_authorize_a_goal(tmp_path):
    def plan(payload):
        rs = next(s for s in payload["sources"] if s["origin"] == "resume_evidence")
        return {"outcome": "CHANGES", "changes": [proposal(rs, category="goals", value={"label": "Hospitality career", "goal_type": "career_goal"})]}
    h = Harness(tmp_path, background="student", plan=plan)
    assert h.start() is None and h.session.status == Status.INVALID_REFERENCE and not h.history()


@pytest.mark.parametrize("background", ["student", "audit", "mechanical", "marketing", "design", "switcher"])
def test_focused_universal_normalized_profile_shapes_reuse_existing_doubles(tmp_path, background):
    h = Harness(tmp_path, background=background)
    h.start(); h.review(); final = h.confirm()
    assert final and not final.projects and not final.goals
    assert len(final.education if background == "student" else final.work_experience) == 1
    if background == "switcher":
        assert "2010" in final.work_experience[0].time_range and not final.education


@pytest.mark.parametrize("section", PROFILE_OPTIONAL_SECTIONS)
def test_universal_optional_sections_are_valid_and_source_linked(section):
    value = UserProfile(profile_id="public_synthetic", **{section: [ProfileSectionEntry(
        entry_id="entry_001", label="public synthetic normalized value", confidence=1, source_type=EST.EXPLICIT_USER_INPUT)]}).confirm()
    assert getattr(value, section)[0].confirmed_by_user
    assert UserProfile.model_validate_json(value.model_dump_json()) == value


@pytest.mark.parametrize("kind", ["resume", "evidence", "answer", "clarification_version", "profile", "owner", "conversation"])
def test_binding_changes_reject_old_confirm_no_memory(tmp_path, kind):
    h = Harness(tmp_path, profile=profile_for("审计"))
    h.start(); h.review(); token = h.session.token()
    if kind == "resume":
        h.inputs = replace(h.inputs, resume=bundle_for())
    elif kind == "evidence":
        item = h.inputs.resume.items[0].model_copy(update={"responsibilities": ("Revised public synthetic audit responsibility",)})
        h.inputs = replace(h.inputs, resume=h.inputs.resume.model_copy(update={"items": (item,)}))
    elif kind == "answer":
        h.answer()
    elif kind == "clarification_version":
        h.inputs = replace(h.inputs, clarification_version=1)
    elif kind == "profile":
        h.service.save_confirmed_profile(h.inputs.subject_id, h.history()[0].create_revision(education_summary="public synthetic revision").confirm())
    elif kind == "owner":
        h.inputs = replace(h.inputs, owner_scope_id="other_owner")
    else:
        h.inputs = replace(h.inputs, conversation_id="other_thread")
    before = h.history()
    assert h.session.confirm(token, confirmed_by_user=True) is None
    assert h.session.status == Status.STALE_DRAFT and h.history() == before and not h.memories()


@pytest.mark.parametrize("operation", ["resolve", "confirm", "reject"])
def test_stale_action_identity_cannot_affect_new_draft(tmp_path, operation):
    h = Harness(tmp_path)
    old = h.start(); token = h.session.token()
    new = h.start()
    if operation == "resolve":
        assert not h.session.resolve(token, old.changes[0].change_id, Resolution.CONFIRM)
    elif operation == "confirm":
        assert h.session.confirm(token, confirmed_by_user=True) is None
    else:
        assert not h.session.reject(token)
    assert h.session.draft == new and not h.history() and not h.memories()


def test_old_fingerprint_cannot_edit_current_revision(tmp_path):
    h = Harness(tmp_path)
    draft = h.start(); token = h.session.token()
    assert h.session.resolve(token, draft.changes[0].change_id, Resolution.CONFIRM)
    assert not h.session.resolve(token, draft.changes[0].change_id, Resolution.EDIT, edited_value={"label": "bad late edit"})
    assert h.session.draft.changes[0].user_resolution == Resolution.CONFIRM


@pytest.mark.parametrize("fault", ["unknown_source", "unknown_target", "wrong_target_category", "missing_old_ref", "duplicate_ref", "unsupported_source", "extra_key", "too_many", "outcome_mismatch", "null_update"])
def test_invalid_provider_plan_fails_safe_no_automatic_repair(tmp_path, fault):
    def plan(payload):
        out = work_plan(payload)
        p = out["changes"][0]
        if fault == "unknown_source": p["source_refs"] = ["rs_999"]
        if fault == "unknown_target": p.update(target_id="not_current", change_type="UPDATE")
        if fault == "wrong_target_category": p.update(target_id="goal_001", change_type="UPDATE")
        if fault == "missing_old_ref": p.update(category="goals", target_id="goal_001", change_type="UPDATE", proposed_value={"label": "bad", "goal_type": "career_goal"})
        if fault == "duplicate_ref": p["source_refs"] *= 2
        if fault == "unsupported_source": p.update(category="skills", proposed_value={"label": "Invented skill"})
        if fault == "extra_key": p["reasoning"] = "not permitted"
        if fault == "too_many": out["changes"] *= 21
        if fault == "outcome_mismatch": out["outcome"] = "NO_MATERIAL_CHANGE"
        if fault == "null_update": p["proposed_value"] = None
        return out
    h = Harness(tmp_path, profile=profile_for("审计"), plan=plan)
    assert h.start() is None and h.fake.call_count == 1
    assert h.session.status in {Status.INVALID_DRAFT, Status.INVALID_REFERENCE}
    assert len(h.history()) == 1 and not h.memories()


def test_invalid_clarification_binding_is_rejected_before_provider(tmp_path):
    h = Harness(tmp_path, plan=goal_plan)
    a = h.answer()
    h.inputs = replace(h.inputs, answers=(a.model_copy(update={"binding": a.binding.model_copy(update={"resume_source_id": "other"})}),))
    assert h.start() is None and h.session.status == Status.INVALID_REFERENCE and h.fake.call_count == 0


@pytest.mark.parametrize("failure", ["insert", "pointer", "commit", "guard"])
def test_transaction_failure_rolls_back_profile_and_pointer(tmp_path, monkeypatch, failure):
    h = Harness(tmp_path, profile=profile_for("审计"))
    h.start(); h.review(); before = h.history()
    if failure == "guard":
        original = h.service.profile_store.save_confirmed_profile
        def mutate(*args, **kwargs):
            h.inputs = replace(h.inputs, clarification_version=99)
            return original(*args, **kwargs)
        monkeypatch.setattr(h.service.profile_store, "save_confirmed_profile", mutate)
    else:
        original_connection = h.service.database.connection
        class FailingConnection:
            def __init__(self, connection): self.connection = connection
            def execute(self, sql, *args):
                if failure == "insert" and "INSERT INTO profile_versions" in sql or failure == "pointer" and "INSERT INTO current_profiles" in sql:
                    raise sqlite3.OperationalError("synthetic database fault")
                return self.connection.execute(sql, *args)
            def commit(self):
                if failure == "commit": raise sqlite3.OperationalError("synthetic commit failure")
                self.connection.commit()
        @contextmanager
        def failing():
            with original_connection() as connection: yield FailingConnection(connection)
        monkeypatch.setattr(h.service.database, "connection", failing)
    assert h.confirm() is None and h.history() == before and not h.memories()
    assert h.service.get_current_confirmed_profile(h.inputs.subject_id) == before[0]


def test_compare_and_swap_rejects_race_and_version_skip_inside_transaction(tmp_path):
    h = Harness(tmp_path, profile=profile_for("审计"))
    old = h.history()[0]
    next_profile = old.create_revision(education_summary="synthetic revised").confirm()
    wrong = ProfileReference(subject_id=h.inputs.subject_id, profile_id=old.profile_id, version=9)
    with pytest.raises(ProfileVersionConflictError):
        h.service.profile_store.save_confirmed_profile(h.inputs.subject_id, next_profile, expected_current=wrong)
    skip = next_profile.create_revision(education_summary="synthetic skipped").confirm()
    with pytest.raises(ProfileVersionConflictError):
        h.service.profile_store.save_confirmed_profile(h.inputs.subject_id, skip, expected_current=ProfileReference(
            subject_id=h.inputs.subject_id, profile_id=old.profile_id, version=1))
    assert h.history() == [old]


def test_lost_commit_ack_recovers_exact_identity_once(tmp_path, monkeypatch):
    h = Harness(tmp_path)
    h.start(); h.review()
    original = h.service.profile_store.save_confirmed_profile
    def lost_ack(*args, **kwargs):
        original(*args, **kwargs)
        raise sqlite3.OperationalError("synthetic lost acknowledgement")
    monkeypatch.setattr(h.service.profile_store, "save_confirmed_profile", lost_ack)
    final = h.confirm()
    assert final and len(h.history()) == 1
    assert h.confirm() == final and len(h.history()) == 1


def test_preexisting_legacy_payload_hash_still_idempotent_with_empty_extensions(tmp_path):
    h = Harness(tmp_path)
    profile = profile_for("审计")
    old = profile.model_dump(mode="json", exclude=set(PROFILE_OPTIONAL_SECTIONS) | {"field_provenance"})
    semantic = {k: v for k, v in old.items() if k not in {"confirmed_at", "updated_at"}}
    with h.service.database.connection() as conn:
        conn.execute("INSERT INTO profile_versions VALUES (?, ?, ?, ?, ?, ?)",
            (h.inputs.subject_id, profile.profile_id, 1, _canonical_json(old), _hash_json(semantic), profile.created_at.isoformat()))
        conn.execute("INSERT INTO current_profiles VALUES (?, ?, ?, ?)",
            (h.inputs.subject_id, profile.profile_id, 1, profile.created_at.isoformat()))
        conn.commit()
    saved = h.service.save_confirmed_profile(h.inputs.subject_id, profile)
    assert not saved.created and saved.profile == profile


def test_memory_opt_in_runs_only_after_canonical_commit_and_dedups(tmp_path, monkeypatch):
    h = Harness(tmp_path, profile=profile_for("审计"), plan=goal_plan, current="我现在希望转向数据分析")
    h.start(); h.review(); c = h.session.draft.changes[0]
    assert not h.memories() and len(h.history()) == 1
    original = h.service.create_confirmed
    writes = []
    def observed(**kwargs):
        assert len(h.history()) == 2 and h.service.get_current_confirmed_profile(h.inputs.subject_id).version == 2
        writes.append(kwargs)
        return original(**kwargs)
    monkeypatch.setattr(h.service, "create_confirmed", observed)
    final = h.confirm(memory_change_id=c.change_id)
    assert final and len(writes) == 1 and h.memories()[0].content == "正在探索数据分析"
    assert h.confirm(memory_change_id=c.change_id) == final and len(writes) == 1
    assert h.memories()[0].memory_type == MemoryType.GOAL
    assert h.memories()[0].evidence_refs == final.goals[0].evidence_ids
    assert "work_experience" not in h.memories()[0].content


def test_existing_same_memory_deduplicated_without_write(tmp_path):
    h = Harness(tmp_path, plan=goal_plan, current="我现在希望转向数据分析")
    h.service.create_confirmed(subject_id=h.inputs.subject_id, memory_type=MemoryType.GOAL,
        content="正在探索数据分析", source_type=EST.EXPLICIT_USER_INPUT, confirmed_by_user=True)
    h.start(); h.review(); c = h.session.draft.changes[0]
    final = h.confirm(memory_change_id=c.change_id)
    assert final and len(h.memories()) == 1 and h.session.memory_status == "DEDUPLICATED"


def test_same_dimension_memory_supersedes_with_history(tmp_path):
    h = Harness(tmp_path, profile=profile_for("审计"), plan=goal_plan, current="我现在希望转向数据分析")
    previous = h.service.create_confirmed(subject_id=h.inputs.subject_id, memory_type=MemoryType.GOAL,
        content="继续审计", source_type=EST.EXPLICIT_USER_INPUT, confirmed_by_user=True,
        metadata={"signal_dimension": "profile.goals.goal_001", "signal_value": "继续审计"})
    h.start(); h.review(); c = h.session.draft.changes[0]
    final = h.confirm(memory_change_id=c.change_id)
    assert final and h.session.memory_status == "SUPERSEDED"
    assert len(h.memories()) == 1 and h.memories()[0].supersedes_memory_id == previous.memory_id
    assert h.service.memory_store.get(h.inputs.subject_id, previous.memory_id).status.value == "superseded"


def test_optional_memory_failure_never_rolls_back_confirmed_profile(tmp_path, monkeypatch):
    h = Harness(tmp_path, plan=goal_plan, current="我现在希望转向数据分析")
    h.start(); h.review(); c = h.session.draft.changes[0]
    monkeypatch.setattr(h.service, "create_confirmed", lambda **kw: (_ for _ in ()).throw(RuntimeError("synthetic private error")))
    final = h.confirm(memory_change_id=c.change_id)
    assert final.confirmed and h.history() == [final] and h.session.status == Status.CONFIRMED
    assert h.session.memory_status == "MEMORY_SIDE_EFFECT_FAILED" and not h.memories()
    assert "synthetic private error" not in repr(h.session.events)


def test_memory_allowlist_denies_skill_or_work_full_profile_dump(tmp_path):
    h = Harness(tmp_path)
    draft = h.start(); h.review()
    assert h.confirm(memory_change_id=draft.changes[0].change_id) is None
    assert not h.history() and not h.memories() and h.session.status == Status.INVALID_DRAFT


def test_rejected_whole_draft_zero_authority_writes(tmp_path):
    h = Harness(tmp_path)
    h.start(); h.review()
    assert h.session.reject(h.session.token())
    assert h.confirm() is None and not h.history() and not h.memories()


def test_only_allowlisted_confirmed_scoped_memory_enters_bounded_context(tmp_path):
    h = Harness(tmp_path)
    item = MemoryContextItem(memory_id="memory_synthetic", memory_type=MemoryType.GOAL,
        status="confirmed", content="合成历史职业目标", source_type=EST.EXPLICIT_USER_INPUT,
        authority="active_confirmed", fusion_rank=1)
    memory = MemoryContext(subject_id=h.inputs.subject_id, items=[item], max_records=6, character_count=8)
    context = h.session.builder.build(replace(h.inputs, memory=memory))
    assert any(s.origin == "confirmed_memory" for s in context.sources)
    with pytest.raises(RefinementError):
        h.session.builder.build(replace(h.inputs, memory=memory.model_copy(update={"subject_id": "other_subject"})))
    with pytest.raises(RefinementError):
        h.session.builder.build(replace(h.inputs, memory=memory.model_copy(update={"items": [item.model_copy(update={"memory_type": MemoryType.PROJECT_EVIDENCE})]})))


def test_context_is_bounded_and_no_raw_full_resume_or_identity_serialized(tmp_path):
    h = Harness(tmp_path, profile=profile_for("审计"), current="我想继续审计")
    h.answer()
    context = h.session.builder.build(h.inputs)
    payload = context.model_dump_json()
    quote = h.inputs.resume.items[0].source_quotes[0].excerpt
    assert quote not in payload and h.inputs.owner_scope_id not in payload
    assert h.inputs.resume.source_id not in payload and "source_quotes" not in payload and "origin_refs" not in payload
    crowded = UserProfile(profile_id="public_synthetic", work_experience=[ProfileSectionEntry(entry_id=f"work_{i}",
        label="Synthetic role " + str(i), details=["Synthetic responsibility " * 5], confidence=1,
        source_type=EST.EXPLICIT_USER_INPUT) for i in range(100)]).confirm()
    bounded = h.session.builder.build(replace(h.inputs, profile=crowded, answers=()))
    assert len(bounded.sources) <= 60 and len(bounded.model_dump_json()) <= 24_000 and bounded.partial


@pytest.mark.parametrize("bad", ["/Users/private/resume.pdf", "file:///private/synthetic", "system prompt: contents", "provider completion copied", "<script>unsafe</script>"])
def test_raw_paths_prompts_and_unsafe_edits_fail_without_persistence(tmp_path, bad):
    h = Harness(tmp_path)
    draft = h.start()
    assert not h.session.resolve(h.session.token(), draft.changes[0].change_id, Resolution.EDIT, edited_value={"label": bad})
    assert not h.history() and not h.memories()


def test_persisted_profile_and_safe_events_have_no_source_quote_prompt_completion(tmp_path, caplog):
    h = Harness(tmp_path)
    h.start(); h.review(); final = h.confirm()
    raw = final.model_dump_json()
    quote = h.inputs.resume.items[0].source_quotes[0].excerpt
    assert quote not in raw and "source_quotes" not in raw and "source_block_ids" not in raw
    assert "proposed_value" not in raw and "prompt" not in raw and "completion" not in raw
    events = json.dumps([asdict(e) for e in h.session.events])
    assert final.work_experience[0].label not in events and "source_refs" not in events and "user_answer" not in events
    assert quote not in caplog.text and final.work_experience[0].label not in caplog.text
    refs = next(iter(final.field_provenance.values())).source_refs
    assert any(r.origin == "resume_evidence" and h.inputs.resume.source_id in r.reference for r in refs)
    assert h.fake.options[0].thinking_enabled is False and h.fake.options[0].max_retries == 0
    assert "rs_001" in json.dumps(h.fake.schemas[0]) and "NO_MATERIAL_CHANGE" in json.dumps(h.fake.schemas[0])


def test_general_qa_does_not_start_provider_review(tmp_path):
    h = Harness(tmp_path)
    assert h.session.start(current_statement="Explain an unrelated idea") is None
    assert h.fake.call_count == 0 and not h.history() and h.session.status == Status.IDLE


def test_source_and_owner_token_mismatch_never_confirm(tmp_path):
    h = Harness(tmp_path)
    h.start(); h.review()
    token = h.session.token().model_copy(update={"owner_scope_id": "other_owner"})
    assert h.session.confirm(token, confirmed_by_user=True) is None and h.session.status == Status.OWNER_SCOPE_MISMATCH
    assert not h.history()


def test_provider_sources_cannot_omit_strongest_current_direction(tmp_path):
    h = Harness(tmp_path, profile=profile_for("审计"), plan=goal_plan, current="我现在想继续审计")
    h.answer()
    def ignored(payload):
        payload = {**payload, "sources": [s for s in payload["sources"] if s["origin"] != "explicit_user_input"]}
        return goal_plan(payload)
    h.fake.plan = ignored
    assert h.start() is None and h.session.status == Status.INVALID_REFERENCE


def test_user_explicit_remove_requires_review_and_retains_old_version(tmp_path):
    def remove(payload):
        pf = next(s for s in payload["sources"] if s["origin"] == "confirmed_profile")
        cu = next(s for s in payload["sources"] if s["origin"] == "explicit_user_input")
        return {"outcome": "CHANGES", "changes": [{"category": "goals", "target_id": pf["target_id"],
            "change_type": "REMOVE", "proposed_value": None, "source_refs": [pf["ref"], cu["ref"]],
            "reason_summary": "current_user_update", "uncertainty": "none"}]}
    h = Harness(tmp_path, profile=profile_for("继续审计"), plan=remove, current="请移除继续审计这个目标")
    draft = h.start()
    assert draft.changes[0].change_type == ChangeType.REMOVE and h.history()[0].goals
    h.review()
    final = h.confirm()
    assert final.version == 2 and not final.goals and h.history()[0].goals
    h.inputs = replace(h.inputs, current_statement="一般问答")


def test_explicit_goal_uncertainty_can_be_initial_confirmed_information(tmp_path):
    h = Harness(tmp_path, plan=goal_plan, current="Business Analyst / Data Analyst 都在考虑，我还不确定")
    draft = h.start()
    assert draft.changes[0].uncertainty == "explicit_uncertainty"
    h.review(Resolution.UNCERTAIN)
    final = h.confirm()
    assert final.confirmed and next(iter(final.field_provenance.values())).uncertainty == "explicit_uncertainty"


def test_same_uncertainty_repeated_is_no_change(tmp_path):
    h = Harness(tmp_path, plan=goal_plan, current="我还不确定，两个方向都在考虑")
    h.start(); h.review(Resolution.UNCERTAIN); base = h.confirm()
    assert h.start().status == Status.NO_MATERIAL_CHANGE
    assert h.history() == [base] and not h.memories()


@pytest.mark.parametrize("field,value", [("retry_count", 1), ("thinking_enabled", True), ("model", "other"),
                                        ("prompt_version", "v2"), ("provider", "other")])
def test_invalid_provider_envelope_is_rejected_without_repair(tmp_path, field, value):
    h = Harness(tmp_path)
    generate = h.fake.generate_structured
    def forged(*a, **kw):
        return generate(*a, **kw).model_copy(update={field: value})
    h.fake.generate_structured = forged
    assert h.start() is None and h.session.status == Status.INVALID_DRAFT
    assert h.fake.call_count == 1 and not h.history()


def test_confirm_rechecks_source_references_even_for_constructed_internal_candidate(tmp_path):
    h = Harness(tmp_path)
    draft = h.start(); h.review()
    change = h.session.draft.changes[0].model_copy(update={"source_refs": ("rs_999",)})
    forged = h.session.draft.model_copy(update={"changes": (change,)})
    h.session.draft = forged.model_copy(update={"draft_fingerprint": fingerprint_draft(forged)})
    assert h.confirm() is None and h.session.status == Status.INVALID_REFERENCE
    assert not h.history() and not h.memories()


def test_guard_failure_after_pointer_write_still_rolls_back_both(tmp_path, monkeypatch):
    h = Harness(tmp_path, profile=profile_for("审计"))
    h.start(); h.review()
    validate = h.session._validate_action
    count = 0
    def guarded(token):
        nonlocal count
        count += 1
        if count == 3:  # action, pre-insert, pre-commit
            raise RefinementError(Status.STALE_DRAFT)
        return validate(token)
    monkeypatch.setattr(h.session, "_validate_action", guarded)
    assert h.confirm() is None and count == 3
    assert len(h.history()) == 1 and h.service.get_current_confirmed_profile(h.inputs.subject_id).version == 1


def test_exact_shared_authority_contract_rejects_any_unapproved_byte():
    import subprocess
    from tests.profile_refinement_contract import SHARED_HASHES, assert_c4_shared_delta
    from tests.freeze_contract import PRE_RESUME_BASELINE
    root = Path(__file__).resolve().parents[1]
    for name in SHARED_HASHES:
        current = (root / name).read_bytes()
        original = subprocess.check_output(["git", "show", f"{PRE_RESUME_BASELINE}:{name}"], cwd=root)
        assert_c4_shared_delta(name, current, original)
        with pytest.raises(AssertionError): assert_c4_shared_delta(name, current + b"\n", original)
        with pytest.raises(AssertionError): assert_c4_shared_delta(name, current, original + b"\n")


def test_canonical_provenance_cannot_point_to_missing_field():
    from data.models import ProfileFieldProvenance, ProfileSourceReference, utc_now
    with pytest.raises(ValidationError):
        UserProfile(profile_id="synthetic", field_provenance={"goals.missing": ProfileFieldProvenance(
            source_refs=[ProfileSourceReference(origin="explicit_user_input", reference="public_synthetic")], last_confirmed_at=utc_now())})


def test_resume_skill_mention_does_not_duplicate_known_proficiency(tmp_path):
    h = Harness(tmp_path, profile=skill_profile(), plan=lambda p: skill_plan(p, None))
    resume = bundle_for(category="skills")
    item = resume.items[0].model_copy(update={"normalized_claim": "Python"})
    h.inputs = replace(h.inputs, resume=resume.model_copy(update={"items": (item,)}))
    h.fake.plan = lambda p: {"outcome": "CHANGES", "changes": [proposal(
        next(s for s in p["sources"] if s["origin"] == "resume_evidence"), value={"label": "Python"})]}
    assert h.start().status == Status.NO_MATERIAL_CHANGE
    assert len(h.history()[0].skills) == 1 and h.history()[0].skills[0].level == "intermediate"


def test_foreign_memory_reference_rejected_before_provider(tmp_path):
    h = Harness(tmp_path)
    item = MemoryContextItem(memory_id="foreign_memory", memory_type=MemoryType.GOAL,
        status="confirmed", content="合成历史目标", source_type=EST.EXPLICIT_USER_INPUT,
        authority="active_confirmed", fusion_rank=1)
    h.inputs = replace(h.inputs, memory=MemoryContext(subject_id=h.inputs.subject_id, items=[item], max_records=6, character_count=6))
    assert h.start() is None and h.session.status == Status.INVALID_REFERENCE and h.fake.call_count == 0


def test_modified_cached_base_cannot_smuggle_unreviewed_changes(tmp_path):
    h = Harness(tmp_path, profile=profile_for("审计"))
    h.start(); h.review()
    h.session.base.education_summary = "unreviewed synthetic change"
    assert h.confirm() is None and h.session.status == Status.STALE_DRAFT
    assert len(h.history()) == 1 and h.history()[0].education_summary is None


def test_uncertain_current_source_cannot_become_development_weakness(tmp_path):
    def unsupported(payload):
        cu = next(s for s in payload["sources"] if s["origin"] == "explicit_user_input")
        return {"outcome": "CHANGES", "changes": [proposal(cu, category="development_areas", value={"label": "能力不足"})]}
    h = Harness(tmp_path, current="我不确定，还未评估这项能力", plan=unsupported)
    assert h.start() is None and h.session.status == Status.INVALID_DRAFT and not h.history()


def test_confirmation_cleanup_runs_after_profile_lock_is_released(tmp_path):
    h = Harness(tmp_path)
    called = []
    def cleanup(binding):
        assert not h.session._lock._is_owned()
        assert h.history()[-1].confirmed
        called.append(binding)
    h.session.on_confirmed = cleanup
    h.start(); h.review()
    assert h.confirm() and len(called) == 1
