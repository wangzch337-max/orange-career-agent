"""Adapters execute real production paths and expose only synthetic observations.

Expected values live in catalogue.py; adapters do not decide evaluation status.
Fixtures describe canned Fake responses, not claims about live model quality.
"""

import json
from dataclasses import replace
from pathlib import Path

from agents.action_renderer import ActionRenderer
from agents.job_intelligence import JobIntelligenceAgent, public_offline_job_extraction
from agents.job_intelligence_models import JobIntelligenceExtraction
from agents.match_context import MatchContextBuilder
from agents.match_insight import MatchInsightAgent, public_offline_match_extraction
from agents.self_discovery import SelfDiscoveryAgent
from agents.self_discovery_models import SelfDiscoveryExtraction
from data.models import (UserProfile, InferenceType, GoalType, EvidenceSourceType, ProfileUncertainty,
                         ClarificationQuestion, JobUncertainty)
from evaluation.checks import normalize_label
from evaluation.scenarios.catalogue import NO_ML
from memory.embeddings import FakeEmbeddingProvider
from memory.models import MemoryType, MemoryChangeChoice, MemoryStatus
from memory.service import build_semantic_memory_service
from providers.fake import FakeLLMProvider
from tools.course_data import MockCourseDataProvider
from tools.job_data import MockJobDataProvider
from ui.conversation import ConversationStage, QUESTIONS
from ui.demo_controller import DemoController, DemoWorkflowError
from ui.presentation import AUTHORITY_UNKNOWN
from workflows.langgraph_workflow import OrangeGraphRunner, build_orange_graph


ROOT = Path(__file__).resolve().parents[2]


def load_input(*, sparse=False):
    filename = "sparse_input.json" if sparse else "application_input.json"
    return json.loads((ROOT / "evaluation" / "fixtures" / filename).read_text())


def application_extraction(*, sparse=False):
    unknowns = ["career_direction", "technical_depth"] if sparse else NO_ML
    base = dict(
        profile_uncertainties=[ProfileUncertainty(topic=topic, reason="Synthetic source does not establish this capability.")
                               for topic in unknowns],
        clarification_questions=[ClarificationQuestion(question_id="q_eval_001", question="Which evidence could you review?",
            topic="technical_depth", reason="Preserve uncertainty rather than infer a deficit.")],
    )
    if sparse:
        return SelfDiscoveryExtraction(**base)
    def signal(label, evidence, *, explicit=False):
        return dict(label=label, description="A bounded synthetic statement; no employment or model-training claim.",
                    confidence=1.0 if explicit else 0.85, evidence_ids=[evidence],
                    inference_type=InferenceType.EXPLICIT_FACT if explicit else InferenceType.EVIDENCE_SUPPORTED_INFERENCE)
    return SelfDiscoveryExtraction(
        skills=[signal(label, "project_001") for label in ("Python", "API integration", "LLM API usage")],
        strengths=[signal("Application prototyping", "project_001")],
        interests=[signal("AI application and AI product exploration", "career_001", explicit=True)],
        goals=[dict(**signal("Build Orange", "career_002", explicit=True), goal_type=GoalType.PROJECT_GOAL)],
        values=[signal("Practical impact", "value_001", explicit=True)],
        career_preferences=[signal("Hands-on implementation", "preference_001", explicit=True)], **base,
    )


def profile_observation(profile, uncertainties):
    signals = [*profile.skills, *profile.interests, *profile.values, *profile.goals,
               *profile.strengths, *profile.development_areas, *profile.career_preferences]
    allowed = [item.id for item in profile.evidence]
    return dict(skills=[item.label for item in profile.skills], strengths=[item.text for item in profile.strengths],
        capability_claims=[dict(label=getattr(item, "label", getattr(item, "text", "")),
                               description=getattr(item, "description", "")) for item in [*profile.skills, *profile.strengths]],
        development=[item.text for item in profile.development_areas], profile_confirmed=profile.confirmed,
        goal_types=[item.goal_type.value for item in profile.goals], uncertainties=[item.topic for item in uncertainties],
        profile_provenance=[dict(refs=item.evidence_ids, allowed=allowed) for item in signals])


def public_profile(*, no_sql=False):
    profile = UserProfile.model_validate_json((ROOT / "data/fixtures/public_confirmed_profile.json").read_text())
    if no_sql:
        profile = UserProfile.model_validate({**profile.model_dump(), "development_areas": []})
    return profile


