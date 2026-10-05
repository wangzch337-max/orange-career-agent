"""Focused actual Workspace/AppTest isolation, review and late-worker checks."""

from threading import Event, Thread
from uuid import uuid4

import pytest

from data.models import EvidenceSourceType
from memory.models import MemoryType
from profile_refinement.context import workspace_inputs, binding_for_refinement
from profile_refinement.models import Resolution, Status
from tests.clarification_doubles import profile_for
from tests.profile_refinement_doubles import DeltaFake, goal_plan
from tests.test_chat_product import app, WORKSPACE_KEY
from tests.test_clarification_ui import ready, snapshot
from ui.chat_runtime import Workspace


def prepared(workspace, background="audit"):
    ready(workspace, background)
    fake = DeltaFake()
    workspace.profile_refinement.provider_factory = lambda: fake
    return fake


@pytest.mark.parametrize("operation", ["new_chat", "switch", "delete", "close", "revoke", "replace"])
def test_lifecycle_invalidates_drafts_not_canonical_authority(tmp_path, operation):
    with Workspace(str(uuid4()), tmp_path) as w:
        base = profile_for("审计")
        w.memory_service.save_confirmed_profile(w.subject_id, base)
        memory = w.memory_service.create_confirmed(subject_id=w.subject_id, memory_type=MemoryType.GOAL,
            content="继续审计", source_type=EvidenceSourceType.EXPLICIT_USER_INPUT, confirmed_by_user=True)
        fake = prepared(w)
        s = w.profile_refinement
        draft = s.start(explicit_review=True)
        token = s.token()
        thread = w.thread.thread_id
        if operation == "new_chat": w.create_new_thread()
        elif operation == "switch": w.activate(w.store.create_thread(w.owner_scope_id).thread_id)
        elif operation == "delete": w.delete_thread(thread)
        elif operation == "close": w.close()
        elif operation == "revoke": w.resume_analysis.revoke()
        else:
            from tests.resume_evidence_doubles import docx_for
            w.resume_intake.select(w.owner_scope_id, thread, "replacement.docx", docx_for("student"))
        assert s.draft is None and fake.call_count == 1
        assert not s.resolve(token, draft.changes[0].change_id, Resolution.CONFIRM)
        assert s.confirm(token, confirmed_by_user=True) is None
        assert w.memory_service.get_current_confirmed_profile(w.subject_id) == base
        assert w.memory_service.memory_store.list_active(w.subject_id) == [memory]


@pytest.mark.parametrize("operation", ["delete", "new_chat", "revoke"])
def test_late_provider_output_cannot_resurrect_draft(tmp_path, operation):
    with Workspace(str(uuid4()), tmp_path) as w:
        prepared(w)
        entered, release = Event(), Event()
        class Late(DeltaFake):
            def generate_structured(self, *a, **kw):
                entered.set()
                assert release.wait(4)
                return super().generate_structured(*a, **kw)
        fake = Late()
        w.profile_refinement.provider_factory = lambda: fake
        worker = Thread(target=lambda: w.profile_refinement.start(explicit_review=True))
        worker.start()
        assert entered.wait(4)
        if operation == "delete": w.delete_thread(w.thread.thread_id)
        elif operation == "new_chat": w.create_new_thread()
        else: w.resume_analysis.revoke()
        release.set()
        worker.join(4)
        assert not worker.is_alive() and w.profile_refinement.draft is None
        assert w.memory_service.get_current_confirmed_profile(w.subject_id) is None


def test_current_client_canonical_profile_is_available_after_confirm_and_new_chat(tmp_path):
    scope = str(uuid4())
    with Workspace(scope, tmp_path) as w:
        prepared(w)
        s = w.profile_refinement
        s.start(explicit_review=True)
        for c in s.draft.changes: s.resolve(s.token(), c.change_id, Resolution.CONFIRM)
        final = s.confirm(s.token(), confirmed_by_user=True)
        assert not w.clarification.state.answer_candidates
        w.create_new_thread()
        assert w.thread.profile_id_ref == final.profile_id and w.thread.profile_version_ref == 1
        assert w.memory_service.get_current_confirmed_profile(w.subject_id) == final
        assert w.profile_refinement.draft is None
    with Workspace(scope, tmp_path) as restored:
        assert restored.memory_service.get_current_confirmed_profile(restored.subject_id) == final
        assert restored.profile_refinement.draft is None  # New process refresh is read-only.


