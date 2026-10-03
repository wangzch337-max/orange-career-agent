"""Public synthetic scenarios with structural expectations, no LLM judge."""

from dataclasses import dataclass

from tests.agent_doubles import plan, answer, request


@dataclass(frozen=True)
class Scenario:
    name: str
    text: str = "公开合成问题"
    mode: str = "GENERAL_QA"
    kind: str = "normal"
    profile: bool = False
    tools: tuple = ()
    clarification: bool = False
    suggestions: tuple = ()


SCENARIOS = (
    Scenario("simple_general_qa"),
    Scenario("technical_learning", text="解释 Python 生成器", mode="LEARNING_OR_TECHNICAL"),
    Scenario("career_sufficient_context", mode="DIRECT_CAREER", profile=True, tools=(request("current_profile", sections=["skills"]),)),
    Scenario("career_missing_context", mode="DIRECT_CAREER", tools=(request("current_profile", sections=["skills"]),)),
    Scenario("known_info_not_reasked", mode="PROFILE_OR_MEMORY", profile=True, tools=(request("goals_preferences"),)),
    Scenario("goal_change_without_overwrite", text="我想探索 AI 产品方向", mode="PROFILE_OR_MEMORY", profile=True, kind="change"),
    Scenario("relevant_confirmed_memory", mode="DIRECT_CAREER", kind="memory", tools=(request("relevant_memory"),)),
    Scenario("irrelevant_memory_excluded", mode="GENERAL_QA", kind="memory", tools=(request("relevant_memory"),)),
    Scenario("actual_tool_failure", mode="DIRECT_CAREER", kind="tool_failure", tools=(request("relevant_memory"),)),
    Scenario("malformed_plan_closed", kind="malformed"),
    Scenario("structured_provider_retry", kind="retry"),
    Scenario("no_career_forcing", text="两杯水各 250ml，一共有多少？"),
    Scenario("zero_suggestions"),
    Scenario("relevant_optional_suggestions", suggestions=("给一个短示例",)),
    Scenario("bounded_multi_step", mode="ROLE_EXPLORATION", kind="multistep"),
    Scenario("runaway_plan_cutoff", mode="ROLE_EXPLORATION", kind="cutoff"),
    Scenario("canonical_immutable", mode="PROFILE_OR_MEMORY", profile=True, tools=(request("current_profile", sections=["values"]),)),
    Scenario("candidate_authority", text="我想探索 AI 产品方向", mode="PROFILE_OR_MEMORY", profile=True, kind="candidate"),
    Scenario("new_chat_exact_profile", profile=True, kind="new_chat"),
    Scenario("truthful_activity", mode="ROLE_EXPLORATION", tools=(request("known_role", role_id="job_001"),)),
    Scenario("no_fake_web_activity"),
    Scenario("no_reasoning_persistence", kind="persist"),
    Scenario("provider_failure_safe_history", kind="failure"),
    Scenario("stream_final_once", kind="persist"),
    Scenario("historical_open_no_reexecution", kind="history"),
    Scenario("one_blocking_clarification", mode="META_OR_CLARIFICATION", clarification=True),
    Scenario("career_exploration_structural_repair", kind="stabilization_B"),
    Scenario("known_capability_structural_repair", kind="stabilization_C"),
    Scenario("goal_change_structural_repair", kind="stabilization_D"),
    Scenario("repair_terminal_failure", kind="stabilization_terminal"),
    Scenario("replan_repair_without_tool_replay", kind="stabilization_replan"),
    Scenario("repair_permission_boundary", kind="stabilization_permission"),
    Scenario("repair_owner_isolation", kind="stabilization_owner"),
    Scenario("repair_closed_diagnostics", kind="stabilization_diagnostics"),
    Scenario("long_general_stream_identity", kind="long_general"),
    Scenario("long_career_authority", kind="long_career"),
    Scenario("long_optional_suggestions_degrade", kind="long_optional"),
    Scenario("long_optional_tail_degrade", kind="long_tail"),
    Scenario("long_output_limit_safe_failure", kind="long_limit"),
    Scenario("long_transport_interrupt", kind="long_interrupt"),
    Scenario("long_service_restart_restore", kind="long_restart"),
    Scenario("long_duplicate_finalization", kind="long_duplicate"),
    Scenario("continuity_general_qa", kind="continuity_general"),
    Scenario("continuity_technical_qa", kind="continuity_technical"),
    Scenario("continuity_audit_career_chain", kind="continuity_audit_chain"),
    Scenario("continuity_accounting_background", kind="continuity_background_1"),
    Scenario("continuity_mechanical_background", kind="continuity_background_2"),
    Scenario("continuity_marketing_background", kind="continuity_background_3"),
    Scenario("continuity_design_background", kind="continuity_background_4"),
    Scenario("continuity_ai_student_demo", kind="continuity_background_0"),
    Scenario("continuity_long_previous_answer", kind="continuity_long"),
    Scenario("continuity_true_failure_recovery", kind="continuity_recovery"),
    Scenario("continuity_stale_failure_cleared", kind="continuity_stale"),
    Scenario("continuity_false_truncation_blocked", kind="continuity_false"),
    Scenario("continuity_profile_owned_reference_reuse", kind="continuity_profile"),
    Scenario("continuity_status_service_restart", kind="continuity_restart"),
    Scenario("continuity_history_budget", kind="continuity_budget"),
    Scenario("continuity_user_feedback_not_diagnosis", kind="continuity_feedback"),
)