def analyze_job(job):
    provider = MockJobDataProvider()
    fake = FakeLLMProvider(public_offline_job_extraction(job))
    return JobIntelligenceAgent(provider, fake).analyze(job)


def job_by_id(job_id):
    return next(item for item in MockJobDataProvider().load() if item.job_id == job_id)


def job_observation(record, job):
    signals = [*record.actual_work, *record.required_capabilities, *record.preferred_capabilities,
        *record.technology_signals, *record.work_style, *record.collaboration_context,
        *record.growth_exposure, *record.potential_friction]
    return dict(job_provenance=[dict(refs=item.evidence_ids, allowed=[ev.id for ev in record.evidence]) for item in signals],
        technology_supported=set(item.label for item in record.technology_signals).issubset(job.technology_tags),
        technology_labels=[item.label for item in record.technology_signals],
        job_unknowns=[item.topic for item in record.uncertainties])


# Minimal evidence-conditions matrix, NOT a second relation generation engine.
# It never chooses, repairs or replaces a production relation.
RELATION_MINIMUMS = {
    "strong_alignment": "both sides; capability evidence, not preference-only",
    "partial_alignment": "both sides; bounded skill/interest/goal evidence",
    "evidence_missing": "job requirement; no profile capability asserted",
    "confirmed_gap": "explicit evidenced development area + job requirement",
    "experience_depth_gap": "existing skill/strength evidence + relevant job work",
    "preference_alignment": "confirmed preference + job work",
    "potential_friction": "preference/value + job evidence; no exclusion verdict",
    "unknown": "at least one referenced uncertain signal; not a confirmed gap",
}


def relation_minimums(rows):
    if not rows:
        return False
    for row in rows:
        relation, p, j = row["relation"], set(row["profile_categories"]), set(row["job_categories"])
        if relation not in RELATION_MINIMUMS:
            return False
        if relation not in {"unknown", "evidence_missing"} and not (p and j):
            return False
        if relation == "strong_alignment" and not p.intersection({"skill", "strength"}):
            return False
        if relation == "partial_alignment" and not p.intersection({"skill", "strength", "interest", "goal", "value"}):
            return False
        if relation == "evidence_missing" and (p or "required_capability" not in j):
            return False
        if relation == "confirmed_gap" and not ("development_area" in p and "required_capability" in j and row["explicit_limit"]):
            return False
        if relation == "experience_depth_gap" and not p.intersection({"skill", "strength"}):
            return False
        if relation == "preference_alignment" and "career_preference" not in p:
            return False
        if relation == "potential_friction" and not p.intersection({"career_preference", "value"}):
            return False
        if relation == "unknown" and not ("uncertainty" in j or row["profile_uncertain"]):
            return False
    return True


def match_observation(result, context, profile):
    p = {item.signal_id: item for item in context.profile_signals}
    j = {item.signal_id: item for item in context.job_signals}
    pe = {item.id: item for item in profile.evidence}
    relations, provenance_rows, actions = [], [], []
    for insight in result.insights():
        link = insight.evidence_link
        profile_signals = [p[key] for key in link.profile_signal_ids if key in p]
        job_signals = [j[key] for key in link.job_signal_ids if key in j]
        relations.append(dict(relation=insight.relation_type.value,
            job_labels=[item.label for item in job_signals],
            profile_categories=[item.category.value for item in profile_signals],
            job_categories=[item.category.value for item in job_signals],
            explicit_limit=any(pe[ev].metadata.get("supports_development_area", False)
                               for item in profile_signals for ev in item.evidence_ids if ev in pe),
            profile_uncertain=any(not item.confirmed_by_user for item in profile_signals)))
        for refs, ids, owners, allowed in (
            (link.profile_evidence_ids, link.profile_signal_ids, p, [item.evidence_id for item in context.profile_evidence]),
            (link.job_evidence_ids, link.job_signal_ids, j, [item.evidence_id for item in context.job_evidence]),
        ):
            if ids or refs:
                provenance_rows.append(dict(refs=refs, allowed=allowed,
                    owned=[ev for key in ids if key in owners for ev in owners[key].evidence_ids],
                    signal_ids_valid=all(key in owners for key in ids),
                    allow_empty=insight.relation_type.value == "unknown" and bool(ids)))
    by_id = {item.insight_id: item for item in result.insights()}
    for action in result.action_items:
        related = [by_id[key] for key in action.related_insight_ids if key in by_id]
        labels = [owners[key].label for insight in related for ids, owners in (
            (insight.evidence_link.profile_signal_ids, p), (insight.evidence_link.job_signal_ids, j)
        ) for key in ids if key in owners]
        rendered = ActionRenderer().render(action_type=action.action_type, target_label=action.target_label,
                                           related_insights=related) if related else None
        actions.append(dict(related_ids=action.related_insight_ids,
            related_ids_valid=all(key in by_id for key in action.related_insight_ids),
            target_owned=normalize_label(action.target_label) in map(normalize_label, labels),
            recipe_valid=rendered is not None and action.description == rendered.description
                and action.expected_evidence == rendered.expected_evidence and action.rationale == rendered.rationale,
            expected_evidence_present=bool(action.expected_evidence), rationale_present=bool(action.rationale)))
    return dict(match=result.model_dump(mode="json"), relations=relations,
        match_claims=[dict(title=item.title, description=item.description) for item in result.insights()],
        match_provenance=provenance_rows, action_provenance=actions,
        relation_rules=relation_minimums(relations), relation_types=[row["relation"] for row in relations],
        verify_action_for_missing=any(action.action_type.value == "verify_existing_capability" and
            all(by_id[key].relation_type.value == "evidence_missing" for key in action.related_insight_ids)
            for action in result.action_items),
        unknown_action_investigates=any(action.action_type.value == "investigate_job_unknown" and
            all(by_id[key].relation_type.value == "unknown" for key in action.related_insight_ids)
            for action in result.action_items))