def test_two_clients_and_review_tokens_isolated(tmp_path):
    with Workspace(str(uuid4()), tmp_path) as a, Workspace(str(uuid4()), tmp_path) as b:
        prepared(a); prepared(b)
        a.profile_refinement.start(explicit_review=True)
        b.profile_refinement.start(explicit_review=True)
        token = a.profile_refinement.token()
        foreign = b.profile_refinement.draft
        assert b.profile_refinement.confirm(token, confirmed_by_user=True) is None
        assert b.profile_refinement.status == Status.OWNER_SCOPE_MISMATCH and b.profile_refinement.draft == foreign
        assert a.memory_service.get_current_confirmed_profile(a.subject_id) is None
        assert b.memory_service.get_current_confirmed_profile(b.subject_id) is None


def test_bound_start_rejects_stale_ui_resume_before_provider(tmp_path):
    with Workspace(str(uuid4()), tmp_path) as w:
        fake = prepared(w)
        expected = binding_for_refinement(workspace_inputs(w))
        prepared(w, "mechanical")
        assert w.profile_refinement.start(explicit_review=True, expected_binding=expected) is None
        assert w.profile_refinement.status == Status.STALE_DRAFT and fake.call_count == 0


def test_native_ui_diff_review_explicit_edit_partial_confirm_and_no_automatic_model(tmp_path, monkeypatch):
    monkeypatch.setattr("resume_evidence.session._qwen_provider", lambda: (_ for _ in ()).throw(AssertionError("No live Qwen")))
    value = app(tmp_path, str(uuid4()))
    w = value.session_state[WORKSPACE_KEY]
    try:
        fake = prepared(w, "mechanical")
        value.run()
        assert fake.call_count == 0 and not w.profile_refinement.draft
        value.button(key="orange_profile_refinement_start").click().run()
        assert not value.exception and fake.call_count == 1
        s = w.profile_refinement
        assert s.draft and value.chat_input
        assert any(button.disabled for button in value.button if button.key and button.key.startswith("orange_profile_confirm_"))
        assert not w.memory_service.profile_store.list_profile_history(w.subject_id)
        # Unrelated composer still uses General QA, not an implicit Profile edit.
        forwarded = []
        monkeypatch.setattr(w, "submit", lambda text, **kw: forwarded.append(text))
        value.chat_input[0].set_value("什么是轴承？").run()
        assert forwarded == ["什么是轴承？"] and fake.call_count == 1
        edit = next(x for x in value.text_input if x.key and x.key.endswith("_label"))
        edit.set_value("协助审核公差，未独立负责维修").run()
        next(b for b in value.button if b.key and b.key.endswith("_edit")).click().run()
        assert not value.exception and s.draft.changes[0].user_resolution == Resolution.EDIT
        next(b for b in value.button if b.key and b.key.startswith("orange_profile_confirm_")).click().run()
        assert not value.exception and s.confirmed_profile.work_experience[0].label == "协助审核公差，未独立负责维修"
        assert fake.call_count == 1 and not w.memory_service.memory_store.list_active(w.subject_id)
        rendered = "\n".join(m.value for m in value.markdown)
        assert "已确认" in rendered and "最适合" not in rendered and "推荐你" not in rendered
    finally:
        w.close()


def test_workspace_refinement_memory_context_is_existing_policy_and_read_only(tmp_path, monkeypatch):
    with Workspace(str(uuid4()), tmp_path) as w:
        fake = prepared(w)
        before = snapshot(tmp_path)
        seen = []
        retrieve = w.memory_service.retrieve_hybrid
        def observed(*a, **kwargs):
            seen.append(kwargs)
            return retrieve(*a, **kwargs)
        monkeypatch.setattr(w.memory_service, "retrieve_hybrid", observed)
        assert w.profile_refinement.start(explicit_review=True)
        assert seen[0]["top_k"] == 8 and {t.value for t in seen[0]["memory_types"]} == {"goal", "career_preference", "user_feedback"}
        assert snapshot(tmp_path) == before and fake.call_count == 1


