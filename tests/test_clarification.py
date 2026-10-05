"""Focused authority, deduplication, provider and lifecycle tests; all synthetic."""

from dataclasses import asdict, replace
import json
import logging
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from clarification.context import ClarificationContextBuilder, binding_for, workspace_inputs
from clarification.models import ClarificationDecision
from clarification.needs import generate_needs, highest_value_needs
from clarification.policy import ClarificationStatus as Status, ReasonCode as RC, TurnIntent, MAX_CONTEXT_CHARS
from clarification.service import ClarificationSelector, ClarificationError, no_question, validate_decision
from clarification.session import ClarificationSession
from data.models import EvidenceSourceType, InferenceType, GoalType
from memory.models import MemoryContext, MemoryContextItem, MemoryType, MemoryStatus
from tests.clarification_doubles import SelectingFake, InputSource, bundle_for, inputs_for, profile_for


def context_for(inputs, **kwargs):
    ctx = ClarificationContextBuilder().build(inputs)
    return ctx.model_copy(update={"needs": generate_needs(ctx, **kwargs)})


def session_for(inputs=None, fake=None):
    source = InputSource(inputs or inputs_for())
    fake = fake or SelectingFake()
    session = ClarificationSession(source.value.owner_scope_id, source, provider_factory=lambda: fake)
    return session, source, fake


def ask(session):
    decision = session.run(TurnIntent.RESUME_REVIEW)
    assert decision.should_ask and session.status == Status.QUESTION_OPEN
    return session.current_question()


def memory_context(*, status=MemoryStatus.CONFIRMED, content="我希望继续运营", kind=MemoryType.GOAL, count=1):
    items = [MemoryContextItem(memory_id=f"memory_{i}", memory_type=kind, status=status, content=content,
        source_type="explicit_user_input", authority="active_confirmed", fusion_rank=i+1) for i in range(count)]
    return MemoryContext(subject_id="synthetic_subject", items=items, max_records=8,
                         character_count=sum(len(i.content) for i in items))


def test_zero_question_valid_and_no_candidates_skip_provider_entirely():
    assert not no_question().should_ask
    session, _, fake = session_for(inputs_for(goal="财务审计"))
    assert not session.run(TurnIntent.RESUME_REVIEW).should_ask
    assert session.status == Status.NO_CLARIFICATION_NEEDED and fake.call_count == 0


def test_provider_can_decide_zero_with_valid_need_and_no_forced_followup():
    session, _, fake = session_for(fake=SelectingFake(ask=False))
    assert not session.run(TurnIntent.RESUME_REVIEW).should_ask
    assert session.current_question() is None and fake.call_count == 1
    session.run(TurnIntent.RESUME_REVIEW)
    assert fake.call_count == 1


@pytest.mark.parametrize("change", [
    {"question": "问题一？问题二？"}, {"question": "你最适合 Data Analyst？"},
    {"question": "x" * 361}, {"suggested_replies": ["x"]*5},
    {"suggested_replies": ["推荐转产品经理"]}, {"questions": ["a", "b"]},
    {"selected_need_id": "need_" + "f"*20}, {"source_refs": ["rs_999"]},
    {"reason_summary": "hidden chain of thought"}, {"should_ask": "yes"},
])
def test_malformed_or_unsupported_plan_safe_failure_no_retry(change):
    fake = SelectingFake(transform=lambda output: {**output, **change})
    session, _, _ = session_for(fake=fake)
    assert not session.run(TurnIntent.RESUME_REVIEW).should_ask
    assert session.status in {Status.INVALID_CLARIFICATION_PLAN, Status.INVALID_REFERENCE}
    assert session.current_question() is None
    session.run(TurnIntent.RESUME_REVIEW)
    assert fake.call_count == 1 and not session.state.answer_candidates


@pytest.mark.parametrize("data", [
    {"should_ask": False, "question": "仍有问题？"},
    {"should_ask": True, "question": None},
    {"should_ask": False, "suggested_replies": ["x"]},
    {"should_ask": False, "source_refs": ["rs_001"]},
])
def test_strict_zero_one_consistency(data):
    with pytest.raises(ValidationError):
        ClarificationDecision.model_validate({**no_question().model_dump(), **data})


