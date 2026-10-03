"""Offline execution, evidence, minimization and authority regressions."""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from career_runtime.engine import OrangeRuntime, TurnComplete, AnswerDelta
from career_runtime.models import Activity, Proposal, Relevance
from career_runtime.tools import ToolRegistry
from career_runtime.context import recent_turns
from data.models import UserProfile, EvidenceSourceType
from memory.models import MemoryType
from ui.chat_runtime import Workspace
from tests.agent_doubles import ScriptedProvider, plan, answer, request


@pytest.fixture
def workspace(tmp_path):
    with Workspace(str(uuid4()), tmp_path) as value:
        yield value


def seed(workspace):
    payload = json.loads((Path(__file__).resolve().parents[1] / "data/fixtures/public_confirmed_profile.json").read_text())
    profile = UserProfile.model_validate(payload)
    workspace.memory_service.save_confirmed_profile(workspace.subject_id, profile)
    return profile


def execute(workspace, provider, text="公开合成问题", *, proposal=False):
    events = []
    try:
        for event in OrangeRuntime(provider).run(workspace, text, consent=True, proposal_permission=proposal):
            events.append(event)
    except RuntimeError:
        pass
    return events


@pytest.mark.parametrize("mode", ["GENERAL_QA", "LEARNING_OR_TECHNICAL", "META_OR_CLARIFICATION"])
def test_normal_answer_no_career_forcing_or_unneeded_context(workspace, mode):
    seed(workspace)
    provider = ScriptedProvider([plan(relevance=mode)], answer("生成器是实现迭代器协议的对象。"))
    assert any(isinstance(e, TurnComplete) for e in execute(workspace, provider))
    assert provider.requests[-1]["selected_context"] == []
    assert "skills" not in json.dumps(provider.requests[0]["authority"])
    assert provider.structured_calls == provider.stream_calls == 1


def test_profile_only_selected_fields_and_owned_evidence(workspace):
    original = seed(workspace)
    provider = ScriptedProvider([plan(relevance="DIRECT_CAREER", tools=[request("current_profile", sections=["skills"])])])
    complete = next(e for e in execute(workspace, provider) if isinstance(e, TurnComplete))
    context = provider.requests[-1]["selected_context"]
    assert context and all(item["category"] == "skills" for item in context)
    assert len(context) <= 4
    assert {r["ref"] for item in context for r in item["refs"]} <= {e.id for e in original.evidence}
    assert complete.registry.profile() == original
    serialized = json.dumps(provider.requests, ensure_ascii=False)
    for excluded in [workspace.owner_scope_id, workspace.subject_id, "education_summary", "confirmed_at", "metadata"]:
        assert excluded not in serialized


def test_known_goals_not_reasked_and_no_draft_mutation(workspace):
    original = seed(workspace)
    provider = ScriptedProvider([plan(relevance="PROFILE_OR_MEMORY", tools=[request("goals_preferences")])],
        answer("已有目标可作为本轮依据，无需再填写问卷。"))
    assert any(isinstance(e, TurnComplete) for e in execute(workspace, provider))
    assert provider.requests[-1]["selected_context"]
    assert workspace.memory_service.get_current_confirmed_profile(workspace.subject_id) == original


def test_no_profile_yields_unknown_not_fabricated_experience(workspace):
    provider = ScriptedProvider([plan(relevance="DIRECT_CAREER", tools=[request("current_profile", sections=["skills"])])])
    execute(workspace, provider)
    assert provider.requests[-1]["tool_statuses"][0]["status"] == "unavailable"
    assert provider.requests[-1]["selected_context"] == []


