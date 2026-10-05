"""Public synthetic adaptive/session authority tests, Fake only, no private inputs."""

from dataclasses import asdict
import json
from threading import Event, Thread
from uuid import uuid4

import pytest

from career_runtime.profile_conversation import InterviewStage as Stage, MAX_ROUNDS, Readiness
from data.models import UserProfile
from profile_refinement.models import Status
from providers.fake import FakeLLMProvider
from tests.clarification_doubles import SelectingFake, profile_for
from tests.profile_refinement_doubles import DeltaFake, proposal
from tests.resume_evidence_doubles import docx_for, evidence_output
from tests.test_clarification_ui import snapshot
from ui.chat_runtime import Workspace


def faithful_plan(payload):
    changes = []
    sources = payload["sources"]
    for source in sources:
        if source["origin"] != "resume_evidence":
            continue
        old = next((s for s in sources if s["origin"] == "confirmed_profile" and
                    s["category"] == source["category"] and s["value"] == source["value"]), None)
        if old is None:
            changes.append(proposal(source))
    answer = next((s for s in sources if s["origin"] == "explicit_user_input"), None) or next(
        (s for s in sources if s["origin"] == "clarification_answer" and s["category"] == "career_direction"), None)
    if answer:
        category = "uncertainties" if answer["uncertainty"] else "career_preferences"
        changes.append(proposal(answer, category=category, value={"label": answer["text"][:160]}))
    return {"outcome": "CHANGES" if changes else "NO_MATERIAL_CHANGE", "changes": changes}


def prepare(w, background="audit", *, ambiguous=False, extractor_output=None):
    w.agent_session  # Same content-free settings initialization as the actual shell.
    intake = w.resume_intake
    intake.select(w.owner_scope_id, w.thread.thread_id, "public-synthetic.docx", docx_for(background))
    intake.parse_pending()
    document = intake.result.document
    output = extractor_output or evidence_output(document,
        category="education" if background == "student" else "work_experience")
    if ambiguous:
        output["items"][0].update(confidence="uncertain", uncertainty="unclear_ownership")
    extraction = FakeLLMProvider(output)
    w.resume_analysis.provider_factory = lambda: extraction
    assert w.resume_analysis.grant_current()
    w.resume_analysis.analyze()
    assert w.resume_analysis.bundle
    selector, refiner = SelectingFake(), DeltaFake(faithful_plan)
    w.clarification.provider_factory = lambda: selector
    w.profile_refinement.provider_factory = lambda: refiner
    return selector, refiner


def begin(w):
    return w.profile_conversation.start(consent=True, expected_consent=w.resume_analysis.consent)


@pytest.fixture(autouse=True)
def no_live(monkeypatch):
    monkeypatch.setattr("providers.models.load_llm_settings", lambda *a: pytest.fail("No credential reads"))
    monkeypatch.setattr("resume_evidence.session._qwen_provider", lambda: pytest.fail("No live provider"))


@pytest.mark.parametrize("background,answer", [
    ("audit", "我想探索数据分析和业务分析，但暂时不确定是否完全离开审计。"),
    ("student", "我还没想好，想先了解不同的工作。"),
    ("switcher", "我希望探索运营管理和业务改进。"),
    ("mechanical", "我还不确定。"),
])
def test_adaptive_public_backgrounds_stop_early_preserve_facts_and_confirm_only_explicitly(tmp_path, background, answer):
    with Workspace(str(uuid4()), tmp_path) as w:
        selector, refiner = prepare(w, background)
        before = snapshot(tmp_path)
        assert begin(w)
        s = w.profile_conversation
        assert s.stage == Stage.QUESTION and s.rounds == 1
        assert w.clarification.current_question()
        assert not begin(w) and selector.call_count == 1
        assert s.submit(answer)
        assert s.stage == Stage.REVIEW and s.readiness == Readiness.READY_FOR_PROFILE_REVIEW
        assert s.rounds < MAX_ROUNDS and selector.call_count == refiner.call_count == 1
        assert w.memory_service.get_current_confirmed_profile(w.subject_id) is None
        assert not w.memory_service.memory_store.list_active(w.subject_id)
        assert snapshot(tmp_path) == before and not w.chat.messages
        assert not w.store.list_messages(w.owner_scope_id, w.thread.thread_id)
        final = s.confirm(s.token(), w.profile_refinement.token())
        assert final and final.confirmed and not final.projects
        assert bool(final.work_experience) is (background != "student")
        assert bool(final.education) is (background == "student")
        if "不确定" in answer or "没想好" in answer:
            assert final.uncertainties and not final.development_areas
        assert not w.memory_service.memory_store.list_active(w.subject_id)
        assert len(w.memory_service.profile_store.list_profile_history(w.subject_id)) == 1
        assert s.stage == Stage.CONFIRMED and not w.clarification.state.answer_candidates
        assert selector.call_count == refiner.call_count == 1