@pytest.mark.parametrize("background,label", [
    ("student", "Hospitality"), ("audit", "Audit Associate"), ("mechanical", "Mechanical Engineer"),
    ("marketing", "E-commerce Specialist"), ("design", "UX Designer"), ("switcher", "Operations Supervisor"),
])
def test_background_adaptive_missing_goal_not_ai_student_or_project_checklist(background, label):
    session, _, fake = session_for(inputs_for(background))
    question = ask(session)
    assert question.need.reason_code == RC.MISSING_GOAL and label in question.decision.question
    assert "编程" not in question.decision.question and "项目" not in question.decision.question
    assert "推荐" not in question.decision.question and "AI Engineer" not in question.decision.question
    assert session._inputs().resume.category_counts()["projects"] == 0
    assert fake.call_count == 1


def test_current_explicit_statement_not_ignored_by_stale_profile_or_memory():
    inputs = replace(inputs_for("switcher", goal="继续运营", current="我现在更想转做数据分析。"), memory=memory_context())
    context = context_for(inputs)
    assert context.needs[0].reason_code == RC.PROFILE_RESUME_CONFLICT
    refs = context.needs[0].source_refs
    assert [s.authority for s in context.sources if s.ref in refs] == ["explicit_user_input", "confirmed_profile"]
    assert not any(n.reason_code == RC.MISSING_GOAL for n in context.needs)
    session, _, _ = session_for(inputs)
    before = inputs.profile.model_dump_json()
    question = ask(session)
    assert "数据分析" in question.decision.question and "运营" in question.decision.question
    assert inputs.profile.model_dump_json() == before
    assert all(kind in {"current", "profile"} for _, kind, _ in question.resolved_sources)


@pytest.mark.parametrize("current,reason", [
    ("我想转行，但方向还没定", RC.AMBIGUOUS_TRANSITION_INTENT),
    ("我不确定自己的工作偏好", RC.CURRENT_PREFERENCE_UNKNOWN),
])
def test_explicit_transition_or_preference_unknown_not_fixed_questionnaire(current, reason):
    context = context_for(inputs_for(current=current))
    assert context.needs[0].reason_code == reason


def test_just_stated_uncertainty_not_forced_to_answer_missing_goal_again():
    assert not context_for(inputs_for(current="我还没想好。两个方向都在考虑。")).needs


def test_current_statement_precedes_prior_candidate_answer():
    session, source, _ = session_for(inputs_for(goal="运营"))
    # Create a supported current-change question then answer with another intent.
    session.run(TurnIntent.RESUME_REVIEW, current_statement="我现在想转产品")
    q = session.current_question()
    candidate = session.answer(q, "我想转财务审计")
    inputs = replace(source.value, current_statement="我现在想转数据分析")
    context = ClarificationContextBuilder().build(inputs, answers=(candidate,))
    needs = generate_needs(context)
    selected = needs[0]
    assert selected.reason_code == RC.PROFILE_RESUME_CONFLICT
    assert "数据分析" in selected.allowed_questions[0] and "财务审计" not in selected.allowed_questions[0]


def test_explicitly_tagged_model_source_never_masquerades_as_user_fact():
    inputs = inputs_for(goal="审计")
    profile = inputs.profile.model_copy(deep=True)
    profile.goals[0].source_type = EvidenceSourceType.MODEL_INFERENCE
    context = context_for(replace(inputs, profile=profile))
    assert not any(s.kind == "profile" for s in context.sources)
    assert context.needs[0].reason_code == RC.MISSING_GOAL


def test_multiple_confirmed_directions_and_project_goals_do_not_create_false_conflict():
    from data.models import Goal
    profile = profile_for("审计").model_copy(deep=True)
    profile.goals.append(Goal(goal_id="goal_002", label="数据分析", goal_type=GoalType.CAREER_GOAL, confirmed_by_user=True))
    ctx = context_for(replace(inputs_for(current="我现在想做数据分析"), profile=profile))
    assert not ctx.needs
    profile.goals = [Goal(goal_id="goal_003", label="完成课程作业", goal_type=GoalType.PROJECT_GOAL, confirmed_by_user=True)]
    ctx = context_for(replace(inputs_for(), profile=profile))
    assert ctx.needs[0].reason_code == RC.MISSING_GOAL
    assert next(s for s in ctx.sources if s.kind == "profile").category == "goal:project_goal"


