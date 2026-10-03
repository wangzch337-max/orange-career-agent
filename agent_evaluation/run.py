"""Run the independent network-disabled Agent suite; emit only safe outcomes."""

import socket
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from agent_evaluation.scenarios import SCENARIOS
from career_runtime.engine import TurnComplete, AnswerDelta
from career_runtime.models import Activity
from career_runtime.session import AgentSession, FAILURE_TEXT
from data.models import EvidenceSourceType
from memory.models import MemoryType
from tests.agent_doubles import ScriptedProvider, plan, answer, request
from tests.test_agent_runtime import seed
from ui.chat_runtime import Workspace


def blocked(*_args, **_kwargs):
    raise AssertionError("Agent evaluation forbids network access.")


def evaluate(scenario, root):
    if scenario.kind.startswith("continuity_"):
        from tests import test_conversation_continuity as checks
        from career_runtime.streaming import ResponseStreamError
        kind = scenario.kind.removeprefix("continuity_")
        if kind == "restart":
            checks.test_thread_switch_refresh_and_service_restart_preserve_truth(root)
            return
        with Workspace(str(uuid4()), root) as workspace:
            if kind.startswith("background_"):
                checks.public_dialogue(workspace, checks.BACKGROUNDS[int(kind[-1])])
            elif kind == "general": checks.test_four_turn_general_and_technical_reference_chains(workspace, "GENERAL_QA", "怎么安慰情绪低落的朋友？", "先倾听，不抢着给建议")
            elif kind == "technical": checks.test_four_turn_general_and_technical_reference_chains(workspace, "LEARNING_OR_TECHNICAL", "generator 和 iterator 有什么区别？", "生成器通过 yield 保留执行位置")
            elif kind == "audit_chain": checks.test_audit_to_business_analysis_chain_retains_current_user_facts(workspace)
            elif kind == "long": checks.test_long_previous_answer_keeps_head_all_dimensions_middle_tail_and_budget(workspace, 9500)
            elif kind == "recovery": checks.test_true_failure_notice_not_semantic_content_and_recovery_truthful(workspace, ResponseStreamError("output_limit"), "FAILED_TRANSPORT")
            elif kind == "stale": checks.test_old_failure_then_success_then_continuation_clears_stale_failure(workspace)
            elif kind == "false": checks.test_explicit_false_runtime_claim_blocked_before_display_and_commit(workspace, "抱歉，刚才的回答被截断了。")
            elif kind == "profile": checks.test_profile_assisted_followup_reuses_owned_same_version_evidence_without_reasking(workspace)
            elif kind == "budget": checks.test_old_unrelated_history_falls_out_and_explicit_recent_reference_is_available(workspace)
            elif kind == "feedback": checks.test_user_reported_incomplete_is_feedback_not_transport_diagnosis(workspace)
            else: raise AssertionError("Unknown continuity scenario.")
        return
    if scenario.kind.startswith("long_"):
        from tests import test_long_response as checks
        if scenario.kind == "long_restart":
            checks.test_service_restart_restores_long_exactly_without_provider(root)
            return
        with Workspace(str(uuid4()), root) as workspace:
            kind = scenario.kind.removeprefix("long_")
            if kind == "general": checks.test_length_chunk_unicode_matrix_identical_once_and_reload(workspace,5000,"uneven",True)
            elif kind == "career": checks.test_long_career_reads_context_without_authority_mutation(workspace)
            elif kind == "optional": checks.test_malformed_optional_suggestions_keep_long_core(workspace,{})
            elif kind == "tail": checks.test_incomplete_optional_tail_after_sealed_core_kept_only_on_stop(workspace,'["未完整结束')
            elif kind == "limit": checks.test_real_truncation_never_salvaged_even_with_complete_core(workspace,"length")
            elif kind == "interrupt": checks.test_interrupted_after_large_visible_core_still_fails(workspace)
            elif kind == "duplicate": checks.test_duplicate_identical_completion_is_idempotent_but_conflicting_fails(workspace)
        return
    if scenario.kind.startswith("stabilization_"):
        from tests import test_agent_planning as checks
        if scenario.kind == "stabilization_diagnostics":
            checks.test_closed_diagnostic_field_does_not_weaken_global_metadata()
            return
        with Workspace(str(uuid4()), root) as workspace:
            kind = scenario.kind.removeprefix("stabilization_")
            if kind in {"B", "C", "D"}:
                shape = checks.SHAPES[{"B": 0, "C": 1, "D": 2}[kind]]
                checks.test_synthetic_career_shape_repair_completes_without_authority_mutation(workspace, shape)
            else:
                check = {"terminal": checks.test_invalid_repair_is_terminal_once_without_stream_or_duplicate_history,
                    "replan": checks.test_replan_repair_keeps_observations_and_does_not_reexecute_completed_tools,
                    "permission": checks.test_repair_cannot_bypass_policy_after_initial_structural_failure,
                    "owner": checks.test_repair_context_cannot_read_another_owner}[kind]
                check(workspace)
        return
    if scenario.kind == "retry":
        from tests.test_agent_streaming import test_structured_planner_reuses_bounded_existing_retry_mechanism
        test_structured_planner_reuses_bounded_existing_retry_mechanism()
        return
    with Workspace(str(uuid4()), root) as workspace:
        original = seed(workspace) if scenario.profile else None
        tools = list(scenario.tools)
        if scenario.kind == "candidate":
            tools = [request("profile_draft", dimension="career_direction_priority", value="ai_product", user_quote=scenario.text)]
        if scenario.kind == "change":
            # No candidate permission: read old preference, adapt current response.
            tools = [request("goals_preferences")]
        if scenario.kind == "memory":
            workspace.memory_service.create_confirmed(subject_id=workspace.subject_id,
                memory_type=MemoryType.CAREER_PREFERENCE, content="职业方向探索 AI 产品",
                source_type=EvidenceSourceType.EXPLICIT_USER_INPUT, confirmed_by_user=True)
        if scenario.kind == "tool_failure":
            workspace.controller.role_memory_service.recall = blocked
        first = plan(relevance=scenario.mode, tools=tools, clarify=scenario.clarification,
                     suggestions="optional_relevant" if scenario.suggestions else "none")
        plans = [first]
        if scenario.kind in {"multistep", "cutoff"}:
            plans = [plan(relevance=scenario.mode, tools=[request("known_role", role_id="job_001"), request("known_role", role_id="job_007"), request("known_role", role_id="job_013")], continuing=True),
                     plan(relevance=scenario.mode, tools=[request("course_project_evidence"), request("goals_preferences")], continuing=scenario.kind == "cutoff")]
        if scenario.kind == "malformed":
            plans = [{"reasoning": "hidden", "tools": [{"name": "arbitrary_io"}]}]
        provider = ScriptedProvider(plans, answer(suggestions=scenario.suggestions),
                                    failure=RuntimeError("untrusted exception") if scenario.kind == "failure" else None)
        session = AgentSession(workspace, provider_factory=lambda: provider)
        session.set_consent(granted=True)
        session.queue(scenario.text, "typed", allow_proposal=scenario.kind == "candidate")
        pending = session.pending
        events = list(session.stream_turn(pending))
        stored = workspace.store.list_messages(workspace.owner_scope_id, pending.thread_id)
        assert len(stored) == 2
        successful = any(isinstance(event, TurnComplete) for event in events)
        assert successful == (scenario.kind not in {"failure", "malformed"})
        assert workspace.memory_service.get_current_confirmed_profile(workspace.subject_id) == original
        assert provider.structured_calls <= 2 and provider.stream_calls <= 1
        assert "reasoning" not in repr(stored) and "scratchpad" not in repr(stored)
        assert not any(isinstance(event, Activity) and "web" in event.stage for event in events)
        if successful:
            payload = provider.requests[-1]
            assert not any(private in str(provider.requests) for private in (workspace.subject_id, workspace.owner_scope_id))
            assert len(payload["tool_statuses"]) <= 4
            assert len(payload["recent_turns"]) <= 6
            assert stored[-1].metadata["suggestions"] == list(scenario.suggestions)
            if scenario.mode in {"GENERAL_QA", "LEARNING_OR_TECHNICAL"}:
                assert not payload["selected_context"]
            if scenario.kind == "candidate":
                assert session.last_result.registry.profile_drafts and not workspace.controller.active_memories()
            if scenario.kind == "change":
                assert not payload["tool_proposals"]
            if scenario.kind == "memory" and scenario.mode == "DIRECT_CAREER":
                assert payload["selected_context"]
            if scenario.kind == "tool_failure":
                assert payload["tool_statuses"][0]["status"] == "failed"
            if scenario.kind == "cutoff":
                assert payload["bound_reached"]
            assert any(isinstance(event, AnswerDelta) for event in events)
        else:
            assert stored[-1].content == FAILURE_TEXT
        if scenario.kind in {"persist", "history"}:
            counts = provider.structured_calls, provider.stream_calls
            assert list(session.stream_turn(pending)) == []
            workspace.activate(pending.thread_id)
            assert (provider.structured_calls, provider.stream_calls) == counts
            assert len(workspace.chat.messages) == 2
        if scenario.kind == "new_chat":
            fresh = workspace.create_new_thread()
            assert (fresh.profile_id_ref, fresh.profile_version_ref) == (original.profile_id, original.version)
            assert not workspace.chat.messages


def run():
    base = Path(__file__).resolve().parents[1] / "data/local/agent-evaluation"
    base.mkdir(parents=True, exist_ok=True)
    failures = []
    with patch.object(socket.socket, "connect", blocked), patch.object(socket, "create_connection", blocked):
        for scenario in SCENARIOS:
            with TemporaryDirectory(dir=base) as directory:
                try:
                    evaluate(scenario, Path(directory))
                except Exception:
                    failures.append(scenario.name)
                    print(f"FAIL {scenario.name}")
                else:
                    print(f"PASS {scenario.name}")
    print(f"total={len(SCENARIOS)} PASS={len(SCENARIOS)-len(failures)} FAIL={len(failures)} network_attempts=0")
    return len(failures)


if __name__ == "__main__":
    raise SystemExit(bool(run()))