def match_case(scenario_id):
    job_id = {"MI_001": "job_007", "MI_004": "job_007", "MI_005": "job_004"}.get(scenario_id, "job_013")
    profile = public_profile(no_sql=scenario_id in {"MI_002", "ACT_001"})
    record = analyze_job(job_by_id(job_id))
    context = MatchContextBuilder().build(profile, record)
    agent = MatchInsightAgent(FakeLLMProvider(public_offline_match_extraction(context)))
    result, _, context = agent.analyze_with_details(profile, record)
    return match_observation(result, context, profile)


def memory_snapshot(service, subject):
    return ([item.model_dump(mode="json") for item in service.memory_store.list_history(subject)],
            [item.model_dump(mode="json") for item in service.vector_index.list_entries(subject)])


def memory_rows(service, subject, refs):
    return [dict(refs=list(refs), active_same_subject=[item.memory_id for item in service.memory_store.list_active(subject)])]


def memory_case(scenario_id, temporary_root):
    service = build_semantic_memory_service(memory_path=temporary_root / "canonical.sqlite3",
        vector_path=temporary_root / "vector.sqlite3", embedding_provider=FakeEmbeddingProvider())
    fixture = json.loads((ROOT / "evaluation/fixtures/memory_cases.json").read_text())
    subject = fixture["subject"]
    common = dict(subject_id=subject, memory_type=MemoryType.CAREER_PREFERENCE,
                  source_type=EvidenceSourceType.SYSTEM_FIXTURE)
    query = fixture["query"]
    active = service.create_confirmed(**common, content=fixture["active_content"], confirmed_by_user=True,
                                      memory_id="memory_eval_active")
    excluded = None
    if scenario_id == "MEM_001":
        excluded = service.create_candidate(**common, content=query, memory_id="memory_eval_candidate")
    elif scenario_id == "MEM_002":
        excluded = service.create_confirmed(**common, content=query, confirmed_by_user=True, memory_id="memory_eval_old")
        service.supersede(subject, excluded.memory_id, content=fixture["replacement_content"], source_type=EvidenceSourceType.SYSTEM_FIXTURE,
                          confirmed_by_user=True, new_memory_id="memory_eval_new")
    elif scenario_id == "MEM_003":
        excluded = service.create_confirmed(**common, content=query, confirmed_by_user=True, memory_id="memory_eval_archived")
        service.archive(subject, excluded.memory_id)
    elif scenario_id == "MEM_004":
        excluded = service.create_confirmed(**{**common, "subject_id": fixture["other_subject"]},
            content=query, confirmed_by_user=True, memory_id="memory_eval_other_subject")
    before = memory_snapshot(service, subject)
    context = service.retrieve_context(subject, query, top_k=8)
    refs = [item.memory_id for item in context.items]
    return dict(active_present=active.memory_id in refs,
        excluded_absent=excluded is None or excluded.memory_id not in refs,
        memory_read_only=before == memory_snapshot(service, subject),
        memory_provenance=memory_rows(service, subject, refs))