def test_confirmed_skill_depth_already_known_not_asked_again():
    from data.models import CandidateSkill
    inputs = inputs_for(goal="财务方向", category="skills", ambiguity="unclear_proficiency", current="我想了解 Audit Associate 的工作深度")
    profile = inputs.profile.model_copy(deep=True)
    profile.skills = [CandidateSkill(skill_id="skill_001", label="Audit Associate", level="independent",
        confidence=1, source_type=EvidenceSourceType.EXPLICIT_USER_INPUT, confirmed_by_user=True)]
    ctx = context_for(replace(inputs, profile=profile))
    assert not any(n.reason_code == RC.UNCLEAR_SKILL_DEPTH for n in ctx.needs)


def test_profile_resume_explicit_intent_conflict_is_possible_change_not_truth():
    inputs = inputs_for(goal="继续运营")
    item = inputs.resume.items[0].model_dump()
    item.update(category="other_evidence", normalized_claim="Career goal: Product Management", claim_type="explicit_career_statement")
    for field in ("role_title", "organization", "time_range", "responsibilities", "achievements", "domain_signals", "tools", "business_metrics"):
        item.pop(field)
    resume = type(inputs.resume).model_validate({**inputs.resume.model_dump(), "items": [item]})
    context = context_for(replace(inputs, resume=resume))
    need = context.needs[0]
    assert need.reason_code == RC.PROFILE_RESUME_CONFLICT and need.uncertainty == "possible_change"
    source = next(s for s in context.sources if s.kind == "resume")
    assert source.authority == "resume_provided"  # Not independently confirmed.


def test_work_title_and_major_are_not_current_preference_or_goal():
    for background in ("student", "switcher", "audit"):
        context = context_for(inputs_for(background))
        assert any(n.reason_code == RC.MISSING_GOAL for n in context.needs)
        assert not any(s.explicit_goal for s in context.sources)


@pytest.mark.parametrize("background,category,ambiguity,reason", [
    ("mechanical", "work_experience", "unclear_ownership", RC.AMBIGUOUS_RESPONSIBILITY),
    ("marketing", "achievements", "unclear_ownership", RC.UNCLEAR_ACHIEVEMENT_OWNERSHIP),
    ("design", "research", "unclear_ownership", RC.AMBIGUOUS_RESPONSIBILITY),
    ("switcher", "work_experience", "overlapping_roles", RC.INSUFFICIENT_ROLE_CONTEXT),
    ("audit", "work_experience", "unclear_dates", RC.OUTDATED_INFORMATION),
])
def test_supported_ambiguities_get_focused_background_need(background, category, ambiguity, reason):
    context = context_for(inputs_for(background, goal="明确的当前方向", category=category, ambiguity=ambiguity))
    assert context.needs[0].reason_code == reason
    decision, _ = ClarificationSelector().select(SelectingFake(), context)
    assert decision.should_ask and decision.question.count("？") == 1


def test_skills_not_asked_merely_because_listed_only_material_ambiguity():
    inputs = inputs_for(goal="财务方向", category="skills", ambiguity="unclear_proficiency")
    assert not context_for(inputs).needs
    current = "我想了解 Audit Associate 的实际工作深度"
    assert context_for(replace(inputs, current_statement=current)).needs[0].reason_code == RC.UNCLEAR_SKILL_DEPTH
    plain = inputs_for(category="skills")
    assert all(n.reason_code != RC.UNCLEAR_SKILL_DEPTH for n in context_for(plain).needs)


