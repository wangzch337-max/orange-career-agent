"""Focused native chat/lifecycle checks and three local Fake smoke flows."""

from threading import Event, Thread
from uuid import uuid4

import pytest

from clarification.context import workspace_inputs
from clarification.policy import ClarificationStatus as Status, ReasonCode as RC, TurnIntent
from providers.fake import FakeLLMProvider
from tests.clarification_doubles import SelectingFake, profile_for
from tests.resume_evidence_doubles import docx_for, evidence_output
from tests.test_chat_product import app, WORKSPACE_KEY
from ui.chat_runtime import Workspace


def ready(workspace, background="audit", *, ambiguous=False):
    intake = workspace.resume_intake
    intake.select(workspace.owner_scope_id, workspace.thread.thread_id, "public-synthetic.docx", docx_for(background))
    intake.parse_pending()
    document = intake.result.document
    output = evidence_output(document)
    if ambiguous:
        output["items"][0].update(confidence="uncertain", uncertainty="unclear_ownership")
    extraction = FakeLLMProvider(output)
    workspace.resume_analysis.provider_factory = lambda: extraction
    assert workspace.resume_analysis.grant_current()
    workspace.resume_analysis.analyze()
    assert workspace.resume_analysis.bundle is not None and extraction.call_count == 1
    fake = SelectingFake()
    workspace.clarification.provider_factory = lambda: fake
    return fake


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("operation", ["replace", "new_chat", "select_other", "delete", "close", "revoke"])
def test_workspace_lifecycle_clears_open_answers_and_dedup_not_canonical(tmp_path, operation):
    workspace = Workspace(str(uuid4()), tmp_path)
    try:
        current = profile_for("财务方向")
        workspace.memory_service.save_confirmed_profile(workspace.subject_id, current)
        # Need goal ambiguity even though canonical Profile remains available.
        fake = ready(workspace, "mechanical", ambiguous=True)
        session = workspace.clarification
        assert session.run(TurnIntent.RESUME_REVIEW).should_ask
        question = session.current_question()
        old_thread = workspace.thread.thread_id
        if operation == "replace":
            workspace.resume_intake.select(workspace.owner_scope_id, old_thread, "replacement.docx", docx_for("student"))
        elif operation == "new_chat":
            workspace.create_new_thread()
        elif operation == "select_other":
            other = workspace.store.create_thread(workspace.owner_scope_id)
            workspace.activate(other.thread_id)
        elif operation == "delete":
            workspace.delete_thread(old_thread)
        elif operation == "close":
            workspace.close()
        else:
            workspace.resume_analysis.revoke()
        assert session.state.current_open_need is None and not session.state.asked_need_ids
        assert session.answer(question, "late synthetic answer") is None
        assert not session.state.answer_candidates and fake.call_count == 1
        if not workspace._closed:
            assert workspace.memory_service.get_current_confirmed_profile(workspace.subject_id).model_dump_json() == current.model_dump_json()
    finally:
        workspace.close()


def test_new_chat_clears_answer_candidates_not_only_open_question(tmp_path):
    with Workspace(str(uuid4()), tmp_path) as workspace:
        fake = ready(workspace)
        workspace.clarification.run(TurnIntent.RESUME_REVIEW)
        q = workspace.clarification.current_question()
        assert workspace.clarification.answer(q, "我不确定")
        assert workspace.clarification.state.answer_candidates
        workspace.create_new_thread()
        assert not workspace.clarification.state.answer_candidates and not workspace.clarification.state.answered_need_ids
        assert fake.call_count == 1


def test_actual_workspace_late_result_cannot_resurrect_deleted_conversation(tmp_path):
    with Workspace(str(uuid4()), tmp_path) as workspace:
        entered, release = Event(), Event()
        ready(workspace)
        class LateFake(SelectingFake):
            def generate_structured(self, *args, **kwargs):
                entered.set()
                assert release.wait(3)
                return super().generate_structured(*args, **kwargs)
        fake = LateFake()
        workspace.clarification.provider_factory = lambda: fake
        thread = workspace.thread.thread_id
        worker = Thread(target=lambda: workspace.clarification.run(TurnIntent.RESUME_REVIEW))
        worker.start()
        assert entered.wait(3)
        workspace.delete_thread(thread)
        state = workspace.clarification.state
        release.set()
        worker.join(3)
        assert not worker.is_alive() and workspace.clarification.state is state
        assert workspace.clarification.current_question() is None and not state.answer_candidates
        assert thread not in {t.thread_id for t in workspace.threads}


