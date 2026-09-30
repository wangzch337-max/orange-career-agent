"""Thin public-Demo runtime adapter over the validated Orange graph."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Mapping

from data.models import (
    CareerReport,
    JobIntelligenceRecord,
    JobRecord,
    MatchResult,
    UserProfile,
)
from memory.models import MemoryRecord, new_subject_id
from memory.service import MemoryService, build_sqlite_memory_service
from providers.fake import FakeLLMProvider
from workflows.langgraph_checkpoint import create_memory_checkpointer
from workflows.langgraph_runtime import (
    DEFAULT_SELECTED_JOB_IDS,
    build_public_offline_dependencies,
    load_public_self_discovery_input,
)
from workflows.langgraph_state import (
    GraphWorkflowStatus,
    OrangeGraphState,
    ProfileReviewAction,
    ProfileReviewDecision,
)
from workflows.langgraph_workflow import (
    OrangeGraphRunner,
    build_orange_graph,
    create_initial_graph_state,
    new_workflow_id,
    validate_completed_state,
)


APPROVED_ROLE_IDS = DEFAULT_SELECTED_JOB_IDS
APPROVED_ROLE_TITLES = (
    "AI Product Intern",
    "AI Application Engineer",
    "Data Analyst",
)


class DemoControllerError(RuntimeError):
    """Safe base error for the public interactive Demo adapter."""


class DemoWorkflowError(DemoControllerError):
    """Raised when the public Demo workflow is not in the required state."""


class DemoValidationError(DemoControllerError):
    """Raised when validated workflow output violates the Demo contract."""


class DemoController:
    """Own one browser-session graph, in-memory checkpoint and temporary memory DB."""

    def __init__(self) -> None:
        self.workflow_id = new_workflow_id()
        self.subject_id = new_subject_id()
        self._temporary_directory = TemporaryDirectory(prefix="orange_ui_demo_")
        memory_path = Path(self._temporary_directory.name) / "orange_demo_memory.sqlite3"
        self.memory_service = build_sqlite_memory_service(memory_path)
        dependencies = replace(
            build_public_offline_dependencies(APPROVED_ROLE_IDS),
            memory_service=self.memory_service,
        )
        providers = (
            dependencies.self_discovery_agent.llm_provider,
            dependencies.job_intelligence_agent.llm_provider,
            dependencies.match_insight_agent.llm_provider,
        )
        if not all(isinstance(provider, FakeLLMProvider) for provider in providers):
            raise DemoValidationError("Public Demo requires offline fake providers.")
        self.dependencies = dependencies
        self.checkpointer = create_memory_checkpointer()
        self.runner = OrangeGraphRunner(
            build_orange_graph(
                dependencies=dependencies,
                checkpointer=self.checkpointer,
            )
        )
        self._state: OrangeGraphState | None = None

    @property
    def state(self) -> OrangeGraphState | None:
        return self._state

    @property
    def public_persona(self) -> dict[str, object]:
        return load_public_self_discovery_input()

    def start(self) -> OrangeGraphState:
        """Start once; Streamlit reruns cannot restart Self-Discovery."""

        if self._state is not None:
            return self._state
        self._state = self.runner.start(
            create_initial_graph_state(
                selected_job_ids=APPROVED_ROLE_IDS,
                checkpoint_mode="memory",
                workflow_id=self.workflow_id,
                subject_id=self.subject_id,
            )
        )
        if self._state["workflow_status"] not in {
            GraphWorkflowStatus.WAITING_FOR_HUMAN.value,
            GraphWorkflowStatus.FAILED.value,
        }:
            raise DemoWorkflowError("Public Demo did not reach the profile review gate.")
        return self._state

    def profile_review_payload(self) -> dict[str, object]:
        state = self._require_state(GraphWorkflowStatus.WAITING_FOR_HUMAN)
        interrupts = state.get("__interrupt__", [])
        if not interrupts:
            raise DemoWorkflowError("Profile review interrupt is unavailable.")
        payload = interrupts[0].value
        if not isinstance(payload, Mapping) or payload.get("kind") != "profile_review":
            raise DemoValidationError("Profile review payload is invalid.")
        return dict(payload)

    def confirm_profile(self) -> OrangeGraphState:
        """Resume the same real LangGraph thread with the domain confirm contract."""

        self._require_state(GraphWorkflowStatus.WAITING_FOR_HUMAN)
        before_count = self.dependencies.self_discovery_agent.llm_provider.call_count
        self._state = self.runner.resume(
            self.workflow_id,
            ProfileReviewDecision(action=ProfileReviewAction.CONFIRM),
        )
        if self._state["workflow_id"] != self.workflow_id:
            raise DemoValidationError("Workflow identity changed during resume.")
        if (
            self._state["self_discovery_call_count"] != 1
            or self.dependencies.self_discovery_agent.llm_provider.call_count
            != before_count
        ):
            raise DemoValidationError("Self-Discovery reran during profile resume.")
        if self._state["workflow_status"] == GraphWorkflowStatus.COMPLETED.value:
            self._validate_completed_roles()
        return self._state

    def confirmed_profile(self) -> UserProfile:
        state = self._require_state(GraphWorkflowStatus.COMPLETED)
        return UserProfile.model_validate(state["profile"])

    def report(self) -> CareerReport:
        return validate_completed_state(self._require_state(GraphWorkflowStatus.COMPLETED))

    def job_records(self) -> list[JobRecord]:
        state = self._require_state(GraphWorkflowStatus.COMPLETED)
        return [JobRecord.model_validate(item) for item in state["job_records"]]

    def job_intelligence(self) -> list[JobIntelligenceRecord]:
        state = self._require_state(GraphWorkflowStatus.COMPLETED)
        return [
            JobIntelligenceRecord.model_validate(item)
            for item in state["job_intelligence"]
        ]

    def match_results(self) -> list[MatchResult]:
        state = self._require_state(GraphWorkflowStatus.COMPLETED)
        return [MatchResult.model_validate(item) for item in state["match_results"]]

    def job_record(self, job_id: str) -> JobRecord:
        return self._select(job_id, self.job_records())

    def intelligence_for(self, job_id: str) -> JobIntelligenceRecord:
        return self._select(job_id, self.job_intelligence())

    def match_for(self, job_id: str) -> MatchResult:
        return self._select(job_id, self.match_results())

    def current_profile_from_memory(self) -> UserProfile | None:
        return self.memory_service.get_current_confirmed_profile(self.subject_id)

    def active_memories(self) -> list[MemoryRecord]:
        return self.memory_service.memory_store.list_active(self.subject_id)

    def profile_history(self) -> list[UserProfile]:
        return self.memory_service.profile_store.list_profile_history(self.subject_id)

    def safe_trace(self) -> list[dict[str, object]]:
        if self._state is None:
            return []
        return [
            {
                "event_type": event["event_type"],
                "node": event.get("node_name"),
                "status": event.get("safe_metadata", {}).get("workflow_status"),
                "profile_version": event.get("safe_metadata", {}).get(
                    "profile_version"
                ),
                "checkpoint_mode": event.get("safe_metadata", {}).get(
                    "checkpoint_mode"
                ),
                "count": event.get("safe_metadata", {}).get(
                    "match_result_count",
                    event.get("safe_metadata", {}).get("job_intelligence_count"),
                ),
            }
            for event in self._state.get("graph_events", [])
        ]

    def close(self) -> None:
        self._temporary_directory.cleanup()

    def _require_state(self, expected: GraphWorkflowStatus) -> OrangeGraphState:
        if self._state is None or self._state["workflow_status"] != expected.value:
            raise DemoWorkflowError(
                f"Public Demo workflow is not in the required {expected.value} state."
            )
        return self._state

    def _validate_completed_roles(self) -> None:
        titles = tuple(item.role_title for item in self.job_intelligence())
        if titles != APPROVED_ROLE_TITLES:
            raise DemoValidationError("Public Demo role set or order changed.")
        if len(self.match_results()) != len(APPROVED_ROLE_IDS):
            raise DemoValidationError("Public Demo Match output is incomplete.")
        self.report()

    @staticmethod
    def _select(job_id: str, records):
        for record in records:
            if record.job_id == job_id:
                return record
        raise DemoValidationError("Requested role is not part of the public Demo.")