def test_highest_value_conflict_then_missing_goal_then_ownership_no_scores():
    conflict = context_for(inputs_for(goal="运营", current="我现在想转产品", ambiguity="unclear_ownership"))
    assert all(n.priority == "conflict" for n in highest_value_needs(conflict.needs))
    unknown = context_for(inputs_for(ambiguity="unclear_ownership"))
    assert [n.priority for n in highest_value_needs(unknown.needs)] == ["direction"]
    assert "score" not in unknown.model_dump_json()


@pytest.mark.parametrize("intent", [TurnIntent.GENERAL_QA, TurnIntent.UNRELATED, TurnIntent.ANSWER])
def test_general_qa_unrelated_never_build_context_or_call_provider(intent):
    session, source, fake = session_for()
    assert not session.run(intent, current_statement="Python generator 和 iterator 有什么区别？").should_ask
    assert source.calls == 0 and fake.call_count == 0


@pytest.mark.parametrize("answer", ["我还没想好。", "我不确定。", "两个方向都在考虑。", "I don't know", "not sure"])
def test_uncertainty_is_valid_answer_no_repeat_same_turn_or_next_turn(answer):
    session, _, fake = session_for()
    question = ask(session)
    candidate = session.answer(question, answer)
    assert candidate.uncertainty == "explicit_uncertainty" and candidate.status == "candidate"
    assert session.status == Status.ANSWER_RECORDED and question.need.need_id in session.state.answered_need_ids
    assert fake.call_count == 1 and session.current_question() is None
    assert not session.run(TurnIntent.RESUME_REVIEW).should_ask and fake.call_count == 1


def test_freeform_answer_candidate_only_binds_question_refs_no_next_question():
    session, source, fake = session_for()
    before = source.value.profile.model_dump_json()
    question = ask(session)
    candidate = session.answer(question, "我希望继续财务审计，也想了解业务分析的可能性。")
    assert candidate.user_answer.startswith("我希望") and candidate.source == "explicit_user_input"
    assert candidate.binding == question.binding and candidate.resolved_sources == question.resolved_sources
    assert source.value.profile.model_dump_json() == before and source.value.profile.version == 1
    assert fake.call_count == 1


def test_one_open_question_and_duplicate_submission_never_repeated():
    session, _, fake = session_for()
    question = ask(session)
    for _ in range(3):
        assert not session.run(TurnIntent.RESUME_REVIEW).should_ask
    assert fake.call_count == 1 and session.current_question() == question
    assert session.answer(question, "已回答") is not None
    assert session.answer(question, "重复提交") is None and len(session.state.answer_candidates) == 1


def test_dismissed_need_not_asked_again():
    session, _, fake = session_for()
    question = ask(session)
    assert session.dismiss(question)
    assert question.need.need_id in session.state.dismissed_need_ids
    assert not session.run(TurnIntent.RESUME_REVIEW).should_ask and fake.call_count == 1


def test_semantic_identity_not_wording_and_same_scope_dedup():
    context = context_for(inputs_for(ambiguity="unclear_ownership", goal="审计"))
    first = context.needs[0]
    # Changed evidence wording, same source/category, same semantic need identity.
    source = context.sources[-1].model_copy(update={"text": "不同表达方式的同一经历"})
    changed = context.model_copy(update={"sources": (*context.sources[:-1], source), "needs": ()})
    assert generate_needs(changed)[0].need_id == first.need_id
    duplicate = source.model_copy(update={"ref": "rs_002"})
    assert len(generate_needs(changed.model_copy(update={"sources": (*changed.sources, duplicate)}))) == 1
    assert not generate_needs(changed, closed_need_ids={first.need_id})


def test_new_supported_conflict_can_reopen_but_same_conflict_cannot():
    session, source, fake = session_for(inputs_for(goal="运营", current="我现在想转产品"))
    q = ask(session)
    session.answer(q, "我还不确定")
    assert not session.run(TurnIntent.RESUME_REVIEW).should_ask and fake.call_count == 1
    source.value = replace(source.value, current_statement="我现在想转财务审计")
    assert session.run(TurnIntent.RESUME_REVIEW, current_statement="我现在想转财务审计").should_ask
    newer = session.current_question()
    assert newer.need.need_id != q.need.need_id and fake.call_count == 2


