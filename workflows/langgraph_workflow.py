"""LangGraph orchestration over Orange's existing domain Agents."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import JsonValue, ValidationError

from agents.job_intelligence import JobIntelligenceAgent
from agents.match_insight import MatchInsightAgent
from agents.self_discovery import SelfDiscoveryAgent
from data.models import (
    CareerReport,
    ClarificationQuestion,
    EventType,
    GraphEvent,
    JobIntelligenceRecord,
    JobRecord,
    MatchResult,
    ProfileUncertainty,
    UserProfile,
)
from providers.errors import LLMError, LLMStructuredOutputError
from memory.models import new_subject_id
from memory.service import MemoryService
from tools.report import DeterministicReportBuilder
from workflows.langgraph_state import (
    GraphErrorCategory,
    GraphWorkflowStatus,
    OrangeGraphState,
    ProfileReviewAction,
    ProfileReviewDecision,
    SafeGraphError,
    UnknownWorkflowError,
)
from workflows.stages import ProfileNotConfirmedError, WorkflowError


@dataclass(frozen=True)
class OrangeGraphDependencies:
    """Runtime-only dependencies; none of these objects enter checkpoint state."""

    self_discovery_agent: SelfDiscoveryAgent
    job_intelligence_agent: JobIntelligenceAgent
    match_insight_agent: MatchInsightAgent
    report_builder: DeterministicReportBuilder
    self_discovery_input: Mapping[str, object]
    memory_service: MemoryService | None = None


def new_workflow_id() -> str:
    return f"orange_{uuid4().hex}"


def _event(
    state: OrangeGraphState,
    event_type: EventType,
    summary: str,
    *,
    node_name: str | None = None,
    metadata: Mapping[str, JsonValue] | None = None,
    duration_ms: int | None = None,
) -> dict[str, JsonValue]:
    sequence = len(state.get("graph_events", [])) + 1
    item = GraphEvent(
        event_id=f"{state['workflow_id']}_graph_{sequence:04d}",
        event_type=event_type,
        component="LangGraphOrchestrator",
        summary=summary,
        safe_metadata=dict(metadata or {}),
        duration_ms=duration_ms,
        workflow_id=state["workflow_id"],
        node_name=node_name,
    )
    return item.model_dump(mode="json")


def _append_events(
    state: OrangeGraphState,
    *events: dict[str, JsonValue],
) -> list[dict[str, JsonValue]]:
    return [*state.get("graph_events", []), *events]


def _failure_update(
    state: OrangeGraphState,
    *,
    node_name: str,
    exc: Exception,
) -> dict[str, object]:
    if isinstance(exc, LLMStructuredOutputError):
        category = GraphErrorCategory.VALIDATION_FAILURE
        message = "Structured provider output failed deterministic validation."
        retryable = False
    elif isinstance(exc, LLMError):
        category = GraphErrorCategory.PROVIDER_FAILURE
        message = "The configured provider failed within its existing retry policy."
        retryable = exc.retryable
    elif isinstance(exc, (ValidationError, WorkflowError, ValueError, KeyError)):
        category = GraphErrorCategory.VALIDATION_FAILURE
        message = "Workflow data failed a deterministic validation rule."
        retryable = False
    else:
        category = GraphErrorCategory.UNEXPECTED_FAILURE
        message = "An unexpected non-recoverable workflow error occurred."
        retryable = False
    error = SafeGraphError(
        category=category,
        node_name=node_name,
        message=message,
        retryable=retryable,
    )
    failed = _event(
        state,
        EventType.GRAPH_FAILED,
        "Graph execution entered a safe failed state.",
        node_name=node_name,
        metadata={
            "workflow_status": GraphWorkflowStatus.FAILED.value,
            "error_category": category.value,
        },
    )
    return {
        "workflow_status": GraphWorkflowStatus.FAILED.value,
        "safe_error": error.model_dump(mode="json"),
        "graph_events": _append_events(state, failed),
    }


def _safe_profile_summary(state: OrangeGraphState) -> dict[str, object]:
    profile = UserProfile.model_validate(state["profile"])
    uncertainties = [
        ProfileUncertainty.model_validate(item)
        for item in state.get("profile_uncertainties", [])
    ]
    questions = [
        ClarificationQuestion.model_validate(item)
        for item in state.get("clarification_questions", [])
    ]
    return {
        "kind": "profile_review",
        "workflow_id": state["workflow_id"],
        "profile": {
            "profile_id": profile.profile_id,
            "version": profile.version,
            "confirmed": profile.confirmed,
            "skills": [item.label for item in profile.skills],
            "interests": [item.label for item in profile.interests],
            "values": [item.label for item in profile.values],
            "goals": [
                {"label": item.label, "goal_type": item.goal_type.value}
                for item in profile.goals
            ],
            "strengths": [item.text for item in profile.strengths],
            "development_areas": [item.text for item in profile.development_areas],
            "career_preferences": [item.label for item in profile.career_preferences],
            "uncertainties": [item.topic for item in uncertainties],
            "clarification_questions": [item.question for item in questions],
        },
    }


def create_initial_graph_state(
    *,
    selected_job_ids: Sequence[str],
    checkpoint_mode: str,
    workflow_id: str | None = None,
    subject_id: str | None = None,
) -> OrangeGraphState:
    if not selected_job_ids:
        raise ValueError("At least one selected job ID is required.")
    if len(selected_job_ids) != len(set(selected_job_ids)):
        raise ValueError("Selected job IDs must be unique.")
    identifier = workflow_id or new_workflow_id()
    state: OrangeGraphState = {
        "workflow_id": identifier,
        "subject_id": subject_id or new_subject_id(),
        "workflow_status": GraphWorkflowStatus.RUNNING.value,
        "checkpoint_mode": checkpoint_mode,
        "selected_job_ids": list(selected_job_ids),
        "profile": None,
        "current_profile_ref": None,
        "profile_uncertainties": [],
        "clarification_questions": [],
        "self_discovery_metadata": {},
        "job_records": [],
        "job_intelligence": [],
        "match_results": [],
        "report": None,
        "graph_events": [],
        "safe_error": None,
        "review_outcome": None,
        "self_discovery_call_count": 0,
    }
    started = _event(
        state,
        EventType.GRAPH_RUN_STARTED,
        "Orange graph run started.",
        metadata={
            "workflow_status": GraphWorkflowStatus.RUNNING.value,
            "selected_job_count": len(selected_job_ids),
            "checkpoint_mode": checkpoint_mode,
        },
    )
    state["graph_events"] = [started]
    return state


def build_orange_graph(
    *,
    dependencies: OrangeGraphDependencies,
    checkpointer: Any,
) -> Any:
    """Build deterministic graph edges around injected domain components."""

    def self_discovery_node(state: OrangeGraphState) -> dict[str, object]:
        node_name = "self_discovery"
        started_at = perf_counter()
        started = _event(
            state,
            EventType.GRAPH_NODE_STARTED,
            "Self-Discovery node started.",
            node_name=node_name,
            metadata={"workflow_status": GraphWorkflowStatus.RUNNING.value},
        )
        working_state = dict(state)
        working_state["graph_events"] = _append_events(state, started)
        try:
            courses = dependencies.self_discovery_agent.course_provider.load()
            result = dependencies.self_discovery_agent.discover(
                dict(dependencies.self_discovery_input), courses
            )
            duration_ms = max(0, round((perf_counter() - started_at) * 1000))
            completed = _event(
                working_state,
                EventType.GRAPH_NODE_COMPLETED,
                "Self-Discovery node completed through the existing Agent.",
                node_name=node_name,
                metadata={"profile_version": result.user_profile.version},
                duration_ms=duration_ms,
            )
            interrupted = _event(
                {**working_state, "graph_events": _append_events(working_state, completed)},
                EventType.GRAPH_INTERRUPTED,
                "Workflow is waiting for explicit profile review.",
                node_name="profile_review_gate",
                metadata={
                    "workflow_status": GraphWorkflowStatus.WAITING_FOR_HUMAN.value,
                    "profile_version": result.user_profile.version,
                },
            )
            checkpoint = _event(
                {
                    **working_state,
                    "graph_events": _append_events(working_state, completed, interrupted),
                },
                EventType.CHECKPOINT_CREATED,
                "Profile-review checkpoint created.",
                node_name="profile_review_gate",
                metadata={"checkpoint_mode": state["checkpoint_mode"]},
            )
            return {
                "workflow_status": GraphWorkflowStatus.WAITING_FOR_HUMAN.value,
                "profile": result.user_profile.model_dump(mode="json"),
                "profile_uncertainties": [
                    item.model_dump(mode="json") for item in result.uncertainties
                ],
                "clarification_questions": [
                    item.model_dump(mode="json")
                    for item in result.clarification_questions
                ],
                "self_discovery_metadata": dict(result.extraction_metadata),
                "self_discovery_call_count": state["self_discovery_call_count"] + 1,
                "review_outcome": None,
                "safe_error": None,
                "graph_events": _append_events(
                    working_state, completed, interrupted, checkpoint
                ),
            }
        except Exception as exc:
            return _failure_update(working_state, node_name=node_name, exc=exc)

    def profile_review_gate(state: OrangeGraphState) -> dict[str, object]:
        node_name = "profile_review_gate"
        decision_value = interrupt(
            _safe_profile_summary(state),
            response_schema=ProfileReviewDecision,
        )
        try:
            decision = (
                decision_value
                if isinstance(decision_value, ProfileReviewDecision)
                else ProfileReviewDecision.model_validate(decision_value)
            )
            profile = UserProfile.model_validate(state["profile"])
            resumed = _event(
                state,
                EventType.GRAPH_RESUMED,
                "Profile-review checkpoint resumed.",
                node_name=node_name,
                metadata={"decision": decision.action.value},
            )
            checkpoint = _event(
                {**state, "graph_events": _append_events(state, resumed)},
                EventType.CHECKPOINT_RESUMED,
                "Workflow resumed from the existing checkpoint.",
                node_name=node_name,
                metadata={"checkpoint_mode": state["checkpoint_mode"]},
            )
            started = _event(
                {
                    **state,
                    "graph_events": _append_events(state, resumed, checkpoint),
                },
                EventType.GRAPH_NODE_STARTED,
                "Profile-review decision processing started.",
                node_name=node_name,
            )
            current_events = _append_events(state, resumed, checkpoint, started)
            current_state = {**state, "graph_events": current_events}
            if decision.action == ProfileReviewAction.CONFIRM:
                active_profile = profile.confirm()
                profile_reference = state.get("current_profile_ref")
                if dependencies.memory_service is not None:
                    saved = dependencies.memory_service.save_confirmed_profile(
                        state["subject_id"], active_profile
                    )
                    profile_reference = saved.reference.model_dump(mode="json")
                completed = _event(
                    current_state,
                    EventType.GRAPH_NODE_COMPLETED,
                    "Profile was explicitly confirmed through domain behavior.",
                    node_name=node_name,
                    metadata={"profile_version": active_profile.version},
                )
                return {
                    "workflow_status": GraphWorkflowStatus.RUNNING.value,
                    "profile": active_profile.model_dump(mode="json"),
                    "current_profile_ref": profile_reference,
                    "review_outcome": ProfileReviewAction.CONFIRM.value,
                    "graph_events": _append_events(current_state, completed),
                }

            active_profile = profile.create_revision(**decision.revision_changes())
            completed = _event(
                current_state,
                EventType.GRAPH_NODE_COMPLETED,
                "An unconfirmed profile revision was created through domain behavior.",
                node_name=node_name,
                metadata={"profile_version": active_profile.version},
            )
            interrupted = _event(
                {**current_state, "graph_events": _append_events(current_state, completed)},
                EventType.GRAPH_INTERRUPTED,
                "Revised profile requires another explicit review.",
                node_name=node_name,
                metadata={
                    "workflow_status": GraphWorkflowStatus.WAITING_FOR_HUMAN.value,
                    "profile_version": active_profile.version,
                },
            )
            checkpoint_created = _event(
                {
                    **current_state,
                    "graph_events": _append_events(current_state, completed, interrupted),
                },
                EventType.CHECKPOINT_CREATED,
                "Revised profile-review checkpoint created.",
                node_name=node_name,
                metadata={"checkpoint_mode": state["checkpoint_mode"]},
            )
            return {
                "workflow_status": GraphWorkflowStatus.WAITING_FOR_HUMAN.value,
                "profile": active_profile.model_dump(mode="json"),
                "review_outcome": ProfileReviewAction.REVISE.value,
                "graph_events": _append_events(
                    current_state, completed, interrupted, checkpoint_created
                ),
            }
        except Exception as exc:
            return _failure_update(state, node_name=node_name, exc=exc)

    def job_intelligence_node(state: OrangeGraphState) -> dict[str, object]:
        node_name = "job_intelligence"
        started_at = perf_counter()
        started = _event(
            state,
            EventType.GRAPH_NODE_STARTED,
            "Job Intelligence node started.",
            node_name=node_name,
        )
        working_state = {**state, "graph_events": _append_events(state, started)}
        try:
            profile = UserProfile.model_validate(state["profile"])
            if not profile.confirmed:
                raise ProfileNotConfirmedError(
                    "Profile confirmation is required before Job Intelligence."
                )
            jobs_by_id = {
                item.job_id: item
                for item in dependencies.job_intelligence_agent.job_provider.load()
            }
            selected_jobs = [jobs_by_id[job_id] for job_id in state["selected_job_ids"]]
            intelligence = [
                dependencies.job_intelligence_agent.analyze(job)
                for job in selected_jobs
            ]
            completed = _event(
                working_state,
                EventType.GRAPH_NODE_COMPLETED,
                "Job Intelligence node completed through the existing Agent.",
                node_name=node_name,
                metadata={"job_intelligence_count": len(intelligence)},
                duration_ms=max(0, round((perf_counter() - started_at) * 1000)),
            )
            return {
                "job_records": [item.model_dump(mode="json") for item in selected_jobs],
                "job_intelligence": [
                    item.model_dump(mode="json") for item in intelligence
                ],
                "graph_events": _append_events(working_state, completed),
            }
        except Exception as exc:
            return _failure_update(working_state, node_name=node_name, exc=exc)

    def match_insight_node(state: OrangeGraphState) -> dict[str, object]:
        node_name = "match_insight"
        started_at = perf_counter()
        started = _event(
            state,
            EventType.GRAPH_NODE_STARTED,
            "Match & Insight node started.",
            node_name=node_name,
        )
        working_state = {**state, "graph_events": _append_events(state, started)}
        try:
            profile = UserProfile.model_validate(state["profile"])
            intelligence = [
                JobIntelligenceRecord.model_validate(item)
                for item in state["job_intelligence"]
            ]
            results = [
                dependencies.match_insight_agent.analyze(profile, item)
                for item in intelligence
            ]
            completed = _event(
                working_state,
                EventType.GRAPH_NODE_COMPLETED,
                "Match & Insight node completed through the existing Agent.",
                node_name=node_name,
                metadata={"match_result_count": len(results)},
                duration_ms=max(0, round((perf_counter() - started_at) * 1000)),
            )
            return {
                "match_results": [item.model_dump(mode="json") for item in results],
                "graph_events": _append_events(working_state, completed),
            }
        except Exception as exc:
            return _failure_update(working_state, node_name=node_name, exc=exc)

    def report_node(state: OrangeGraphState) -> dict[str, object]:
        node_name = "report"
        started_at = perf_counter()
        started = _event(
            state,
            EventType.GRAPH_NODE_STARTED,
            "Deterministic report node started.",
            node_name=node_name,
        )
        working_state = {**state, "graph_events": _append_events(state, started)}
        try:
            profile = UserProfile.model_validate(state["profile"])
            intelligence = [
                JobIntelligenceRecord.model_validate(item)
                for item in state["job_intelligence"]
            ]
            matches = [MatchResult.model_validate(item) for item in state["match_results"]]
            report = dependencies.report_builder.build(
                state["workflow_id"], profile, intelligence, matches
            )
            completed = _event(
                working_state,
                EventType.GRAPH_NODE_COMPLETED,
                "Deterministic report node completed.",
                node_name=node_name,
                metadata={"report_status": "created"},
                duration_ms=max(0, round((perf_counter() - started_at) * 1000)),
            )
            graph_completed = _event(
                {**working_state, "graph_events": _append_events(working_state, completed)},
                EventType.GRAPH_COMPLETED,
                "Orange graph run completed.",
                node_name=node_name,
                metadata={
                    "workflow_status": GraphWorkflowStatus.COMPLETED.value,
                    "match_result_count": len(matches),
                },
            )
            return {
                "workflow_status": GraphWorkflowStatus.COMPLETED.value,
                "report": report.model_dump(mode="json"),
                "graph_events": _append_events(
                    working_state, completed, graph_completed
                ),
            }
        except Exception as exc:
            return _failure_update(working_state, node_name=node_name, exc=exc)

    def route_after_self_discovery(state: OrangeGraphState) -> str:
        return "end" if state["workflow_status"] == GraphWorkflowStatus.FAILED.value else "review"

    def route_after_review(state: OrangeGraphState) -> str:
        if state["workflow_status"] == GraphWorkflowStatus.FAILED.value:
            return "end"
        if state["review_outcome"] == ProfileReviewAction.REVISE.value:
            return "review"
        return "jobs"

    def route_after_domain_node(state: OrangeGraphState) -> str:
        return "end" if state["workflow_status"] == GraphWorkflowStatus.FAILED.value else "continue"

    builder = StateGraph(OrangeGraphState)
    builder.add_node("self_discovery", self_discovery_node)
    builder.add_node("profile_review_gate", profile_review_gate)
    builder.add_node("job_intelligence", job_intelligence_node)
    builder.add_node("match_insight", match_insight_node)
    builder.add_node("report", report_node)
    builder.add_edge(START, "self_discovery")
    builder.add_conditional_edges(
        "self_discovery",
        route_after_self_discovery,
        {"review": "profile_review_gate", "end": END},
    )
    builder.add_conditional_edges(
        "profile_review_gate",
        route_after_review,
        {"review": "profile_review_gate", "jobs": "job_intelligence", "end": END},
    )
    builder.add_conditional_edges(
        "job_intelligence",
        route_after_domain_node,
        {"continue": "match_insight", "end": END},
    )
    builder.add_conditional_edges(
        "match_insight",
        route_after_domain_node,
        {"continue": "report", "end": END},
    )
    builder.add_edge("report", END)
    return builder.compile(checkpointer=checkpointer, name="orange_phase_6")


class OrangeGraphRunner:
    """Small runner that enforces stable thread identity on start and resume."""

    def __init__(self, graph: Any) -> None:
        self.graph = graph

    @staticmethod
    def _config(workflow_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": workflow_id}}

    def start(self, initial_state: OrangeGraphState) -> OrangeGraphState:
        return self.graph.invoke(
            initial_state,
            config=self._config(initial_state["workflow_id"]),
        )

    def resume(
        self,
        workflow_id: str,
        decision: ProfileReviewDecision | Mapping[str, object],
    ) -> OrangeGraphState:
        config = self._config(workflow_id)
        snapshot = self.graph.get_state(config)
        values = snapshot.values
        if not values or values.get("workflow_id") != workflow_id:
            raise UnknownWorkflowError("No checkpoint exists for this workflow ID.")
        if values.get("workflow_status") != GraphWorkflowStatus.WAITING_FOR_HUMAN.value:
            raise UnknownWorkflowError("Workflow is not waiting for a human decision.")
        if not snapshot.interrupts:
            raise UnknownWorkflowError("Workflow has no resumable profile-review interrupt.")
        validated = (
            decision
            if isinstance(decision, ProfileReviewDecision)
            else ProfileReviewDecision.model_validate(decision)
        )
        return self.graph.invoke(Command(resume=validated), config=config)

    def state(self, workflow_id: str) -> OrangeGraphState:
        snapshot = self.graph.get_state(self._config(workflow_id))
        if not snapshot.values:
            raise UnknownWorkflowError("No checkpoint exists for this workflow ID.")
        return snapshot.values


def validate_completed_state(state: OrangeGraphState) -> CareerReport:
    if state["workflow_status"] != GraphWorkflowStatus.COMPLETED.value:
        raise ValueError("Graph state is not completed.")
    return CareerReport.model_validate(state["report"])
