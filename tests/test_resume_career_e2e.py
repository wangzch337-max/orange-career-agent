"""C.5A true upload-to-confirm E2E, fault injection, isolation and privacy audits."""

from contextlib import contextmanager
from dataclasses import replace
import json
import sqlite3
from threading import Event, Thread
from uuid import uuid4

import pytest

from career_background_evaluation.harness import CareerHarness, CapturingFake
from career_background_evaluation.scenarios import SCENARIOS, CONTACTS, RAW_MARKER
from career_runtime.engine import TurnComplete
from clarification.policy import TurnIntent, ClarificationStatus
from profile_refinement.models import Resolution, Status
from resume_evidence.session import ResumeAnalysisStatus
from resume_intake.models import ResumeParseStatus
from tests.agent_doubles import ScriptedProvider, plan, answer
from ui.chat_runtime import Workspace


@pytest.fixture(autouse=True)
def forbid_credentials_and_live_construction(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("C.5A forbids live configuration/provider access")
    monkeypatch.setattr("providers.models.load_llm_settings", forbidden)
    monkeypatch.setattr("resume_evidence.session._qwen_provider", forbidden)


@pytest.fixture
def h(tmp_path):
    value = CareerHarness(tmp_path, SCENARIOS[3])
    try:
        yield value
    finally:
        value.close()


def initial(h, *, memory=False, edit=False):
    h.prepare(); h.resolve_all(edit=edit)
    return h.confirm(memory=memory)


def test_first_profile_complete_atomic_explicit_and_idempotent(h):
    draft = h.prepare()
    assert not h.current() and not h.history() and not h.memories()
    s = h.workspace.profile_refinement
    assert s.confirm(s.token(), confirmed_by_user=True) is None  # Pending fields cannot commit.
    assert not h.history()
    h.resolve_all(edit=True)
    profile = h.confirm(memory=True)
    assert profile.version == 1 and len(profile.work_experience) == 1 and not profile.projects
    assert h.history() == [profile] and len(h.memories()) == 1
    key = next(key for key in profile.field_provenance if key.startswith("goals."))
    assert profile.field_provenance[key].uncertainty == "explicit_uncertainty"
    assert profile.field_provenance[key].source_refs[0].origin == "explicit_user_edit"
    assert s.confirm(s.token(), confirmed_by_user=True) == profile
    assert h.history() == [profile] and len(h.memories()) == 1
    h.universal_checks(profile); h.privacy_checks(profile)


def test_existing_user_delta_only_partial_accept_edit_keep_and_memory_supersede(h):
    # Create v1 through the actual upload/consent/clarification/draft/confirm pipeline.
    h.scenario = replace(SCENARIOS[3], answer="我希望继续审计与财务。", goal_label="继续审计与财务", uncertain=False)
    from career_background_evaluation.harness import delta_program
    h.refiner.program = delta_program(h.scenario)
    base = initial(h, memory=True)
    old_memory = h.memories()[0]
    new = CareerHarness(h.root, SCENARIOS[4], workspace=h.workspace)
    new.upload(); new.analyze()
    decision = h.workspace.clarification.run(TurnIntent.RESUME_REVIEW, current_statement="我现在希望探索数据或业务分析转向。")
    assert decision.should_ask
    q = h.workspace.clarification.current_question()
    assert q.need.reason_code.value == "PROFILE_RESUME_CONFLICT"
    assert h.workspace.clarification.answer(q, new.scenario.answer)
    draft = new.draft()
    assert h.current() == base and h.memories() == [old_memory]
    assert len(draft.changes) == 2 and any(c.conflict_state != "none" for c in draft.changes)
    new.resolve_all(edit=True, keep_category="work_experience")
    final = new.confirm(memory=True)
    assert final.version == 2 and new.history() == [base, final]
    assert final.work_experience == base.work_experience  # Rejected addition does not erase history.
    for name in ("skills", "education", "values", "interests", "projects", "career_preferences"):
        assert getattr(final, name) == getattr(base, name)
    provenance = final.field_provenance["goals." + final.goals[0].goal_id]
    assert provenance.uncertainty == "explicit_uncertainty" and provenance.source_refs[0].origin == "explicit_user_edit"
    assert h.workspace.profile_refinement.memory_status == "SUPERSEDED"
    assert len(new.memories()) == 1 and new.memories()[0].memory_id != old_memory.memory_id
    assert new.memories()[0].content == final.goals[0].label
    assert new.memories()[0].evidence_refs == final.goals[0].evidence_ids
    expected_memory = new.memories()
    scope = h.workspace.owner_scope_id
    h.close()
    with Workspace(scope, h.root) as restored:
        assert restored.memory_service.get_current_confirmed_profile(restored.subject_id) == final
        assert restored.memory_service.profile_store.list_profile_history(restored.subject_id) == [base, final]
        assert restored.memory_service.memory_store.list_active(restored.subject_id) == expected_memory
        assert restored.resume_intake.result is None and restored.resume_analysis.bundle is None
        assert restored.profile_refinement.draft is None and not restored.clarification.state.answer_candidates
        fresh = restored.create_new_thread()
        assert (fresh.profile_id_ref, fresh.profile_version_ref) == (final.profile_id, 2)


def test_no_material_change_has_no_review_new_version_or_duplicate_memory(h):
    base = initial(h, memory=True)
    memories = h.memories()
    h.upload(); h.analyze()
    assert not h.workspace.clarification.run(TurnIntent.RESUME_REVIEW).should_ask
    draft = h.draft()
    assert draft.status == Status.NO_MATERIAL_CHANGE and not draft.changes
    assert h.workspace.profile_refinement.confirm(h.workspace.profile_refinement.token(), confirmed_by_user=True) is None
    assert h.history() == [base] and h.current() == base and h.memories() == memories


@pytest.mark.parametrize("dependency", ["replace", "base_version", "new_chat", "delete", "revoke"])
def test_complete_old_confirmation_rejected_after_dependency_change(h, dependency):
    base = initial(h, memory=True)
    memory = h.memories()
    fresh = CareerHarness(h.root, SCENARIOS[4], workspace=h.workspace)
    fresh.upload(); fresh.analyze()
    fresh.draft(); fresh.resolve_all()
    s = h.workspace.profile_refinement
    token, thread = s.token(), h.workspace.thread.thread_id
    expected = base
    if dependency == "replace": fresh.upload()
    elif dependency == "base_version":
        expected = base.create_revision(education_summary="Public synthetic reviewed update").confirm()
        h.workspace.memory_service.save_confirmed_profile(h.workspace.subject_id, expected)
    elif dependency == "new_chat": h.workspace.create_new_thread()
    elif dependency == "delete": h.workspace.delete_thread(thread)
    else: h.workspace.resume_analysis.revoke()
    assert s.confirm(token, confirmed_by_user=True) is None
    assert h.current() == expected and h.memories() == memory
    assert h.history() == ([base, expected] if dependency == "base_version" else [base])
    if dependency != "base_version":
        assert not h.workspace.resume_analysis.has_consent and h.workspace.resume_analysis.bundle is None
        assert not h.workspace.clarification.state.answer_candidates and s.draft is None
        if dependency != "revoke": assert h.workspace.resume_intake.result is None or dependency == "replace"


def test_two_clients_canonical_and_candidate_scope_are_isolated(tmp_path):
    a, b = CareerHarness(tmp_path, SCENARIOS[3]), CareerHarness(tmp_path, SCENARIOS[5])
    try:
        a.prepare(); a.resolve_all()
        b.prepare(); b.resolve_all()
        token = a.workspace.profile_refinement.token()
        assert b.workspace.profile_refinement.confirm(token, confirmed_by_user=True) is None
        assert b.workspace.profile_refinement.status == Status.OWNER_SCOPE_MISMATCH
        assert a.current() is None and b.current() is None
        final = a.confirm(memory=True)
        assert b.current() is None and not b.memories()
        assert a.workspace.thread.thread_id not in {t.thread_id for t in b.workspace.threads}
        assert a.workspace.resume_analysis.bundle.source_id != b.workspace.resume_analysis.bundle.source_id
        a.workspace.create_new_thread()
        assert a.current() == final and a.workspace.profile_refinement.draft is None
        assert b.workspace.profile_refinement.draft is not None
    finally:
        a.close(); b.close()


def test_general_qa_with_open_resume_question_uses_actual_normal_pipeline(h):
    h.upload(); h.analyze()
    h.workspace.clarification.run(TurnIntent.RESUME_REVIEW)
    q = h.workspace.clarification.current_question()
    version = h.workspace.clarification.state.version
    calls = [p.attempts for p in h.providers]
    provider = ScriptedProvider([plan()], answer("generator 是 iterator 的一种；yield 保留执行状态。"))
    session = h.workspace.agent_session
    session.provider_factory = lambda: provider
    session.queue("Python generator 和 iterator 有什么区别？", "typed")
    events = list(session.stream_turn(session.pending))
    assert any(isinstance(event, TurnComplete) for event in events)
    assert provider.structured_calls == provider.stream_calls == 1
    assert not provider.requests[-1]["selected_context"]
    assert h.workspace.clarification.current_question() == q
    assert h.workspace.clarification.state.version == version
    assert [p.attempts for p in h.providers] == calls and not h.current() and not h.memories()
    assert h.workspace.clarification.answer(q, "unrelated technical question", intent=TurnIntent.UNRELATED) is None
    assert h.workspace.clarification.current_question() == q and not h.workspace.clarification.state.answer_candidates


@pytest.mark.parametrize("stage", ["extraction", "clarification", "refinement"])
def test_late_worker_after_delete_cannot_resurrect_any_stage(h, stage):
    h.upload()
    if stage != "extraction": h.analyze()
    if stage == "refinement": h.clarify()
    entered, release = Event(), Event()
    fake = {"extraction": h.extraction, "clarification": h.clarifier, "refinement": h.refiner}[stage]
    native = fake.program
    def delayed(payload):
        entered.set()
        assert release.wait(5)
        return native(payload)
    fake.program = delayed
    if stage == "extraction":
        h.workspace.resume_analysis.grant_current()
        operation = h.workspace.resume_analysis.analyze
    elif stage == "clarification": operation = lambda: h.workspace.clarification.run(TurnIntent.RESUME_REVIEW)
    else: operation = lambda: h.workspace.profile_refinement.start(explicit_review=True)
    errors = []
    def work():
        try: operation()
        except Exception as error: errors.append(type(error).__name__)
    worker = Thread(target=work)
    worker.start()
    try:
        assert entered.wait(5)
        h.workspace.delete_thread(h.workspace.thread.thread_id)
    finally:
        release.set(); worker.join(5)
    assert not worker.is_alive() and not errors
    assert h.workspace.resume_intake.result is None and h.workspace.resume_analysis.bundle is None
    assert not h.workspace.clarification.state.answer_candidates and h.workspace.clarification.current_question() is None
    assert h.workspace.profile_refinement.draft is None and not h.history() and not h.memories()


@pytest.mark.parametrize("failure", ["parse", "evidence_provider", "evidence_malformed", "evidence_refs", "clarification_provider", "clarification_malformed", "refinement_provider", "draft_refs"])
def test_e2e_failure_injection_safe_terminal_stage_no_authority(h, failure, caplog):
    def fail(_): raise RuntimeError("PUBLIC_SYNTHETIC_UNTRUSTED_ERROR_MARKER")
    if failure == "parse":
        h.workspace.resume_intake.select(h.workspace.owner_scope_id, h.workspace.thread.thread_id, "synthetic.pdf", b"PUBLIC_SYNTHETIC_UNTRUSTED_ERROR_MARKER")
        assert h.workspace.resume_intake.parse_pending().status == ResumeParseStatus.PARSE_FAILED
        assert h.workspace.resume_intake.pending is None
    else:
        h.upload()
        if failure.startswith("evidence"):
            native = h.extraction.program
            if failure.endswith("provider"): h.extraction.program = fail
            elif failure.endswith("malformed"): h.extraction.program = lambda _: {"unexpected": "PUBLIC_SYNTHETIC_UNTRUSTED_ERROR_MARKER"}
            else:
                def bad_refs(payload):
                    result = native(payload)
                    result["items"][0]["source_block_ids"] = ["unowned_source"]
                    return result
                h.extraction.program = bad_refs
            h.workspace.resume_analysis.grant_current()
            status = h.workspace.resume_analysis.analyze()
            assert status == {"evidence_provider": ResumeAnalysisStatus.PROVIDER_FAILED, "evidence_malformed": ResumeAnalysisStatus.INVALID_STRUCTURED_OUTPUT, "evidence_refs": ResumeAnalysisStatus.INVALID_SOURCE_REFERENCE}[failure]
            h.workspace.resume_analysis.analyze()
            assert h.extraction.attempts == 1 and h.workspace.resume_analysis.bundle is None
        else:
            h.analyze()
            if failure.startswith("clarification"):
                h.clarifier.program = fail if failure.endswith("provider") else lambda _: {"unexpected": True}
                assert not h.workspace.clarification.run(TurnIntent.RESUME_REVIEW).should_ask
                assert h.workspace.clarification.status == (ClarificationStatus.PROVIDER_FAILED if failure.endswith("provider") else ClarificationStatus.INVALID_CLARIFICATION_PLAN)
                h.workspace.clarification.run(TurnIntent.RESUME_REVIEW)
                assert h.clarifier.attempts == 1 and not h.workspace.clarification.current_question()
            else:
                h.clarify()
                native = h.refiner.program
                if failure.endswith("provider"): h.refiner.program = fail
                else:
                    def bad_draft(payload):
                        result = native(payload)
                        result["changes"][0]["source_refs"] = ["rs_999"]
                        return result
                    h.refiner.program = bad_draft
                assert h.workspace.profile_refinement.start(explicit_review=True) is None
                assert h.workspace.profile_refinement.status in {Status.PROVIDER_FAILED, Status.INVALID_DRAFT, Status.INVALID_REFERENCE}
                assert h.refiner.attempts == 1
    assert not h.current() and not h.history() and not h.memories()
    safe = repr([session.events for session in (h.workspace.resume_intake, h.workspace.resume_analysis, h.workspace.clarification, h.workspace.profile_refinement)]) + caplog.text
    assert "PUBLIC_SYNTHETIC_UNTRUSTED_ERROR_MARKER" not in safe


@pytest.mark.parametrize("failure", ["insert", "pointer", "commit"])
def test_full_e2e_profile_transaction_failure_rolls_back_both(h, monkeypatch, failure):
    base = initial(h, memory=True)
    before = h.memories()
    new = CareerHarness(h.root, SCENARIOS[4], workspace=h.workspace)
    new.upload(); new.analyze(); new.draft(); new.resolve_all()
    database = h.workspace.memory_service.database
    native = database.connection
    class Fault:
        def __init__(self, connection): self.connection = connection
        def execute(self, sql, *args):
            if (failure == "insert" and "INSERT INTO profile_versions" in sql or failure == "pointer" and "INSERT INTO current_profiles" in sql):
                raise sqlite3.OperationalError("PUBLIC_SYNTHETIC_DB_FAULT")
            return self.connection.execute(sql, *args)
        def commit(self):
            if failure == "commit": raise sqlite3.OperationalError("PUBLIC_SYNTHETIC_DB_FAULT")
            self.connection.commit()
    @contextmanager
    def connection():
        with native() as value: yield Fault(value)
    with monkeypatch.context() as patch:
        patch.setattr(database, "connection", connection)
        s = h.workspace.profile_refinement
        assert s.confirm(s.token(), confirmed_by_user=True) is None
        assert s.status == Status.PROFILE_CONFIRMATION_FAILED
    assert h.current() == base and h.history() == [base] and h.memories() == before
    assert "PUBLIC_SYNTHETIC_DB_FAULT" not in repr(s.events)


def test_full_e2e_optional_memory_failure_preserves_profile_and_reports_partial(h, monkeypatch):
    h.prepare(); h.resolve_all()
    observed = []
    def failure(**kwargs):
        observed.append(h.current())
        raise RuntimeError("PUBLIC_SYNTHETIC_MEMORY_FAULT")
    monkeypatch.setattr(h.workspace.memory_service, "create_confirmed", failure)
    final = h.confirm(memory=True)
    s = h.workspace.profile_refinement
    assert observed == [final] and h.history() == [final] and not h.memories()
    assert s.memory_status == Status.MEMORY_SIDE_EFFECT_FAILED.value
    assert any(e.event == "profile_memory_side_effect_failed" for e in s.events)
    assert s.confirm(s.token(), confirmed_by_user=True) == final and observed == [final]
    assert "PUBLIC_SYNTHETIC_MEMORY_FAULT" not in repr(s.events)


def test_curated_memory_deduplicates_exact_unchanged_signal_across_new_revision(h):
    base = initial(h, memory=True)
    old = h.memories()
    new = CareerHarness(h.root, SCENARIOS[4], workspace=h.workspace)
    new.upload(); new.analyze()
    new.draft(); new.resolve_all(); final = new.confirm()
    assert final.version == base.version + 1 and new.memories() == old
    assert final.goals == base.goals


def test_real_observability_and_logs_do_not_store_provider_or_source_content(h, caplog):
    from observability.collector import DiagnosticEventCollector
    from observability.context import diagnostic_scope
    from observability.models import ObservabilityContext, run_id
    collector = DiagnosticEventCollector()
    context = ObservabilityContext(run_id=run_id(), subject_id=h.workspace.subject_id)
    with diagnostic_scope(collector, context):
        final = initial(h, memory=True)
    events = collector.timeline(context.run_id)
    assert events and any(e.operation == "provider_call" for e in events)
    safe = json.dumps([e.model_dump(mode="json") for e in events], ensure_ascii=False) + caplog.text
    for value in (RAW_MARKER, h.answer_text, *[f.label for f in h.scenario.facts], *CONTACTS, h.raw_text):
        assert value not in safe
    assert not any(s in safe for s in ("source_quotes", "api_key", "reasoning", "messages"))
    assert not collector.recording_failure_count
    h.privacy_checks(final)


@pytest.mark.parametrize("path", ["/Users/synthetic-developer/resume.pdf", "/home/synthetic-developer/resume.docx", "file:///synthetic/resume.pdf", "C:\\synthetic\\resume.docx"])
def test_public_safe_path_guard_encoding_keeps_all_rejections(path):
    from profile_refinement.models import Value, RefinementError
    from profile_refinement.service import check_value
    with pytest.raises(RefinementError):
        check_value("work_experience", Value(label=path))


@pytest.mark.parametrize("contact", CONTACTS)
@pytest.mark.parametrize("entry_point", ["provider", "user_edit"])
def test_arbitrary_contact_is_not_a_canonical_career_field(h, contact, entry_point):
    if entry_point == "provider":
        h.upload(); h.analyze(); h.clarify()
        native = h.refiner.program
        def contact_delta(payload):
            result = native(payload)
            result["changes"][0]["proposed_value"]["label"] = contact
            return result
        h.refiner.program = contact_delta
        assert h.workspace.profile_refinement.start(explicit_review=True) is None
        assert h.workspace.profile_refinement.status == Status.INVALID_DRAFT
    else:
        h.prepare()
        s = h.workspace.profile_refinement
        change = s.draft.changes[0]
        edited = change.proposed_value.model_dump()
        edited["label"] = contact
        assert not s.resolve(s.token(), change.change_id, Resolution.EDIT, edited_value=edited)
        assert s.status == Status.INVALID_DRAFT
    assert not h.current() and not h.history() and not h.memories()


def test_bounded_normalized_resume_flows_to_review_confirm_and_isolated_reload(h, caplog):
    """Same public C.5A career; normalization doesn't promote candidate authority."""
    claim = "Experience preparing statutory audit working papers; reconciling financial records; Audit Associate"
    native = h.extraction.program
    def normalized(payload):
        output = native(payload)
        output["items"][0]["normalized_claim"] = claim
        return output
    h.extraction.program = normalized
    draft = h.prepare()
    assert draft.proposed_profile_version == 1 and not h.current() and not h.history() and not h.memories()
    assert h.workspace.resume_analysis.bundle.authority == "candidate"
    assert h.workspace.clarification.state.answer_candidates[0].uncertainty == "explicit_uncertainty"
    h.resolve_all(edit=True)
    profile = h.confirm()  # No forced Memory side effect.
    assert profile.version == 1 and profile.work_experience[0].label == h.workspace.resume_analysis.bundle.items[0].canonical_label and not profile.projects
    assert claim not in profile.model_dump_json()
    assert h.history() == [profile] and not h.memories()
    assert [p.attempts for p in h.providers] == [1,1,1]
    h.privacy_checks(profile)
    assert claim not in caplog.text and h.raw_text not in caplog.text
    owner, root = h.workspace.owner_scope_id, h.root
    h.close()
    with Workspace(owner,root) as restored:
        assert restored.memory_service.get_current_confirmed_profile(restored.subject_id) == profile
        assert restored.memory_service.profile_store.list_profile_history(restored.subject_id) == [profile]
        assert restored.resume_intake.result is None and not restored.resume_analysis.has_consent
        assert restored.resume_analysis.bundle is None and restored.profile_refinement.draft is None
        assert not restored.clarification.state.answer_candidates
        fresh = restored.create_new_thread()
        assert (fresh.profile_id_ref,fresh.profile_version_ref) == (profile.profile_id,1)