@pytest.mark.parametrize("change", ["resume", "profile", "conversation", "owner", "resume_evidence"])
def test_stale_question_rejected_on_bound_source_change(change):
    session, source, fake = session_for()
    q = ask(session)
    if change == "resume":
        source.value = replace(source.value, resume=bundle_for())
    elif change == "resume_evidence":
        source.value = replace(source.value, resume=source.value.resume.model_copy(update={"context_partial": True}))
    elif change == "profile":
        source.value = replace(source.value, profile=source.value.profile.create_revision(education_summary="synthetic").confirm())
    elif change == "conversation":
        source.value = replace(source.value, conversation_id="other_thread")
    else:
        source.value = replace(source.value, owner_scope_id="other_owner")
    assert session.answer(q, "不能应用旧问题") is None
    assert not session.state.answer_candidates and fake.call_count == 1


def test_old_ui_selection_binding_cannot_authorize_new_evidence():
    session, source, fake = session_for()
    expected = binding_for(source.value, session.state.version)
    source.value = replace(source.value, resume=bundle_for())
    assert not session.run(TurnIntent.RESUME_REVIEW, expected_binding=expected).should_ask
    assert fake.call_count == 0 and session.status == Status.STALE_CLARIFICATION_STATE


def test_late_provider_cannot_resurrect_invalidated_state():
    entered, release = Event(), Event()
    class Delayed(SelectingFake):
        def generate_structured(self, *args, **kwargs):
            entered.set()
            assert release.wait(3)
            return super().generate_structured(*args, **kwargs)
    session, _, fake = session_for(fake=Delayed())
    worker = Thread(target=lambda: session.run(TurnIntent.RESUME_REVIEW))
    worker.start()
    assert entered.wait(3)
    session.invalidate()
    state = session.state
    release.set()
    worker.join(3)
    assert not worker.is_alive() and session.state is state
    assert session.current_question() is None and not session.state.asked_need_ids
    assert session.usage is None and session.last_decision is None and fake.call_count == 1


def test_owner_conversation_isolation_even_with_same_source_factory():
    a, _, _ = session_for()
    b, _, bf = session_for()
    qa = ask(a)
    assert b.answer(qa, "跨客户端") is None
    assert b.current_question() is None and not b.state.answer_candidates and bf.call_count == 0
    wrong = ClarificationSession("different_owner", a.input_factory, provider_factory=lambda: bf)
    assert not wrong.run(TurnIntent.RESUME_REVIEW).should_ask and bf.call_count == 0


@pytest.mark.parametrize("which", ["draft", "superseded", "inference"])
def test_noncanonical_profile_or_inference_never_promoted(which):
    inputs = inputs_for(goal="审计")
    if which == "draft":
        inputs = replace(inputs, profile=inputs.profile.create_revision(education_summary="draft"))
        with pytest.raises(ValueError):
            context_for(inputs)
    elif which == "superseded":
        # Builder receives only the current canonical getter, not history/drafts.
        inputs = replace(inputs, profile=None)
        assert any(n.reason_code == RC.MISSING_GOAL for n in context_for(inputs).needs)
    else:
        profile = inputs.profile.model_copy(deep=True)
        profile.goals[0].inference_type = InferenceType.EVIDENCE_SUPPORTED_INFERENCE
        context = context_for(replace(inputs, profile=profile))
        assert not any(s.kind == "profile" for s in context.sources)
        assert any(n.reason_code == RC.MISSING_GOAL for n in context.needs)


@pytest.mark.parametrize("status", [MemoryStatus.CANDIDATE, MemoryStatus.SUPERSEDED, MemoryStatus.ARCHIVED])
def test_unconfirmed_historical_memory_is_not_authority(status):
    ctx = context_for(replace(inputs_for(), memory=memory_context(status=status)))
    assert not any(s.kind == "memory" for s in ctx.sources)