def test_known_supported_direction_requires_zero_questions_and_one_automatic_proposal(tmp_path):
    with Workspace(str(uuid4()), tmp_path) as w:
        w.memory_service.save_confirmed_profile(w.subject_id, profile_for("继续审计"))
        selector, refiner = prepare(w)
        before = w.memory_service.get_current_confirmed_profile(w.subject_id)
        assert begin(w)
        assert w.profile_conversation.stage == Stage.REVIEW and w.profile_conversation.rounds == 0
        assert selector.call_count == 0 and refiner.call_count == 1
        assert w.memory_service.get_current_confirmed_profile(w.subject_id) == before


@pytest.mark.parametrize("answer", ["不确定", "我还没想好", "先跳过"])
def test_uncertain_and_skip_do_not_require_a_career_goal_or_invent_capabilities(tmp_path, answer):
    with Workspace(str(uuid4()), tmp_path) as w:
        selector, refiner = prepare(w)
        begin(w)
        assert w.profile_conversation.submit(answer)
        assert w.profile_conversation.stage == Stage.REVIEW
        assert not w.memory_service.get_current_confirmed_profile(w.subject_id)
        draft = w.profile_refinement.draft
        assert not any(c.category in {"skills", "development_areas", "goals"} for c in draft.changes)
        assert bool(w.clarification.state.answer_candidates) is (answer != "先跳过")
        assert w.profile_conversation.skipped is (answer == "先跳过")
        assert selector.call_count == refiner.call_count == 1


def test_bound_is_four_material_questions_not_four_required_questions(tmp_path):
    with Workspace(str(uuid4()), tmp_path) as w:
        # Distinct public evidence scopes with explicit ownership ambiguity.
        from dataclasses import replace
        from tests.test_resume_evidence_ui import public_document
        from resume_intake.models import ResumeParseResult, ResumeParseStatus
        document = public_document()
        blocks = tuple(replace(document.blocks[0], block_id=f"{document.source_id}:block:{i}",
            text=f"Synthetic role {i}\nSynthetic firm {i}\n2021 - 2024\nPrepared synthetic audit report {i}")
            for i in range(1, 7))
        document = replace(document, blocks=blocks)
        w.resume_intake.result = ResumeParseResult(ResumeParseStatus.READY, document=document)
        items = []
        for i, block in enumerate(blocks, 1):
            single = replace(document, blocks=(block,))
            item = evidence_output(single)["items"][0]
            item.update(evidence_id=f"resume_evidence_{i:03d}", role_title=None, organization=None, time_range=None,
                responsibilities=[block.text.splitlines()[-1]],
                confidence="uncertain", uncertainty="unclear_ownership")
            items.append(item)
        extraction = FakeLLMProvider({"items": items, "uncertainties": []})
        w.resume_analysis.provider_factory = lambda: extraction
        assert w.resume_analysis.grant_current()
        w.resume_analysis.analyze()
        selector, refiner = SelectingFake(), DeltaFake(faithful_plan)
        w.clarification.provider_factory = lambda: selector
        w.profile_refinement.provider_factory = lambda: refiner
        begin(w)
        for _ in range(MAX_ROUNDS):
            assert w.profile_conversation.stage == Stage.QUESTION
            assert w.profile_conversation.submit("我还不确定")
        s = w.profile_conversation
        assert s.stage == Stage.REVIEW and s.rounds == s.selection_attempts == MAX_ROUNDS
        assert s.bound_reached and selector.call_count == MAX_ROUNDS and refiner.call_count == 1
        assert not w.clarification.current_question()
        assert not any(c.category == "development_areas" for c in w.profile_refinement.draft.changes)


