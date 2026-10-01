"""The initial 27 public Golden contracts, independent of result wording."""

from evaluation.models import (
    Capability, EvaluationLayer, EvaluationStatus, GoldenScenario, RequiredExpectation,
    ForbiddenExpectation, UncertaintyExpectation, ProvenanceExpectation,
    RelationExpectation, LifecycleExpectation, WorkflowExpectation,
)
from evaluation.taxonomy import FailureTaxonomy as T
from data.models import MatchRelationType as R


def required(check_id, path, expected=True, *, taxonomy=T.CROSS_COMPONENT_INVARIANT_BREAK,
             operation="equals", family=RequiredExpectation):
    return family(check_id=check_id, path=path, expected=expected, operation=operation,
                  taxonomy=taxonomy, summary=check_id.replace("_", " "), source_component=path.split(".")[0])


def forbidden(check_id, path, values, taxonomy, mode="values"):
    return ForbiddenExpectation(check_id=check_id, path=path, forbidden=values, mode=mode,
                                taxonomy=taxonomy, summary=check_id.replace("_", " "), source_component=path)


def uncertainty(path, topics):
    return UncertaintyExpectation(check_id="preserve_unknown", path=path, topics=topics,
                                  taxonomy=T.UNCERTAINTY_COLLAPSED, summary="保留证据不足的未知", source_component=path)


def provenance(path, scope="evidence"):
    return ProvenanceExpectation(check_id=f"{scope}_provenance", path=path, scope=scope,
                                 taxonomy=T.AUTHORITY_VIOLATION if scope == "memory" else T.PROVENANCE_MISSING,
                                 summary="来源引用可回溯且归属正确", source_component=path)


def relation(kind, label=None, forbidden_types=()):
    return RelationExpectation(check_id="relation_semantics", relation=kind, job_label=label,
                               forbidden_substitutions=list(forbidden_types), taxonomy=T.MATCH_RELATION_MISCLASSIFICATION,
                               summary="关系满足指定证据条件且未替换为错误关系", source_component="match")


NO_ML = ["PyTorch", "TensorFlow", "Model training", "Fine-tuning", "MLOps"]
NO_SCORE = ["overall_score", "match_score", "fit_score", "quality_score", "percentage", "stars"]
NO_RANK = ["ranking", "role_ranking", "best_role", "recommended_role"]
NO_ML_CLAIMS = ["pytorch", "tensorflow", "model training", "fine-tuning", "mlops", "deep ml", "deep learning training"]


def match_checks():
    return [provenance("match_provenance"), provenance("action_provenance", "actions"),
            required("relation_minimum_conditions", "relation_rules", taxonomy=T.MATCH_RELATION_MISCLASSIFICATION),
            forbidden("no_match_score", "match", NO_SCORE, T.MATCH_SCORE_INTRODUCED, "keys"),
            forbidden("no_role_ranking", "match", NO_RANK, T.ROLE_RANKING_INTRODUCED, "keys"),
            forbidden("no_numeric_or_ranked_verdict", "match", ["%", "★", "best role", "ranked #", "overall fit", "match score", "fit score"],
                      T.MATCH_SCORE_INTRODUCED, "claim_fragments"),
            forbidden("no_career_verdict", "match_claims", ["unsuitable", "do not pursue", "incompatible", "最适合", "不适合"],
                      T.EVIDENCE_OVERCLAIM, "claim_fragments")]