def guide(controller, *, unknown=False):
    fixture = json.loads((ROOT / "evaluation/fixtures/guided_answers.json").read_text())
    answers = fixture["unknown" if unknown else "application"]
    while not controller.conversation.ready_for_profile_review:
        stage = controller.conversation.stage
        controller.submit_conversation_answer(stage, answers[stage.value])


def custom_graph(controller, *, sparse=False):
    inputs = load_input(sparse=sparse)
    sd = SelfDiscoveryAgent(MockCourseDataProvider(), FakeLLMProvider(application_extraction(sparse=sparse)))
    preview = sd.discover(inputs, []).user_profile.confirm()
    records = [analyze_job(job_by_id(job_id)) for job_id in ("job_001", "job_007", "job_013")]
    match = MatchInsightAgent(FakeLLMProvider(None, predefined_responses=[
        public_offline_match_extraction(MatchContextBuilder().build(preview, record)) for record in records]))
    deps = replace(controller.dependencies,
        self_discovery_agent=SelfDiscoveryAgent(MockCourseDataProvider(), FakeLLMProvider(application_extraction(sparse=sparse))),
        match_insight_agent=match, self_discovery_input=inputs)
    controller.dependencies = deps
    controller.runner = OrangeGraphRunner(build_orange_graph(dependencies=deps, checkpointer=controller.checkpointer))


def controller_case(scenario_id):
    controller = DemoController()
    try:
        if scenario_id == "CONV_001":
            guide(controller, unknown=True)
            view = controller.career_profile_view()
            labels = [item.label for item in view.evidence_needs if item.authority == AUTHORITY_UNKNOWN]
            return dict(conversation_unknowns=["project_evidence" for label in labels if "项目" in label] +
                        ["work_style" for label in labels if "工作" in label],
                bounded_choices=all(1 <= len(question.options) <= 8 for question in QUESTIONS.values()),
                conversation_calls=controller.dependencies.self_discovery_agent.llm_provider.call_count)
        custom = scenario_id in {"E2E_001", "E2E_004"}
        if custom:
            custom_graph(controller, sparse=scenario_id == "E2E_004")
        guided_gate = False
        try:
            controller.prepare_profile_review()
        except DemoWorkflowError:
            guided_gate = controller.state is None
        guide(controller, unknown=scenario_id == "E2E_004")
        draft = controller.prepare_profile_review()
        before_workflow = draft["workflow_id"]
        roles_hidden = not draft.get("match_results") and not draft.get("job_intelligence") and not draft["profile"]["confirmed"]
        state = controller.confirm_profile()
        profile = controller.confirmed_profile()
        observation = dict(guided_gate=guided_gate, roles_hidden=roles_hidden,
            same_thread_resume=state["workflow_id"] == before_workflow,
            self_discovery_calls=state["self_discovery_call_count"], completed=state["workflow_status"] == "completed",
            confirmed_profile_gate=roles_hidden and state["profile"]["confirmed"] and profile.confirmed)
        if custom:
            result = controller.match_for("job_007")
            context = MatchContextBuilder().build(profile, controller.intelligence_for("job_007"))
            observation.update(match_observation(result, context, profile))
            uncertainties = [ProfileUncertainty.model_validate(item) for item in state["profile_uncertainties"]]
            observation.update(profile_observation(profile, uncertainties))
            observation["sparse_relations_safe"] = all(row["relation"] in {"unknown", "evidence_missing"}
                                                       for row in observation["relations"])
            return observation
        before_match = controller.match_for("job_001").model_dump(mode="json")
        before_job = controller.intelligence_for("job_001").model_dump(mode="json")
        service, subject = controller.memory_service, controller.subject_id
        if scenario_id == "ACT_002":
            before_memory = memory_snapshot(service, subject)
            before_profile = profile.model_dump(mode="json")
            action_id = controller.match_for("job_001").action_items[0].action_id
            controller.mark_action_already_done(action_id)
            observation.update(already_done_review=action_id in controller.actions_needing_evidence_review,
                profile_unchanged=before_profile == controller.confirmed_profile().model_dump(mode="json"),
                memory_unchanged=before_memory == memory_snapshot(service, subject))
        elif scenario_id in {"E2E_002", "E2E_003"}:
            context, statements = controller.role_memory_context("job_001")
            refs = [ref for statement in statements for ref in statement.memory_refs]
            observation["memory_provenance"] = memory_rows(service, subject, refs)
            before = memory_snapshot(service, subject)
            candidate = controller.submit_structured_preference(dimension="work_style.primary_focus",
                value="product_and_requirement_work", display_label="Synthetic preference: product requirements work.")
            observation["candidate_only"] = candidate is not None and before == memory_snapshot(service, subject)
            observation["newest_input_preserved"] = controller.structured_session_signals["work_style.primary_focus"].value == "product_and_requirement_work"
            if scenario_id == "E2E_002":
                controller.resolve_memory_change(candidate.candidate_id, MemoryChangeChoice.DEFER)
                observation["defer_zero_writes"] = before == memory_snapshot(service, subject)
            else:
                old_id = candidate.previous_memory_refs[0]
                controller.resolve_memory_change(candidate.candidate_id, MemoryChangeChoice.UPDATE_LONG_TERM)
                active = service.memory_store.list_active(subject)
                observation["supersession_lifecycle"] = service.memory_store.get(subject, old_id).status == MemoryStatus.SUPERSEDED and any(
                    item.metadata.get("signal_value") == "product_and_requirement_work" for item in active)
                observation["vector_replacement"] = service.vector_index.metadata_for(old_id) is None and all(
                    service.vector_index.metadata_for(item.memory_id) is not None for item in active)
                draft = controller.pending_profile_refinement.draft_profile
                observation["draft_not_current"] = not draft.confirmed and draft.version == 2 and controller.current_profile_from_memory().version == 1
                controller.confirm_pending_profile_refinement()
                observation["profile_versions"] = [item.version for item in controller.profile_history()]
                observation["separate_profile_confirmation"] = controller.current_profile_from_memory().confirmed and controller.current_profile_from_memory().version == 2
            observation.update(match_unchanged=before_match == controller.match_for("job_001").model_dump(mode="json"),
                job_unchanged=before_job == controller.intelligence_for("job_001").model_dump(mode="json"))
        return observation
    finally:
        controller.close()