def test_memory_uses_existing_policy_and_preserves_confirmed_authority(workspace):
    service = workspace.memory_service
    owned = service.create_confirmed(subject_id=workspace.subject_id, memory_type=MemoryType.CAREER_PREFERENCE,
        content="AI 产品方向探索 ai_product", source_type=EvidenceSourceType.EXPLICIT_USER_INPUT, confirmed_by_user=True)
    other = service.create_confirmed(subject_id="subject_other", memory_type=MemoryType.CAREER_PREFERENCE,
        content="AI 产品方向探索 ai_product", source_type=EvidenceSourceType.EXPLICIT_USER_INPUT, confirmed_by_user=True)
    candidate = service.create_candidate(subject_id=workspace.subject_id, memory_type=MemoryType.CAREER_PREFERENCE,
        content="AI 产品方向探索 ai_product", source_type=EvidenceSourceType.EXPLICIT_USER_INPUT)
    provider = ScriptedProvider([plan(relevance="DIRECT_CAREER", tools=[request("relevant_memory", role_id="job_001")])])
    execute(workspace, provider, "AI 产品方向探索 ai_product")
    items = provider.requests[-1]["selected_context"]
    assert items and len(items) <= 3
    refs = {r["ref"] for item in items for r in item["refs"]}
    assert owned.memory_id in refs
    assert other.memory_id not in refs and candidate.memory_id not in refs
    assert all(item["status"] == "confirmed" for item in items)


@pytest.mark.parametrize("tool", ["current_profile", "relevant_memory", "known_role"])
def test_irrelevant_personal_tools_are_denied_for_qa(workspace, tool):
    seed(workspace)
    arguments = {"sections": ["skills"]} if tool == "current_profile" else {"role_id": "job_001"}
    provider = ScriptedProvider([plan(tools=[request(tool, **arguments)])])
    execute(workspace, provider)
    assert provider.requests[-1]["selected_context"] == []
    assert provider.requests[-1]["tool_statuses"][0]["status"] == "denied"


def test_multistep_real_observation_and_strict_bound(workspace):
    first = plan(relevance="ROLE_EXPLORATION", tools=[request("known_role", role_id="job_001"), request("known_role", role_id="job_007"), request("known_role", role_id="job_013")], continuing=True)
    second = plan(relevance="ROLE_EXPLORATION", tools=[request("course_project_evidence"), request("goals_preferences")], continuing=True)
    provider = ScriptedProvider([first, second])
    events = execute(workspace, provider)
    assert provider.structured_calls == 2 and provider.stream_calls == 1
    assert len(provider.requests[1]["observations"]) == 3
    assert provider.requests[-1]["bound_reached"]
    assert len(provider.requests[-1]["tool_statuses"]) == 4
    assert any(isinstance(e, Activity) and e.stage == "bounded" for e in events)


def test_repeat_tool_not_executed_twice(workspace):
    tool = request("known_role", role_id="job_001")
    provider = ScriptedProvider([plan(relevance="ROLE_EXPLORATION", tools=[tool], continuing=True),
                                 plan(relevance="ROLE_EXPLORATION", tools=[tool])])
    execute(workspace, provider)
    assert len(provider.requests[-1]["tool_statuses"]) == 1