def initial_scenarios() -> list[GoldenScenario]:
    scenarios = []
    def add(sid, title, capability, checks, *, uncertain=False, contract=False, journey=()):
        layer = EvaluationLayer.JOURNEY if journey else EvaluationLayer.CONTRACT if contract else EvaluationLayer.SEMANTIC
        refs = ["data/fixtures/public_confirmed_profile.json", "data/fixtures/jobs/demo_jobs.json"]
        if capability == Capability.SELF_DISCOVERY:
            refs = ["evaluation/fixtures/application_input.json"]
        elif capability == Capability.MEMORY:
            refs = ["evaluation/fixtures/memory_cases.json"]
        elif capability == Capability.CONVERSATION or journey or sid in {"JI_003", "ACT_002"}:
            refs = ["evaluation/fixtures/guided_answers.json", "data/fixtures/jobs/demo_jobs.json",
                    "data/fixtures/sample_user_input.json", "data/fixtures/sample_courses.json"]
        if sid in {"E2E_001", "E2E_004"}:
            refs = ["evaluation/fixtures/sparse_input.json" if sid == "E2E_004" else "evaluation/fixtures/application_input.json",
                    "evaluation/fixtures/guided_answers.json", "data/fixtures/jobs/demo_jobs.json", "data/fixtures/sample_courses.json"]
        if sid == "CONV_001":
            refs = ["evaluation/fixtures/guided_answers.json"]
        scenarios.append(GoldenScenario(
            scenario_id=sid, title=title, description=f"合成案例：{title}；检查生产结构与边界，不评价措辞。",
            layer=layer, capability=capability, input_fixture_refs=refs,
            expected_status=EvaluationStatus.EXPECTED_UNCERTAINTY if uncertain else EvaluationStatus.PASS,
            tags=[capability.value, "synthetic", "offline", "uncertainty" if uncertain else "contract"],
            checks=checks, journey_steps=list(journey),
            notes="Fake provider仅验证已定义场景与生产约束；不代表 live LLM 质量。",
        ))
    sd = Capability.SELF_DISCOVERY
    add("SD_001", "Python/API/LLM 应用证据不过度推断", sd, [
        required("application_skills", "skills", ["Python", "API integration", "LLM API usage"], operation="subset"),
        provenance("profile_provenance"), forbidden("no_ml_invention", "skills", NO_ML, T.UNSUPPORTED_INFERENCE),
        forbidden("no_depth_overclaim", "capability_claims", NO_ML_CLAIMS, T.EVIDENCE_OVERCLAIM, "claim_fragments"),
        required("draft_not_authority", "profile_confirmed", False, taxonomy=T.PROFILE_CONFIRMATION_BYPASS)])
    add("SD_002", "未证明训练深度保持未知", sd, [uncertainty("uncertainties", NO_ML),
        forbidden("no_ml_capability", "skills", NO_ML, T.EVIDENCE_OVERCLAIM),
        forbidden("no_depth_overclaim", "capability_claims", NO_ML_CLAIMS, T.EVIDENCE_OVERCLAIM, "claim_fragments"),
        required("no_invented_gaps", "development", [], taxonomy=T.UNKNOWN_COLLAPSED_TO_GAP)], uncertain=True)
    add("SD_003", "Build Orange 是项目目标", sd, [
        required("project_goal", "goal_types", ["project_goal"]),
        forbidden("not_career_goal", "goal_types", ["career_goal"], T.GOAL_TYPE_MISCLASSIFICATION)])
    add("SD_004", "证据缺席不是弱点", sd, [uncertainty("uncertainties", NO_ML),
        required("absence_not_weakness", "development", [], taxonomy=T.UNKNOWN_COLLAPSED_TO_GAP)], uncertain=True)
    ji = Capability.JOB_INTELLIGENCE
    add("JI_001", "技术与岗位事实引用来源", ji, [provenance("job_provenance"),
        required("explicit_technology_only", "technology_supported", taxonomy=T.JOB_REQUIREMENT_INVENTED)])
    add("JI_002", "不完整 JD 不用刻板印象填空", ji, [
        uncertainty("job_unknowns", ["salary", "promotion_path", "work_life_balance", "remote_work_policy", "team_size"]),
        required("no_invented_stack", "technology_labels", ["Python"])], uncertain=True)
    add("JI_003", "同一岗位跨偏好与记忆事实一致", ji, [
        required("job_facts_independent", "job_facts_independent", taxonomy=T.JOB_FACT_CONTAMINATION),
        required("job_memory_retrieval_zero", "job_memory_retrieval_zero", taxonomy=T.AUTHORITY_VIOLATION)], contract=True)
    mi = Capability.MATCH
    cases = [
        ("MI_001", "Python 直接证据支持 strong alignment", R.STRONG_ALIGNMENT, "Python", (), False),
        ("MI_002", "SQL 未被证明不是能力缺口", R.EVIDENCE_MISSING, "SQL", (R.CONFIRMED_GAP, R.EXPERIENCE_DEPTH_GAP), True),
        ("MI_003", "明确 SQL 有限经验可构成 confirmed gap", R.CONFIRMED_GAP, "SQL", (R.EVIDENCE_MISSING,), False),
        ("MI_004", "相关原型与交付深度区分缺席", R.EXPERIENCE_DEPTH_GAP, None, (), False),
        ("MI_005", "客户沟通偏好摩擦不作职业裁决", R.POTENTIAL_FRICTION, None, (), False),
        ("MI_006", "岗位未知不是用户弱点", R.UNKNOWN, "salary", (R.CONFIRMED_GAP,), True),
    ]
    for sid, title, kind, label, banned, uncertain in cases:
        checks = [*match_checks(), relation(kind, label, banned)]
        if uncertain:
            checks.append(uncertainty("relation_types", [kind.value]))
        add(sid, title, mi, checks, uncertain=uncertain)
    mem = Capability.MEMORY
    for sid, title, category in (
        ("MEM_001", "更相似 candidate 不作为权威", T.CANDIDATE_MEMORY_USED_AS_AUTHORITY),
        ("MEM_002", "更相似 superseded 历史被排除", T.STALE_MEMORY_USE),
        ("MEM_003", "archived 记录被排除", T.STALE_MEMORY_USE),
        ("MEM_004", "相同内容不同 subject 被排除", T.SUBJECT_LEAKAGE),
    ):
        add(sid, title, mem, [required("excluded_record_absent", "excluded_absent", taxonomy=category),
            required("active_present", "active_present", taxonomy=T.AUTHORITY_VIOLATION),
            provenance("memory_provenance", "memory")], contract=True)
    add("MEM_005", "检索不更改 canonical/vector 状态", mem, [
        required("read_only_snapshot", "memory_read_only", taxonomy=T.MEMORY_MUTATION_ON_READ,
                 family=LifecycleExpectation), provenance("memory_provenance", "memory")], contract=True)
    conv = Capability.CONVERSATION
    add("CONV_001", "未知回答保留未知并有界澄清", conv, [
        uncertainty("conversation_unknowns", ["work_style", "project_evidence"]),
        required("bounded_choices", "bounded_choices"), required("conversation_no_provider", "conversation_calls", 0,
            taxonomy=T.NETWORK_BOUNDARY_VIOLATION)], uncertain=True)
    add("CONV_002", "先画像确认后岗位探索", conv, [
        required("guided_gate", "guided_gate", taxonomy=T.WORKFLOW_GATE_BYPASS, family=WorkflowExpectation),
        required("roles_hidden_before_confirmation", "roles_hidden", taxonomy=T.PROFILE_CONFIRMATION_BYPASS,
            family=WorkflowExpectation), required("same_thread_resume", "same_thread_resume", taxonomy=T.WORKFLOW_GATE_BYPASS),
        required("self_discovery_once", "self_discovery_calls", 1)], contract=True)
    act = Capability.ACTION
    add("ACT_001", "缺失证据引导验证而非宣判", act, [*match_checks(),
        required("verify_action_for_missing", "verify_action_for_missing", taxonomy=T.ACTION_UNGROUNDED)])
    add("ACT_002", "已做过仅触发证据复核", act, [
        required("already_done_review", "already_done_review"),
        required("no_auto_capability", "profile_unchanged", taxonomy=T.ACTION_AUTO_CONFIRMED_CAPABILITY),
        required("no_auto_memory", "memory_unchanged", taxonomy=T.LIFECYCLE_BYPASS)], contract=True)
    add("ACT_003", "未知岗位信息先调查", act, [*match_checks(),
        required("unknown_action_investigates", "unknown_action_investigates", taxonomy=T.ACTION_UNGROUNDED)])
    e2e = Capability.END_TO_END
    add("E2E_001", "应用工程：发现→确认→岗位→Match→行动", e2e, [*match_checks(),
        required("self_discovery_once", "self_discovery_calls", 1),
        required("confirmed_profile_gate", "confirmed_profile_gate", taxonomy=T.PROFILE_CONFIRMATION_BYPASS),
        required("completed", "completed", taxonomy=T.CROSS_COMPONENT_INVARIANT_BREAK),
        forbidden("no_unproven_ml", "skills", NO_ML, T.UNSUPPORTED_INFERENCE),
        forbidden("no_depth_overclaim", "capability_claims", NO_ML_CLAIMS, T.EVIDENCE_OVERCLAIM, "claim_fragments")],
        journey=["guided_discovery", "draft", "explicit_confirm", "job_intelligence", "match", "action_plan"])
    add("E2E_002", "产品兴趣记忆回顾与 defer 不改 Match", e2e, [
        provenance("memory_provenance", "memory"), required("match_unchanged", "match_unchanged"),
        required("job_unchanged", "job_unchanged", taxonomy=T.JOB_FACT_CONTAMINATION),
        required("candidate_only", "candidate_only", taxonomy=T.LIFECYCLE_BYPASS),
        required("newest_input_preserved", "newest_input_preserved", taxonomy=T.AUTHORITY_VIOLATION),
        required("defer_zero_writes", "defer_zero_writes", taxonomy=T.MEMORY_MUTATION_ON_READ)],
        journey=["confirm_profile", "role_memory_recall", "current_preference", "change_candidate", "defer"])
    add("E2E_003", "显式更新记忆后另行确认画像 v2", e2e, [
        required("supersession_lifecycle", "supersession_lifecycle", taxonomy=T.LIFECYCLE_BYPASS, family=LifecycleExpectation),
        required("vector_replacement", "vector_replacement", taxonomy=T.STALE_MEMORY_USE),
        required("draft_not_current", "draft_not_current", taxonomy=T.PROFILE_CONFIRMATION_BYPASS),
        required("version_history", "profile_versions", [1, 2], taxonomy=T.PROFILE_VERSIONING_ERROR),
        required("match_snapshot_unchanged", "match_unchanged"),
        required("separate_profile_confirmation", "separate_profile_confirmation", taxonomy=T.PROFILE_CONFIRMATION_BYPASS)],
        journey=["confirm_v1", "preference_change", "explicit_memory_update", "draft_v2", "explicit_profile_confirm", "history"])
    add("E2E_004", "稀疏证据保守贯穿完整旅程", e2e, [*match_checks(),
        uncertainty("uncertainties", ["career_direction", "technical_depth"]),
        required("no_invented_strengths", "strengths", [], taxonomy=T.UNSUPPORTED_INFERENCE),
        required("no_invented_gaps", "development", [], taxonomy=T.UNKNOWN_COLLAPSED_TO_GAP),
        required("sparse_relations_safe", "sparse_relations_safe", taxonomy=T.UNKNOWN_COLLAPSED_TO_GAP),
        required("completed", "completed")], uncertain=True,
        journey=["sparse_input", "uncertain_draft", "explicit_confirm", "job_intelligence", "evidence_missing_match", "verify_actions"])
    return scenarios