def test_memory_relevant_allowlist_bounds_and_historical_not_current():
    ctx = context_for(replace(inputs_for(), memory=memory_context(count=8, content="x"*600)))
    historical = [s for s in ctx.sources if s.kind == "memory"]
    assert len(historical) <= 6 and all(s.authority == "confirmed_historical_memory" for s in historical)
    assert any(n.reason_code == RC.MISSING_GOAL for n in ctx.needs)
    excluded = context_for(replace(inputs_for(), memory=memory_context(kind=MemoryType.COURSE_EVIDENCE)))
    assert not any(s.kind == "memory" for s in excluded.sources)
    with pytest.raises(ValueError):
        context_for(replace(inputs_for(), memory=memory_context().model_copy(update={"subject_id": "other_subject"})))


def test_bounded_recent_context_no_full_db_and_no_assistant_fact_promotion():
    from ui.conversation_store import ConversationMessage
    from datetime import datetime, timezone
    messages = tuple(ConversationMessage(message_id=str(uuid4()), thread_id="synthetic_thread", role="user" if i%2 else "assistant",
        content="bounded public synthetic context "*400, metadata={}, created_at=datetime.now(timezone.utc)) for i in range(30))
    ctx = context_for(replace(inputs_for(), recent=messages))
    recent = [s for s in ctx.sources if s.kind == "conversation"]
    assert len(recent) <= 6 and sum(len(s.text) for s in recent) <= 4500
    assert len(ctx.model_dump_json()) <= MAX_CONTEXT_CHARS and len(ctx.sources) <= 36
    assert all(not s.explicit_goal and s.authority == "conversation_context" for s in recent)


def test_maximum_context_bounded_and_no_raw_file_or_profile_dump():
    inputs = inputs_for()
    items = [inputs.resume.items[0].model_copy(update={"evidence_id": f"resume_evidence_{i+1:03d}", "normalized_claim": "x"*400}) for i in range(40)]
    ctx = context_for(replace(inputs, resume=inputs.resume.model_copy(update={"items": tuple(items)}),
        current_statement="candidate name: Synthetic Person\nemail: sample@example.invalid\n我现在想转财务审计"))
    assert ctx.partial and len(ctx.model_dump_json()) < MAX_CONTEXT_CHARS
    fake = SelectingFake(ask=False)
    # Clear goal may leave no candidates; direct serialization still demonstrates minimization.
    serialized = ctx.model_dump_json()
    assert "example.invalid" not in serialized and "Synthetic Person" not in serialized
    assert "content_fingerprint" not in serialized and "source_quotes" not in serialized
    assert "origin_refs" not in serialized


def test_request_scoped_schema_existing_provider_no_thinking_retry_or_repair():
    session, _, fake = session_for()
    ask(session)
    options = fake.options[0]
    assert options.model == "qwen3.8-flash" and options.max_retries == 0 and not options.thinking_enabled
    schema = json.dumps(fake.schemas[0])
    assert session.state.current_open_need.need.need_id in schema
    assert "additionalProperties" in schema and fake.call_count == 1
    assert "origin_refs" not in json.dumps(fake.payloads)


def test_semantic_selector_can_choose_another_supported_high_value_need_not_lower_priority():
    context = context_for(inputs_for(goal="审计", ambiguity="unclear_ownership"))
    first = next(s for s in context.sources if s.kind == "resume")
    second = first.model_copy(update={"ref": "rs_002", "semantic_scope": "a"*20,
                                     "text": "另一项受支持的工作职责"})
    context = context.model_copy(update={"sources": (*context.sources, second)})
    context = context.model_copy(update={"needs": generate_needs(context)})
    eligible = highest_value_needs(context.needs)
    assert len(eligible) == 2
    selected = eligible[1]
    fake = SelectingFake(transform=lambda out: {**out, "selected_need_id": selected.need_id,
        "question": selected.allowed_questions[0], "source_refs": list(selected.source_refs)})
    decision, _ = ClarificationSelector().select(fake, context)
    assert decision.selected_need_id == selected.need_id and fake.call_count == 1