def test_tool_failure_is_observed_not_fabricated_success(workspace, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("untrusted private exception")
    monkeypatch.setattr(workspace.controller.role_memory_service, "recall", fail)
    provider = ScriptedProvider([plan(relevance="DIRECT_CAREER", tools=[request("relevant_memory")])])
    execute(workspace, provider)
    assert provider.requests[-1]["tool_statuses"][0]["status"] == "failed"
    assert "untrusted private exception" not in json.dumps(provider.requests)


def test_malformed_plan_never_executes_or_streams(workspace):
    provider = ScriptedProvider([{"tools": [{"name": "run_shell"}], "reasoning": "hidden"}])
    events = execute(workspace, provider)
    assert provider.stream_calls == 0
    assert not any(isinstance(e, TurnComplete) for e in events)


@pytest.mark.parametrize("kind", ["ref", "proposal"])
def test_unknown_refs_and_invented_candidate_fail_closed(workspace, kind):
    response = answer(citations=["foreign_evidence"]) if kind == "ref" else answer(proposals=[Proposal(
        kind="memory", dimension="career_direction_priority", value="ai_product", user_quote="invented")])
    events = execute(workspace, ScriptedProvider(response=response))
    assert not any(isinstance(e, TurnComplete) for e in events)


def test_current_goal_change_draft_requires_review_and_retains_history(workspace):
    original = seed(workspace)
    text = "我最近越来越想尝试 AI 产品方向，而不是只做开发。"
    tool = request("profile_draft", dimension="career_direction_priority", value="ai_product", user_quote=text)
    provider = ScriptedProvider([plan(relevance="PROFILE_OR_MEMORY", intent="goal_change", tools=[tool])])
    complete = next(e for e in execute(workspace, provider, text, proposal=True) if isinstance(e, TurnComplete))
    registry = complete.registry
    assert registry.proposals and registry.profile() == original
    assert registry.profile_drafts[0][-1].draft_profile.version == original.version + 1
    assert not registry.profile_drafts[0][-1].draft_profile.confirmed
    with pytest.raises(PermissionError):
        registry.confirm_proposal(registry.proposals[0], confirmed_by_user=False)
    updated = registry.confirm_proposal(registry.proposals[0], confirmed_by_user=True)
    assert updated.version == original.version + 1 and updated.confirmed
    assert len(workspace.memory_service.profile_store.list_profile_history(workspace.subject_id)) == 2


@pytest.mark.parametrize("permission,quote", [(False, "原文"), (True, "模型编造")])
def test_candidate_cannot_gain_authority_or_invent_source(workspace, permission, quote):
    original = seed(workspace)
    tool = request("profile_draft", dimension="career_direction_priority", value="ai_product", user_quote=quote)
    provider = ScriptedProvider([plan(relevance="PROFILE_OR_MEMORY", tools=[tool])])
    events = execute(workspace, provider, "原文", proposal=permission)
    assert workspace.memory_service.get_current_confirmed_profile(workspace.subject_id) == original
    assert not any(isinstance(e, TurnComplete) for e in events)
    assert provider.stream_calls == 0 and provider.structured_calls == 1


def test_candidate_memory_not_automatically_saved(workspace):
    text = "我想优先探索 AI 产品方向。"
    registry = ToolRegistry(workspace, text, proposal_permission=True)
    result = registry.execute(request("memory_candidate", dimension="career_direction_priority", value="ai_product", user_quote=text), Relevance.PROFILE_OR_MEMORY)
    assert result.status == "succeeded" and registry.proposals
    assert not workspace.controller.active_memories()
    confirmed = registry.confirm_proposal(registry.proposals[0], confirmed_by_user=True)
    assert confirmed.status.value == "confirmed" and len(workspace.controller.active_memories()) == 1


def test_same_dimension_memory_change_uses_existing_explicit_resolution(workspace):
    from memory.models import MemoryChangeChoice
    from memory.errors import InvalidMemoryTransitionError
    old = workspace.memory_service.create_confirmed(subject_id=workspace.subject_id, memory_type=MemoryType.CAREER_PREFERENCE,
        content="已确认的公开合成偏好：亲手实现", source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
        confirmed_by_user=True, metadata={"signal_dimension": "work_style.primary_focus", "signal_value": "hands_on_implementation"})
    registry = ToolRegistry(workspace, "我想多做产品和需求工作", proposal_permission=True)
    registry.execute(request("memory_candidate", dimension="work_style_primary_focus", value="product_and_requirements", user_quote=registry.user_text), Relevance.PROFILE_OR_MEMORY)
    proposal = registry.proposals[0]
    with pytest.raises(ValueError):
        registry.confirm_proposal(proposal, confirmed_by_user=True)
    assert workspace.memory_service.memory_store.get(workspace.subject_id, old.memory_id).status.value == "confirmed"
    with pytest.raises(InvalidMemoryTransitionError):
        registry.confirm_proposal(proposal, confirmed_by_user=True, memory_choice=MemoryChangeChoice.KEEP_BOTH)
    updated = registry.confirm_proposal(proposal, confirmed_by_user=True, memory_choice=MemoryChangeChoice.UPDATE_LONG_TERM)
    assert updated.supersedes_memory_id == old.memory_id
    assert workspace.memory_service.memory_store.get(workspace.subject_id, old.memory_id).status.value == "superseded"


def test_history_window_is_bounded_and_skips_old_profile_dump(workspace):
    for index in range(8):
        workspace.store.append_turn(workspace.owner_scope_id, workspace.thread.thread_id, f"问题 {index}", "回答 " * 100)
    workspace.store.append_turn(workspace.owner_scope_id, workspace.thread.thread_id, "复核", "整个旧画像", assistant_metadata={"kind": "profile"})
    selected = recent_turns(workspace.store.list_messages(workspace.owner_scope_id, workspace.thread.thread_id))
    assert len(selected) <= 6 and sum(len(item.text) for item in selected) <= 4500
    assert "整个旧画像" not in [item.text for item in selected]


def test_stream_delivers_delta_before_complete(workspace):
    provider = ScriptedProvider(response=answer("这是逐步交付的公开合成响应。"))
    iterator = OrangeRuntime(provider).run(workspace, "公开问题", consent=True)
    first = next(e for e in iterator if isinstance(e, AnswerDelta))
    assert first.text and provider.delivered < 3
    assert any(isinstance(e, TurnComplete) for e in iterator)


@pytest.mark.parametrize("suggestions", [[], ["给一个生成器例子"], ["解释惰性求值", "比较内存占用"]])
def test_dynamic_zero_to_four_suggestions(workspace, suggestions):
    provider = ScriptedProvider([plan(suggestions="optional_relevant")], answer(suggestions=suggestions))
    events = execute(workspace, provider)
    assert next(e for e in events if isinstance(e, TurnComplete)).answer.suggestions == suggestions


def test_no_provider_without_consent(workspace):
    provider = ScriptedProvider()
    with pytest.raises(PermissionError):
        list(OrangeRuntime(provider).run(workspace, "问题", consent=False))
    assert provider.structured_calls == provider.stream_calls == 0


@pytest.mark.parametrize("section", ["skills", "interests", "values", "goals", "strengths", "development_areas", "career_preferences"])
def test_profile_categories_have_validated_sources_and_goal_type(workspace, section):
    original = seed(workspace)
    registry = ToolRegistry(workspace, "公开问题", proposal_permission=False)
    result = registry.execute(request("current_profile", sections=[section]), Relevance.DIRECT_CAREER)
    assert result.status in {"succeeded", "unavailable"}
    assert all(ref.ref in {e.id for e in original.evidence} for item in result.items for ref in item.refs)
    if section == "goals":
        assert all(item.category.startswith("goals:") for item in result.items)


def test_untrusted_context_cannot_send_credential_shaped_text(workspace):
    from career_runtime.context import messages_for
    with pytest.raises(ValueError):
        messages_for("system policy", {"selected_context": "sk-" + "Q" * 25})


def test_denied_tool_activity_is_skipped_not_fake_read(workspace):
    provider = ScriptedProvider([plan(tools=[request("current_profile", sections=["skills"])])])
    activities = [e for e in execute(workspace, provider) if isinstance(e, Activity) and e.stage == "profile"]
    assert [a.status for a in activities] == ["skipped"]


def test_completed_turn_has_no_unfinished_local_understanding_stage(workspace):
    complete = next(e for e in execute(workspace, ScriptedProvider()) if isinstance(e, TurnComplete))
    latest = {item.stage: item.status for item in complete.activities}
    assert latest["understand"] == latest["plan"] == latest["respond"] == "succeeded"


def test_profile_candidate_stale_review_does_not_overwrite_new_version(workspace):
    original = seed(workspace)
    registry = ToolRegistry(workspace, "我想探索 AI 产品方向", proposal_permission=True)
    registry.execute(request("profile_draft", dimension="career_direction_priority", value="ai_product", user_quote=registry.user_text), Relevance.PROFILE_OR_MEMORY)
    current = original.create_revision(education_summary="另一次明确确认的公开合成修订").confirm()
    workspace.memory_service.save_confirmed_profile(workspace.subject_id, current)
    with pytest.raises(ValueError):
        registry.confirm_proposal(registry.proposals[0], confirmed_by_user=True)
    assert registry.profile() == current


def test_agent_evaluation_suite_is_independent_and_network_disabled():
    from agent_evaluation.run import run
    assert run() == 0