def test_existing_memory_policy_read_only_relevant_subset_and_canonical_current_getter(tmp_path, monkeypatch):
    with Workspace(str(uuid4()), tmp_path) as workspace:
        ready(workspace)
        current = profile_for("审计")
        workspace.memory_service.save_confirmed_profile(workspace.subject_id, current)
        service = workspace.memory_service
        calls = []
        original = service.retrieve_hybrid
        def recorded(subject_id, query, **kwargs):
            calls.append((subject_id, query, kwargs))
            return original(subject_id, query, **kwargs)
        monkeypatch.setattr(service, "retrieve_hybrid", recorded)
        def forbidden(*args, **kwargs):
            raise AssertionError("C.3 has no authority write/history loader")
        for name in ("save_confirmed_profile", "create_candidate", "create_confirmed", "confirm_candidate", "supersede", "archive", "purge_subject"):
            monkeypatch.setattr(service, name, forbidden)
        before = snapshot(tmp_path)
        inputs = workspace_inputs(workspace, current_statement="我现在希望继续审计")
        assert inputs.profile.version == 1 and inputs.profile.confirmed
        assert calls[0][2]["top_k"] == 8
        assert {x.value for x in calls[0][2]["memory_types"]} == {"career_preference", "goal", "user_feedback"}
        workspace.clarification.run(TurnIntent.RESUME_REVIEW)
        assert snapshot(tmp_path) == before


def test_native_ui_explicit_action_freeform_optional_route_general_qa_unchanged(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No live provider during C.3")
    monkeypatch.setattr("resume_evidence.session._qwen_provider", forbidden)
    value = app(tmp_path, str(uuid4()))
    workspace = value.session_state[WORKSPACE_KEY]
    try:
        fake = ready(workspace)
        from tests.profile_refinement_doubles import DeltaFake
        refiner = DeltaFake()
        workspace.profile_refinement.provider_factory = lambda: refiner
        value.run()
        assert not value.exception and fake.call_count == 0
        before = snapshot(tmp_path)
        value.button(key="orange_clarification_start").click().run()
        assert not value.exception and fake.call_count == 1
        question = workspace.clarification.current_question()
        assert question is not None and value.chat_input
        assert not [x for x in value.checkbox if x.key and x.key.startswith("orange_clarification_answer_")]
        # Unrelated QA is not consumed as an answer or cause a clarification call.
        forwarded = []
        monkeypatch.setattr(workspace, "submit", lambda text, **kwargs: forwarded.append(text))
        value.chat_input[0].set_value("Python generator 和 iterator 有什么区别？").run()
        assert forwarded == ["Python generator 和 iterator 有什么区别？"]
        assert workspace.clarification.current_question() == question and fake.call_count == 1
        value.chat_input[0].set_value("我还没想好，两个方向都在考虑。").run()
        assert not value.exception and workspace.clarification.status == Status.ANSWER_RECORDED
        assert workspace.clarification.state.answer_candidates[0].uncertainty == "explicit_uncertainty"
        assert fake.call_count == refiner.call_count == 1 and snapshot(tmp_path) == before
        assert workspace.profile_refinement.draft is not None
        assert not workspace.store.list_messages(workspace.owner_scope_id, workspace.thread.thread_id)
        value.run()
        assert fake.call_count == 1  # No automatic second question/model call.
    finally:
        workspace.close()


def test_native_ui_optional_reply_and_dismiss_no_replay_on_theme(tmp_path):
    value = app(tmp_path, str(uuid4()))
    workspace = value.session_state[WORKSPACE_KEY]
    try:
        fake = ready(workspace)
        from tests.profile_refinement_doubles import DeltaFake
        workspace.profile_refinement.provider_factory = lambda: DeltaFake()
        value.run()
        value.button(key="orange_clarification_start").click().run()
        q = workspace.clarification.current_question()
        value.radio(key="orange_appearance").set_value("深色模式").run()
        assert fake.call_count == 1 and workspace.clarification.current_question() == q
        value.button(key=f"orange_profile_reply_{workspace.profile_conversation.generation}_1").click().run()
        assert not value.exception and fake.call_count == 1
        assert workspace.clarification.current_question() is None
    finally:
        workspace.close()


@pytest.mark.parametrize("case", ["audit", "mechanical", "enough_information"])
def test_fake_local_smoke_candidate_only_no_durable_writes(tmp_path, case):
    """Run separately after focused gates: ready → context → need → zero/one → answer."""
    with Workspace(str(uuid4()), tmp_path) as workspace:
        if case in {"mechanical", "enough_information"}:
            workspace.memory_service.save_confirmed_profile(workspace.subject_id, profile_for("财务审计"))
        fake = ready(workspace, "mechanical" if case == "mechanical" else "audit", ambiguous=case == "mechanical")
        before = snapshot(tmp_path)
        profile_before = workspace.memory_service.get_current_confirmed_profile(workspace.subject_id)
        decision = workspace.clarification.run(TurnIntent.RESUME_REVIEW)
        if case == "enough_information":
            assert not decision.should_ask and fake.call_count == 0
        else:
            q = workspace.clarification.current_question()
            expected = RC.AMBIGUOUS_RESPONSIBILITY if case == "mechanical" else RC.MISSING_GOAL
            assert q.need.reason_code == expected and decision.should_ask and fake.call_count == 1
            answer = "主要负责现场配合，不独立负责方案设计。" if case == "mechanical" else "我还没想好。"
            candidate = workspace.clarification.answer(q, answer)
            assert candidate.status == "candidate" and candidate.source == "explicit_user_input"
            assert len(workspace.clarification.state.answer_candidates) == 1
        assert workspace.memory_service.get_current_confirmed_profile(workspace.subject_id) == profile_before
        assert snapshot(tmp_path) == before  # No Profile/version/Memory/transcript writes.