def execute_scenario(scenario_id, temporary_root):
    """Closed dispatch; registry IDs never become import paths or executable text."""
    if scenario_id in {"SD_001", "SD_002", "SD_003", "SD_004"}:
        result = SelfDiscoveryAgent(MockCourseDataProvider(), FakeLLMProvider(application_extraction())).discover(load_input(), [])
        return profile_observation(result.user_profile, result.uncertainties)
    if scenario_id in {"JI_001", "JI_002"}:
        job = job_by_id("job_007")
        if scenario_id == "JI_002":
            job = job.model_copy(update={"description": "Synthetic incomplete application role.",
                "responsibilities": ["Implement a small Python service"], "requirements": ["Basic Python implementation"],
                "technology_tags": ["Python"], "preferred_qualifications": []})
        return job_observation(analyze_job(job), job)
    if scenario_id == "JI_003":
        observations = []
        retrieval_zero = []
        for preference in ("hands_on_implementation", "product_and_requirement_work"):
            controller = DemoController()
            try:
                controller.memory_service.supersede(controller.subject_id, "memory_demo_hands_on_preference",
                    content=f"Synthetic confirmed work-style preference: {preference}",
                    source_type=EvidenceSourceType.SYSTEM_FIXTURE, confirmed_by_user=True,
                    metadata={"signal_dimension": "work_style.primary_focus", "signal_value": preference, "signal_version": 1})
                controller.submit_structured_preference(dimension="work_style.primary_focus", value=preference,
                                                        display_label="Synthetic preference variant")
                controller.start()
                controller.confirm_profile()
                record = controller.intelligence_for("job_001").model_dump(mode="json")
                record.pop("analysis_metadata", None)
                observations.append(record)
                retrieval_zero.append(not controller.memory_context_coordinator.events)
            finally:
                controller.close()
        return dict(job_facts_independent=observations[0] == observations[1], job_memory_retrieval_zero=all(retrieval_zero))
    if scenario_id in {"MI_001", "MI_002", "MI_003", "MI_004", "MI_005", "MI_006", "ACT_001", "ACT_003"}:
        return match_case(scenario_id)
    if scenario_id in {"MEM_001", "MEM_002", "MEM_003", "MEM_004", "MEM_005"}:
        return memory_case(scenario_id, temporary_root)
    if scenario_id in {"CONV_001", "CONV_002", "ACT_002", "E2E_001", "E2E_002", "E2E_003", "E2E_004"}:
        return controller_case(scenario_id)
    raise ValueError("Scenario has no allowlisted production adapter")