@pytest.mark.parametrize("operation", ["new_chat", "switch", "delete", "revoke", "replace", "close"])
def test_lifecycle_clears_ephemeral_interview_and_stale_actions_cannot_write(tmp_path, operation):
    with Workspace(str(uuid4()), tmp_path) as w:
        prepare(w)
        begin(w)
        token = w.profile_conversation.token()
        original = w.thread.thread_id
        if operation == "new_chat": w.create_new_thread()
        elif operation == "switch": w.activate(w.store.create_thread(w.owner_scope_id).thread_id)
        elif operation == "delete": w.delete_thread(original)
        elif operation == "revoke": w.resume_analysis.revoke()
        elif operation == "replace": w.resume_intake.select(w.owner_scope_id, original, "next.docx", docx_for("student"))
        else: w.close()
        assert w.profile_conversation.stage == Stage.IDLE and not w.profile_conversation.messages
        assert not w.profile_conversation.submit("late answer", token=token)
        assert w.profile_conversation.confirm(token, None) is None
        assert not w.memory_service.profile_store.list_profile_history(w.subject_id)


@pytest.mark.parametrize("phase", ["question", "review"])
def test_late_results_never_resurrect_deleted_thread_or_ephemeral_content(tmp_path, phase):
    with Workspace(str(uuid4()), tmp_path) as w:
        selector, refiner = prepare(w)
        entered, release = Event(), Event()
        provider = selector if phase == "question" else refiner
        original = provider.generate_structured
        def waiting(*args, **kwargs):
            entered.set()
            assert release.wait(4)
            return original(*args, **kwargs)
        provider.generate_structured = waiting
        if phase == "review": begin(w)
        worker = Thread(target=lambda: begin(w) if phase == "question" else w.profile_conversation.submit("不确定"))
        worker.start()
        assert entered.wait(4)
        old = w.thread.thread_id
        w.delete_thread(old)
        release.set()
        worker.join(4)
        assert not worker.is_alive() and old not in {t.thread_id for t in w.threads}
        assert not w.profile_conversation.messages and w.profile_conversation.stage == Stage.IDLE
        assert w.profile_refinement.draft is None and not w.memory_service.get_current_confirmed_profile(w.subject_id)


def test_consent_stale_owner_and_duplicate_actions_do_not_call_providers(tmp_path):
    with Workspace(str(uuid4()), tmp_path) as w:
        selector, refiner = prepare(w)
        assert not w.profile_conversation.start(expected_consent=w.resume_analysis.consent)
        assert not w.profile_conversation.start(consent=True, expected_consent=None)
        assert selector.call_count == refiner.call_count == 0
        assert begin(w)
        assert not begin(w) and selector.call_count == 1
        assert not w.agent_session.consent


def test_profile_conflict_preview_cannot_overwrite_until_explicit_confirmation(tmp_path):
    with Workspace(str(uuid4()), tmp_path) as w:
        base = profile_for("继续审计")
        w.memory_service.save_confirmed_profile(w.subject_id, base)
        selector, refiner = prepare(w, ambiguous=True)
        begin(w)
        w.profile_conversation.submit("主要负责")
        from tests.profile_refinement_doubles import goal_plan
        refiner.plan = goal_plan
        s = w.profile_conversation
        assert s.continue_talking(s.token(), edit=True)
        s.submit("我现在希望探索数据分析")
        assert s.stage == Stage.REVIEW
        change = w.profile_refinement.draft.changes[0]
        assert change.old_value.label == "继续审计" and change.conflict_state == "requires_review"
        assert w.memory_service.get_current_confirmed_profile(w.subject_id) == base
        assert not w.memory_service.memory_store.list_active(w.subject_id)
        final = s.confirm(s.token(), w.profile_refinement.token())
        assert final.version == 2 and final.goals[0].label == "正在探索数据分析"


def test_failure_codes_are_structural_events_only_and_do_not_retry(tmp_path):
    with Workspace(str(uuid4()), tmp_path) as w:
        selector, refiner = prepare(w)
        refiner.plan = lambda payload: {"outcome": "CHANGES", "changes": []}
        begin(w)
        w.profile_conversation.submit("我还不确定")
        s = w.profile_conversation
        assert s.stage == Stage.FAILED and w.profile_refinement.status == Status.INVALID_DRAFT
        assert any(e.error_category == "INVALID_DRAFT" for e in s.events)
        assert not any("INVALID_DRAFT" in m.text for m in s.messages)
        assert not w.memory_service.get_current_confirmed_profile(w.subject_id)
        events = json.dumps([asdict(e) for e in s.events])
        for prose in ("我还不确定", "Audit Associate", "source_quotes", "prompt", "completion"):
            assert prose not in events
        assert selector.call_count == refiner.call_count == 1


