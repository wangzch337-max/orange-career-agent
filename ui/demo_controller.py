"""Thin public-Demo runtime adapter over the validated Orange graph."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Mapping

from data.models import (
    CareerReport,
    EvidenceSourceType,
    JobIntelligenceRecord,
    JobRecord,
    MatchResult,
    UserProfile,
)
from memory.embeddings import FakeEmbeddingProvider
from memory.integration import (
    MemoryChangeDetector,
    MemoryChangeService,
    MemoryContextCoordinator,
    ProfileRefinementService,
    RoleMemoryContextService,
)
from memory.models import (
    MemoryAwareStatement,
    MemoryChangeCandidate,
    MemoryChangeChoice,
    MemoryContext,
    MemoryRecord,
    MemoryType,
    ProfileRefinementResult,
    StructuredSessionSignal,
    new_subject_id,
)
from memory.service import MemoryService, build_semantic_memory_service
from providers.fake import FakeLLMProvider
from ui.conversation import ConversationStage, GuidedConversation
from observability.collector import DiagnosticEventCollector
from observability.models import DiagnosticComponent as DC, ObservabilityContext, run_id
from observability.instrumentation import session_operation
from observability.diagnostics import snapshot
from ui.presentation import (
    ACTION_STATUS_OPTIONS,
    ROLE_CLARIFICATION_OPTIONS,
    ROLE_CLARIFICATION_PROMPTS,
    CareerProfileView,
    ExplorationMapView,
    ROLE_ONE_LINE,
    career_profile_view,
)
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

PROFILE_CALIBRATION_OPTIONS = ("基本准确", "我想修改", "我还不确定")
ROLE_EXPLORATION_OPTIONS = ("继续探索", "暂时不考虑")
ROLE_DEPRIORITIZATION_REASONS = (
    "工作内容不感兴趣",
    "技术方向不是我现在想发展的",
    "工作方式不太喜欢",
    "只是目前优先级较低",
    "还说不清楚",
)


class DemoControllerError(RuntimeError):
    """Safe base error for the public interactive Demo adapter."""


class DemoWorkflowError(DemoControllerError):
    """Raised when the public Demo workflow is not in the required state."""


class DemoValidationError(DemoControllerError):
    """Raised when validated workflow output violates the Demo contract."""


class DemoController:
    """Own one browser-session graph, in-memory checkpoint and temporary memory DB."""

    def __init__(self, *, diagnostics_enabled: bool = True) -> None:
        self.workflow_id = new_workflow_id()
        self.subject_id = new_subject_id()
        self.diagnostics_enabled = diagnostics_enabled
        self.diagnostic_collector = DiagnosticEventCollector()
        self.diagnostic_context = ObservabilityContext(run_id=run_id(), workflow_id=self.workflow_id,
                                                       thread_id=self.workflow_id, subject_id=self.subject_id)
        self._temporary_directory = TemporaryDirectory(prefix="orange_ui_demo_")
        memory_path = Path(self._temporary_directory.name) / "orange_demo_memory.sqlite3"
        vector_path = Path(self._temporary_directory.name) / "orange_demo_vectors.sqlite3"
        self.memory_service = build_semantic_memory_service(
            memory_path=memory_path,
            vector_path=vector_path,
            embedding_provider=FakeEmbeddingProvider(),
        )
        self.memory_context_coordinator = MemoryContextCoordinator(self.memory_service)
        self.role_memory_service = RoleMemoryContextService(
            self.memory_service, self.memory_context_coordinator
        )
        self.profile_refinement_service = ProfileRefinementService(
            self.memory_service, self.memory_context_coordinator
        )
        self.memory_change_detector = MemoryChangeDetector(self.memory_service)
        self.memory_change_service = MemoryChangeService(self.memory_service)
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
        self.conversation = GuidedConversation()
        self.profile_calibration: dict[str, str] = {}
        self.role_clarifications: dict[str, str] = {}
        self.saved_feedback_memory_ids: dict[str, str] = {}
        self.role_exploration: dict[str, str] = {}
        self.role_deprioritization_reasons: dict[str, str] = {}
        self.action_statuses: dict[str, str] = {}
        self.actions_needing_evidence_review: set[str] = set()
        self.structured_session_signals: dict[str, StructuredSessionSignal] = {}
        self.memory_change_candidates: dict[str, MemoryChangeCandidate] = {}
        self.role_memory_contexts: dict[str, MemoryContext] = {}
        self.role_memory_statements: dict[str, tuple[MemoryAwareStatement, ...]] = {}
        self.pending_profile_refinement: ProfileRefinementResult | None = None
        self._seed_public_memory_scenario()

    @property
    def state(self) -> OrangeGraphState | None:
        return self._state

    @property
    def public_persona(self) -> dict[str, object]:
        return load_public_self_discovery_input()

    @session_operation(DC.WORKFLOW, "workflow_start")
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

    @session_operation(DC.CONVERSATION, "guided_answer")
    def submit_conversation_answer(
        self,
        stage: ConversationStage,
        answer: str | tuple[str, ...] | list[str],
        *,
        note: str = "",
    ) -> ConversationStage:
        """Advance the deterministic product conversation without invoking an LLM."""

        return self.conversation.submit(stage, answer, note=note)

    def prepare_profile_review(self) -> OrangeGraphState:
        """Start the real graph only after the guided discovery conversation."""

        if not self.conversation.ready_for_profile_review:
            raise DemoWorkflowError("Guided conversation is not ready for profile review.")
        return self.start()

    def career_profile_view(self) -> CareerProfileView:
        payload: dict[str, object] | None = None
        if self._state is not None and self._state.get("profile"):
            profile = UserProfile.model_validate(self._state["profile"])
            payload = {
                "skills": [item.label for item in profile.skills],
                "strengths": [item.text for item in profile.strengths],
                "goals": [
                    {"label": item.label, "goal_type": item.goal_type.value}
                    for item in profile.goals
                ],
                "uncertainties": [
                    item.get("topic", "")
                    for item in self._state.get("profile_uncertainties", [])
                    if isinstance(item, dict) and item.get("topic")
                ],
            }
        return career_profile_view(self.conversation, payload)

    def profile_review_payload(self) -> dict[str, object]:
        state = self._require_state(GraphWorkflowStatus.WAITING_FOR_HUMAN)
        interrupts = state.get("__interrupt__", [])
        if not interrupts:
            raise DemoWorkflowError("Profile review interrupt is unavailable.")
        payload = interrupts[0].value
        if not isinstance(payload, Mapping) or payload.get("kind") != "profile_review":
            raise DemoValidationError("Profile review payload is invalid.")
        return dict(payload)

    @session_operation(DC.WORKFLOW, "workflow_resume")
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

    @session_operation(DC.WORKFLOW, "workflow_resume")
    def revise_profile_summary(self, education_summary: str) -> OrangeGraphState:
        """Use the existing Phase 6 revision contract on the same graph thread."""

        self._require_state(GraphWorkflowStatus.WAITING_FOR_HUMAN)
        before_count = self.dependencies.self_discovery_agent.llm_provider.call_count
        self._state = self.runner.resume(
            self.workflow_id,
            ProfileReviewDecision(
                action=ProfileReviewAction.REVISE,
                education_summary=education_summary,
            ),
        )
        if self._state["workflow_id"] != self.workflow_id:
            raise DemoValidationError("Workflow identity changed during revision.")
        if self.dependencies.self_discovery_agent.llm_provider.call_count != before_count:
            raise DemoValidationError("Self-Discovery reran during profile revision.")
        return self._state

    def set_profile_calibration(self, section: str, response: str) -> None:
        if not section.strip() or response not in PROFILE_CALIBRATION_OPTIONS:
            raise DemoValidationError("Invalid profile calibration response.")
        self.profile_calibration[section] = response

    def role_clarification_prompt(self, job_id: str) -> str:
        self._require_approved_role(job_id)
        return ROLE_CLARIFICATION_PROMPTS[job_id]

    def answer_role_clarification(self, job_id: str, answer: str) -> None:
        self._require_approved_role(job_id)
        if answer not in ROLE_CLARIFICATION_OPTIONS:
            raise DemoValidationError("Invalid role clarification answer.")
        self.role_clarifications[job_id] = answer

    def save_role_clarification(self, job_id: str) -> MemoryRecord:
        """Persist only an explicitly saved answer into this Demo's temporary DB."""

        self._require_approved_role(job_id)
        if job_id not in self.role_clarifications:
            raise DemoWorkflowError("Role clarification must be answered before saving.")
        existing_id = self.saved_feedback_memory_ids.get(job_id)
        if existing_id is not None:
            records = self.active_memories()
            for record in records:
                if record.memory_id == existing_id:
                    return record
        title = APPROVED_ROLE_TITLES[APPROVED_ROLE_IDS.index(job_id)]
        answer = self.role_clarifications[job_id]
        record = self.memory_service.record_user_feedback(
            self.subject_id,
            f"对于 {title} 的工作方式，用户选择：{answer}",
            confirmed_by_user=True,
            metadata={
                "demo_scope": "public_session",
                "feedback_kind": "role_clarification",
                "job_id": job_id,
            },
        )
        self.saved_feedback_memory_ids[job_id] = record.memory_id
        return record

    @session_operation(DC.ROLE_EXPLORATION, "role_recall")
    def role_memory_context(
        self, job_id: str
    ) -> tuple[MemoryContext, tuple[MemoryAwareStatement, ...]]:
        """Explicitly retrieve role context without changing role or Match objects."""

        self._require_approved_role(job_id)
        self._require_state(GraphWorkflowStatus.COMPLETED)
        title = APPROVED_ROLE_TITLES[APPROVED_ROLE_IDS.index(job_id)]
        context, statements = self.role_memory_service.recall(
            subject_id=self.subject_id,
            role_title=title,
            role_summary=ROLE_ONE_LINE[job_id],
            clarification_topic=ROLE_CLARIFICATION_PROMPTS[job_id],
        )
        self.role_memory_contexts[job_id] = context
        self.role_memory_statements[job_id] = statements
        return context, statements

    @session_operation(DC.MEMORY, "memory_change_detect")
    def submit_structured_preference(
        self,
        *,
        dimension: str,
        value: str,
        display_label: str,
    ) -> MemoryChangeCandidate | None:
        """Keep the newest explicit expression in-session and propose, never auto-save."""

        signal = StructuredSessionSignal(
            signal_id=f"session_signal_{len(self.structured_session_signals) + 1:03d}",
            dimension=dimension,
            value=value,
            display_label=display_label,
            source="explicit_user_input",
            session_order=len(self.structured_session_signals) + 1,
        )
        self.structured_session_signals[dimension] = signal
        candidate = self.memory_change_detector.detect(self.subject_id, signal)
        if candidate is not None:
            self.memory_change_candidates[candidate.candidate_id] = candidate
        return candidate

    @session_operation(DC.MEMORY, "memory_change_resolve")
    def resolve_memory_change(
        self,
        candidate_id: str,
        choice: MemoryChangeChoice,
    ) -> MemoryChangeCandidate:
        candidate = self.memory_change_candidates.get(candidate_id)
        if candidate is None:
            raise DemoValidationError("Memory change candidate is unavailable.")
        resolved, record = self.memory_change_service.resolve(candidate, choice)
        self.memory_change_candidates[candidate_id] = resolved
        if record is not None:
            self.role_memory_contexts.clear()
            self.role_memory_statements.clear()
        if record is not None and choice == MemoryChangeChoice.UPDATE_LONG_TERM:
            signal = self.structured_session_signals[candidate.dimension]
            self.pending_profile_refinement = self.profile_refinement_service.refine(
                subject_id=self.subject_id,
                current_input=signal,
            )
        return resolved

    @session_operation(DC.PROFILE_REFINEMENT, "profile_refine_confirm")
    def confirm_pending_profile_refinement(self) -> UserProfile:
        if self.pending_profile_refinement is None:
            raise DemoWorkflowError("No profile refinement is awaiting review.")
        profile = self.profile_refinement_service.confirm(
            self.subject_id,
            self.pending_profile_refinement,
            confirmed_by_user=True,
        )
        self.pending_profile_refinement = None
        return profile

    def memory_aware_match_follow_up(
        self, job_id: str
    ) -> MemoryAwareStatement | None:
        _, statements = self.role_memory_context(job_id)
        return self.role_memory_service.post_match_follow_up(
            subject_id=self.subject_id,
            statements=statements,
            match_result=self.match_for(job_id),
        )

    def set_role_exploration(
        self,
        job_id: str,
        decision: str,
        *,
        reason: str | None = None,
    ) -> None:
        self._require_approved_role(job_id)
        if decision not in ROLE_EXPLORATION_OPTIONS:
            raise DemoValidationError("Invalid role exploration decision.")
        if decision == "暂时不考虑":
            if reason not in ROLE_DEPRIORITIZATION_REASONS:
                raise DemoValidationError("A guided deprioritization reason is required.")
            self.role_deprioritization_reasons[job_id] = reason
        else:
            self.role_deprioritization_reasons.pop(job_id, None)
        self.role_exploration[job_id] = decision

    def exploration_map(self) -> ExplorationMapView:
        """Summarize explicit exploration state without score or inferred ranking."""

        continue_titles: list[str] = []
        open_titles: list[str] = []
        deprioritized_titles: list[str] = []
        questions: list[str] = []
        for job_id, title in zip(APPROVED_ROLE_IDS, APPROVED_ROLE_TITLES):
            decision = self.role_exploration.get(job_id)
            if decision == "继续探索":
                continue_titles.append(title)
            elif decision == "暂时不考虑":
                deprioritized_titles.append(title)
            else:
                open_titles.append(title)
            if job_id not in self.role_clarifications:
                questions.append(self.role_clarification_prompt(job_id))
        return ExplorationMapView(
            continue_exploring=tuple(continue_titles),
            keep_open=tuple(open_titles),
            deprioritized=tuple(deprioritized_titles),
            questions_to_validate=tuple(questions),
        )

    def action_status(self, action_id: str) -> str:
        return self.action_statuses.get(action_id, "未开始")

    @session_operation(DC.ACTION, "action_status")
    def set_action_status(self, action_id: str, status: str) -> None:
        if status not in ACTION_STATUS_OPTIONS:
            raise DemoValidationError("Invalid action status.")
        self._require_action(action_id)
        self.action_statuses[action_id] = status

    @session_operation(DC.ACTION, "action_review")
    def mark_action_already_done(self, action_id: str) -> None:
        """Request evidence review without upgrading profile authority."""

        self._require_action(action_id)
        self.actions_needing_evidence_review.add(action_id)
        self.action_statuses[action_id] = "进行中"

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
        graph_events = [] if self._state is None else [
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
        memory_events = [
            {
                "event_type": event.event_type.value,
                "node": event.component,
                "status": event.safe_metadata.get("status"),
                "profile_version": event.profile_version,
                "checkpoint_mode": None,
                "count": event.safe_metadata.get("result_count"),
                "memory_ids": event.safe_metadata.get("memory_ids"),
                "use_case": event.safe_metadata.get("use_case"),
            }
            for source in (
                self.memory_service.events,
                self.memory_context_coordinator.events,
                self.memory_change_detector.events,
                self.memory_change_service.events,
                self.role_memory_service.events,
            )
            for event in source
        ]
        return [*graph_events, *memory_events]

    def diagnostics_snapshot(self):
        """Read-only safe projection; page rerenders create no events."""
        return snapshot(self.diagnostic_collector, self.diagnostic_context.run_id)

    def close(self) -> None:
        self.diagnostic_collector.reset()
        self._temporary_directory.cleanup()

    def _seed_public_memory_scenario(self) -> None:
        self.memory_service.create_confirmed(
            subject_id=self.subject_id,
            memory_type=MemoryType.CAREER_PREFERENCE,
            content="更偏好亲手实现和搭建可运行系统。",
            source_type=EvidenceSourceType.SYSTEM_FIXTURE,
            confirmed_by_user=True,
            metadata={
                "demo_scope": "public_session",
                "signal_dimension": "work_style.primary_focus",
                "signal_value": "hands_on_implementation",
                "signal_version": 1,
            },
            memory_id="memory_demo_hands_on_preference",
        )
        self.memory_service.create_confirmed(
            subject_id=self.subject_id,
            memory_type=MemoryType.USER_FEEDBACK,
            content="可以接受文档较多的工作。",
            source_type=EvidenceSourceType.SYSTEM_FIXTURE,
            confirmed_by_user=True,
            metadata={
                "demo_scope": "public_session",
                "signal_dimension": "work_style.documentation_tolerance",
                "signal_value": "acceptable",
                "signal_version": 1,
            },
            memory_id="memory_demo_documentation_tolerance",
        )

    def _require_approved_role(self, job_id: str) -> None:
        if job_id not in APPROVED_ROLE_IDS:
            raise DemoValidationError("Requested role is not part of the public Demo.")

    def _require_action(self, action_id: str) -> None:
        if not self._state or self._state["workflow_status"] != GraphWorkflowStatus.COMPLETED.value:
            raise DemoWorkflowError("Actions are unavailable before profile confirmation.")
        if not any(
            action.action_id == action_id
            for result in self.match_results()
            for action in result.action_items
        ):
            raise DemoValidationError("Requested action is not part of the public Demo.")

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