def test_candidate_values_use_plain_text_not_markdown_links():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "ui/profile_refinement.py").read_text()
    assert 'st.text("原理解："' in source and 'st.text("新候选："' in source and "st.text(detail)" in source
    assert 'st.write("新候选："' not in source


def test_refinement_authority_guard_is_read_only_not_nested_invalidation(tmp_path, monkeypatch):
    with Workspace(str(uuid4()), tmp_path) as w:
        prepared(w)
        w.resume_intake.result = None  # Simulate stale consent identity.
        with monkeypatch.context() as patch:
            patch.setattr(w.resume_analysis, "invalidate", lambda: (_ for _ in ()).throw(AssertionError("Guard must be read-only")))
            from profile_refinement.models import RefinementError
            with pytest.raises(RefinementError) as error:
                workspace_inputs(w)
            assert error.value.code == Status.STALE_DRAFT


def test_late_confirmation_cleanup_cannot_clear_new_clarification_version(tmp_path):
    with Workspace(str(uuid4()), tmp_path) as w:
        prepared(w)
        binding = binding_for_refinement(workspace_inputs(w))
        w.clarification.state.version += 1
        state = w.clarification.state
        w._profile_refinement_confirmed(binding)
        assert w.clarification.state is state


@pytest.mark.parametrize("background", ["audit", "mechanical", "switcher", "no_change"])
def test_fake_smoke(tmp_path, background):
    """Run explicitly AFTER focused suite; four local Fake flows, not an evaluator."""
    from tests.profile_refinement_doubles import Harness
    if background == "audit":
        h = Harness(tmp_path, profile=profile_for("继续审计"), plan=goal_plan)
        h.answer()
        assert h.start().changes[0].old_value.label == "继续审计"
        h.review(Resolution.UNCERTAIN)
        assert h.confirm().version == 2
        assert h.history()[-1].field_provenance["goals.goal_001"].uncertainty == "explicit_uncertainty"
    elif background == "mechanical":
        from data.models import ProfileSectionEntry, UserProfile
        base = UserProfile(profile_id="public_mechanical", work_experience=[ProfileSectionEntry(
            entry_id="work_001", label="维修责任范围尚不明确", confidence=0.7,
            source_type=EvidenceSourceType.EXPLICIT_USER_INPUT)]).confirm()
        def responsibility_plan(payload):
            from tests.profile_refinement_doubles import proposal
            old = next(s for s in payload["sources"] if s["origin"] == "confirmed_profile")
            answer = next(s for s in payload["sources"] if s["origin"] == "clarification_answer")
            resume = next(s for s in payload["sources"] if s["origin"] == "resume_evidence")
            return {"outcome": "CHANGES", "changes": [proposal(resume, target=old["target_id"],
                change_type="UPDATE", value={"label": "协助审核公差和维护计划"},
                refs=[old["ref"], answer["ref"], resume["ref"]])]}
        h = Harness(tmp_path, profile=base, background="mechanical", plan=responsibility_plan)
        h.answer("我只协助审核公差，不独立负责维护", topic="ownership")
        draft = h.start()
        c = draft.changes[0]
        edited = c.proposed_value.model_dump()
        edited.update(label="协助审核公差和维护计划")
        h.session.resolve(h.session.token(), c.change_id, Resolution.EDIT, edited_value=edited)
        final = h.confirm()
        assert final.work_experience[0].label == edited["label"]
        assert next(iter(final.field_provenance.values())).source_refs[0].origin == "explicit_user_edit"
    elif background == "switcher":
        h = Harness(tmp_path, profile=profile_for(), background="switcher")
        h.start(); h.review(); final = h.confirm()
        assert final.version == 2 and final.work_experience and not final.projects
    else:
        h = Harness(tmp_path)
        h.start(); h.review(); base = h.confirm()
        h.fake.plan = lambda _: {"outcome": "NO_MATERIAL_CHANGE", "changes": []}
        assert h.start().status == Status.NO_MATERIAL_CHANGE
        assert h.confirm() is None and h.history() == [base] and not h.memories()
    assert h.fake.call_count == (2 if background == "no_change" else 1)