@pytest.mark.parametrize("wrong", ["known_unrelated", "duplicate_ref"])
def test_even_known_ref_must_belong_to_selected_need(wrong):
    context = context_for(inputs_for(goal="审计", ambiguity="unclear_ownership"))
    need = highest_value_needs(context.needs)[0]
    data = {"should_ask": True, "selected_need_id": need.need_id, "question": need.allowed_questions[0],
        "suggested_replies": [], "reason_summary": "highest_value_supported_need", "confidence": "grounded",
        "source_refs": ["pf_001"] if wrong == "known_unrelated" else [need.source_refs[0]]*2}
    with pytest.raises(ClarificationError, match="INVALID_CLARIFICATION_PLAN"):
        validate_decision(ClarificationDecision.model_validate(data), context)


def test_existing_qwen_adapter_with_synthetic_sdk_stub_strict_scoped_schema_no_network():
    from pydantic import SecretStr
    from providers.qwen import QwenProvider
    context = context_for(inputs_for())
    need = highest_value_needs(context.needs)[0]
    calls = []
    def parse(**kwargs):
        calls.append(kwargs)
        data = kwargs["response_format"].model_validate({"should_ask": True, "selected_need_id": need.need_id,
            "question": need.allowed_questions[0], "suggested_replies": [], "source_refs": list(need.source_refs),
            "reason_summary": "highest_value_supported_need", "confidence": "grounded"})
        return SimpleNamespace(id="public-synthetic-only", usage=None,
            choices=[SimpleNamespace(message=SimpleNamespace(parsed=data))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))
    qwen = QwenProvider(SecretStr("public-synthetic-placeholder"), SecretStr("https://public-synthetic.invalid"), client=client)
    decision, usage = ClarificationSelector().select(qwen, context)
    assert decision.should_ask and len(calls) == 1
    assert calls[0]["model"] == "qwen3.8-flash" and calls[0]["extra_body"] == {"enable_thinking": False}
    assert usage.retries == 0


def test_optional_suggestions_empty_is_valid():
    session, _, _ = session_for(fake=SelectingFake(transform=lambda out: {**out, "suggested_replies": []}))
    q = ask(session)
    assert q.decision.suggested_replies == ()
    assert session.answer(q, "自由输入") is not None


@pytest.mark.parametrize("answer", ["", " "*2, "x"*2001])
def test_invalid_answer_does_not_consume_current_question(answer):
    session, _, _ = session_for()
    q = ask(session)
    assert session.answer(q, answer) is None and session.current_question() == q


def test_structural_events_and_transport_logging_no_raw_answer_resume_prompt_completion(caplog):
    class LoggingFake(SelectingFake):
        def generate_structured(self, messages, *args, **kwargs):
            logging.getLogger("httpx").warning("sensitive synthetic payload %s", messages[1].content)
            return super().generate_structured(messages, *args, **kwargs)
    session, _, fake = session_for(fake=LoggingFake())
    with caplog.at_level(logging.DEBUG):
        q = ask(session)
        session.answer(q, "Public Synthetic Sensitive Answer")
    events = json.dumps([asdict(e) for e in session.events])
    assert "Sensitive Answer" not in events + caplog.text
    assert "Audit Associate" not in events + caplog.text
    assert "eligible_needs" not in caplog.text and "source_quotes" not in events
    assert not hasattr(session, "prompt") and not hasattr(session, "completion")
    assert fake.call_count == 1


@pytest.mark.parametrize("invalid", [False, True])
def test_existing_active_observer_does_not_record_clarification_content(invalid):
    from observability.collector import DiagnosticEventCollector
    from observability.context import diagnostic_scope
    from observability.models import ObservabilityContext, run_id
    fake = SelectingFake(transform=(lambda out: {**out, "sensitive_raw_text": "synthetic private-like answer"}) if invalid else None)
    session, _, _ = session_for(fake=fake)
    collector, identity = DiagnosticEventCollector(), run_id()
    with diagnostic_scope(collector, ObservabilityContext(run_id=identity)):
        session.run(TurnIntent.RESUME_REVIEW)
    rendered = json.dumps([event.model_dump(mode="json") for event in collector.timeline(identity)])
    assert collector.timeline(identity) and fake.call_count == 1
    for forbidden in ("Audit Associate", "Public Synthetic Audit Firm", "eligible_needs", "sensitive_raw_text", "synthetic private-like answer"):
        assert forbidden not in rendered