@pytest.mark.parametrize("text", ["什么是数据分析师？", "业务分析师主要做什么？", "如何准备面试？"])
def test_general_questions_are_not_answers_and_leave_question_recoverable(tmp_path, text):
    with Workspace(str(uuid4()), tmp_path) as w:
        selector, refiner = prepare(w)
        begin(w)
        question = w.clarification.current_question()
        assert w.profile_conversation.submit(text) is False
        assert w.clarification.current_question() == question and not w.clarification.state.answer_candidates
        assert selector.call_count == 1 and refiner.call_count == 0


def test_external_profile_change_blocks_stale_answer_persistence_and_confirmation(tmp_path):
    with Workspace(str(uuid4()), tmp_path) as w:
        prepare(w)
        begin(w)
        w.memory_service.save_confirmed_profile(w.subject_id, UserProfile(profile_id="public_new_current").confirm())
        assert w.profile_conversation.submit("my stale interview answer") is True
        assert not w.profile_conversation.messages[-1].text == "my stale interview answer"
        assert not w.chat.messages and not w.clarification.state.answer_candidates


def test_whole_confirmation_cannot_replay_after_edit_or_another_owner(tmp_path):
    with Workspace(str(uuid4()), tmp_path / "a") as a, Workspace(str(uuid4()), tmp_path / "b") as b:
        prepare(a); prepare(b)
        begin(a); begin(b)
        a.profile_conversation.submit("我还不确定")
        b.profile_conversation.submit("我还不确定")
        token, review = a.profile_conversation.token(), a.profile_refinement.token()
        assert b.profile_conversation.confirm(token, review) is None
        assert a.profile_conversation.continue_talking(token, edit=True)
        assert a.profile_conversation.confirm(token, review) is None
        a.profile_conversation.submit("我希望探索运营管理")
        assert a.profile_conversation.confirm(token, review) is None  # Old draft fingerprint.
        final = a.profile_conversation.confirm(token, a.profile_refinement.token())
        assert final and len(a.memory_service.profile_store.list_profile_history(a.subject_id)) == 1
        assert a.profile_conversation.confirm(token, a.profile_refinement.token()) is None
        assert len(a.memory_service.profile_store.list_profile_history(a.subject_id)) == 1
        assert not b.memory_service.get_current_confirmed_profile(b.subject_id)


def test_rejecting_every_proposed_field_does_not_create_an_empty_confirmed_profile(tmp_path):
    from profile_refinement.models import Resolution
    with Workspace(str(uuid4()), tmp_path) as w:
        prepare(w); begin(w)
        w.profile_conversation.submit("我还不确定")
        for change in w.profile_refinement.draft.changes:
            assert w.profile_refinement.resolve(w.profile_refinement.token(), change.change_id, Resolution.REJECT)
        assert w.profile_conversation.confirm(w.profile_conversation.token(), w.profile_refinement.token()) is None
        assert not w.memory_service.profile_store.list_profile_history(w.subject_id)
        assert not w.memory_service.memory_store.list_active(w.subject_id)
        assert w.profile_conversation.stage == Stage.CONFIRMED


def test_selector_validated_stop_is_one_evaluation_and_one_bounded_proposal(tmp_path):
    with Workspace(str(uuid4()), tmp_path) as w:
        _, refiner = prepare(w)
        selector = SelectingFake(ask=False)
        w.clarification.provider_factory = lambda: selector
        assert begin(w)
        assert w.profile_conversation.rounds == 0 and w.profile_conversation.stage == Stage.REVIEW
        assert selector.call_count == refiner.call_count == 1
        assert w.profile_conversation.selection_attempts == 1


def test_summary_and_interview_prose_never_enter_snapshot_or_durable_chat_before_confirmation(tmp_path):
    with Workspace(str(uuid4()), tmp_path) as w:
        prepare(w); begin(w)
        w.profile_conversation.submit("我还不确定是否离开审计，想先理解业务分析的真实工作。")
        assert w.profile_conversation.stage == Stage.REVIEW
        assert not w.store.list_messages(w.owner_scope_id, w.thread.thread_id)
        data = json.dumps(w.store.load_snapshot(w.owner_scope_id, w.thread.thread_id), ensure_ascii=False)
        assert "审计" not in data and "profile_interview" not in data
        for path in tmp_path.rglob("*"):
            if path.is_file():
                content = path.read_bytes()
                for prose in ("我还不确定是否离开审计", "Audit Associate", "我的职业画像"):
                    assert prose.encode() not in content
