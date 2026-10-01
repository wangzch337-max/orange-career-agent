"""Explicit Phase 7C memory-use policies, consumers and mutation commands."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final
from uuid import uuid4

from data.models import (
    CareerPreference,
    EventType,
    EvidenceItem,
    EvidenceSourceType,
    InferenceType,
    MatchResult,
    UserProfile,
)
from memory.context import MemoryContextBuilder
from memory.errors import InvalidMemoryTransitionError, MemoryNotFoundError
from memory.models import (
    DimensionCardinality,
    MemoryAuthorityLabel,
    MemoryAwareStatement,
    MemoryChangeCandidate,
    MemoryChangeChoice,
    MemoryChangeStatus,
    MemoryConsumer,
    MemoryContext,
    MemoryContextPolicy,
    MemoryEvent,
    MemoryRecord,
    MemoryRetrievalMode,
    MemoryStatementKind,
    MemoryStatus,
    MemoryType,
    MemoryUseCase,
    ProfileRefinementContext,
    ProfileRefinementResult,
    StructuredSessionSignal,
)
from memory.service import MemoryService


PROFILE_REFINEMENT_POLICY: Final = MemoryContextPolicy(
    use_case=MemoryUseCase.PROFILE_REFINEMENT,
    allowed_memory_types=[
        MemoryType.CAREER_PREFERENCE,
        MemoryType.GOAL,
        MemoryType.USER_FEEDBACK,
    ],
    retrieval_mode=MemoryRetrievalMode.HYBRID,
    top_k=8,
    max_records=6,
    max_characters=3600,
    session_input_contributes=True,
    consumer=MemoryConsumer.PROFILE_REFINEMENT_SERVICE,
)

ROLE_EXPLORATION_POLICY: Final = MemoryContextPolicy(
    use_case=MemoryUseCase.ROLE_EXPLORATION,
    allowed_memory_types=[
        MemoryType.CAREER_PREFERENCE,
        MemoryType.GOAL,
        MemoryType.USER_FEEDBACK,
    ],
    retrieval_mode=MemoryRetrievalMode.HYBRID,
    top_k=5,
    max_records=3,
    max_characters=1800,
    session_input_contributes=False,
    consumer=MemoryConsumer.ROLE_MEMORY_CONTEXT_SERVICE,
)


class MemoryPolicyRegistry:
    """Closed, code-owned registry; providers cannot change retrieval scope."""

    _policies = {
        MemoryUseCase.PROFILE_REFINEMENT: PROFILE_REFINEMENT_POLICY,
        MemoryUseCase.ROLE_EXPLORATION: ROLE_EXPLORATION_POLICY,
    }

    def get(self, use_case: MemoryUseCase) -> MemoryContextPolicy:
        if not isinstance(use_case, MemoryUseCase):
            raise TypeError("Memory use case must be a MemoryUseCase enum value.")
        return self._policies[use_case].model_copy(deep=True)


class MemoryQueryBuilder:
    """Build bounded retrieval text deterministically, without identifiers."""

    _whitespace = re.compile(r"\s+")

    @classmethod
    def for_profile_refinement(cls, signal: StructuredSessionSignal) -> str:
        return cls._normalize(
            f"profile refinement {signal.dimension} {signal.display_label} {signal.value}"
        )

    @classmethod
    def for_role_exploration(
        cls,
        *,
        role_title: str,
        role_summary: str,
        clarification_topic: str = "",
    ) -> str:
        return cls._normalize(
            f"role exploration {role_title} {role_summary} {clarification_topic}"
        )

    @classmethod
    def _normalize(cls, value: str) -> str:
        normalized = cls._whitespace.sub(" ", value).strip()
        if not normalized:
            raise ValueError("Memory retrieval query cannot be empty.")
        return normalized[:1000]


class MemoryContextCoordinator:
    """Read-only policy gate between use cases and Phase 7B retrieval."""

    def __init__(
        self,
        memory_service: MemoryService,
        *,
        policies: MemoryPolicyRegistry | None = None,
    ) -> None:
        self.memory_service = memory_service
        self.policies = policies or MemoryPolicyRegistry()
        self.events: list[MemoryEvent] = []

    def retrieve(
        self,
        *,
        subject_id: str,
        use_case: MemoryUseCase,
        consumer: MemoryConsumer,
        query: str,
    ) -> MemoryContext:
        policy = self.policies.get(use_case)
        if consumer != policy.consumer:
            raise PermissionError("Memory context consumer is not allowed by policy.")
        self._event(
            EventType.MEMORY_CONTEXT_REQUESTED,
            subject_id,
            use_case,
            {"consumer": consumer.value, "retrieval_mode": policy.retrieval_mode.value},
        )
        results = self.memory_service.retrieve_hybrid(
            subject_id,
            query,
            memory_types=policy.allowed_memory_types,
            top_k=policy.top_k,
        )
        context = MemoryContextBuilder(
            max_records=policy.max_records,
            max_characters=policy.max_characters,
        ).build(subject_id, results)
        self._event(
            EventType.MEMORY_CONTEXT_BUILT,
            subject_id,
            use_case,
            {
                "consumer": consumer.value,
                "result_count": len(context.items),
                "memory_types": sorted({item.memory_type.value for item in context.items}),
                "memory_ids": [item.memory_id for item in context.items],
                "truncated": context.truncated,
            },
        )
        return context

    def record_consumed(
        self,
        *,
        subject_id: str,
        use_case: MemoryUseCase,
        consumer: MemoryConsumer,
        context: MemoryContext,
    ) -> None:
        self._event(
            EventType.MEMORY_CONTEXT_CONSUMED,
            subject_id,
            use_case,
            {
                "consumer": consumer.value,
                "memory_ids": [item.memory_id for item in context.items],
                "result_count": len(context.items),
            },
        )

    def _event(
        self,
        event_type: EventType,
        subject_id: str,
        use_case: MemoryUseCase,
        metadata: Mapping[str, object],
    ) -> None:
        self.events.append(
            MemoryEvent(
                event_id=f"memory_event_{uuid4().hex}",
                event_type=event_type,
                component="MemoryContextCoordinator",
                summary="Explicit memory context lifecycle event.",
                safe_metadata={"use_case": use_case.value, **dict(metadata)},
                subject_id=subject_id,
            )
        )


class MemoryReferenceResolver:
    """Revalidate statement references against current canonical authority."""

    def __init__(self, memory_service: MemoryService) -> None:
        self.memory_service = memory_service

    def resolve(
        self, subject_id: str, memory_refs: Sequence[str]
    ) -> tuple[MemoryRecord, ...]:
        records: list[MemoryRecord] = []
        for memory_id in dict.fromkeys(memory_refs):
            record = self.memory_service.memory_store.get(subject_id, memory_id)
            if record is None or record.status != MemoryStatus.CONFIRMED:
                raise MemoryNotFoundError("Memory-aware statement has a stale reference.")
            records.append(record)
        return tuple(records)

    def validate_statement(
        self, subject_id: str, statement: MemoryAwareStatement
    ) -> MemoryAwareStatement:
        self.resolve(subject_id, statement.memory_refs)
        return statement


@dataclass(frozen=True)
class DimensionPolicy:
    dimension: str
    cardinality: DimensionCardinality
    allowed_values: frozenset[str]

    @property
    def allow_keep_both(self) -> bool:
        return self.cardinality == DimensionCardinality.MULTI_VALUE


class StructuredSignalPolicyRegistry:
    _policies: Final = {
        "work_style.primary_focus": DimensionPolicy(
            "work_style.primary_focus",
            DimensionCardinality.SINGLE_VALUE,
            frozenset({"hands_on_implementation", "product_and_requirement_work"}),
        ),
        "work_style.documentation_tolerance": DimensionPolicy(
            "work_style.documentation_tolerance",
            DimensionCardinality.SINGLE_VALUE,
            frozenset({"comfortable", "acceptable", "not_preferred"}),
        ),
        "career_direction.priority": DimensionPolicy(
            "career_direction.priority",
            DimensionCardinality.MULTI_VALUE,
            frozenset({"ai_application", "ai_product", "data_analysis"}),
        ),
    }

    def get(self, dimension: str) -> DimensionPolicy:
        try:
            return self._policies[dimension]
        except KeyError as exc:
            raise ValueError("Unsupported structured signal dimension.") from exc


class MemoryChangeDetector:
    """Detect only structured, same-dimension differences."""

    def __init__(
        self,
        memory_service: MemoryService,
        *,
        dimensions: StructuredSignalPolicyRegistry | None = None,
    ) -> None:
        self.memory_service = memory_service
        self.dimensions = dimensions or StructuredSignalPolicyRegistry()
        self.events: list[MemoryEvent] = []

    def detect(
        self, subject_id: str, signal: StructuredSessionSignal
    ) -> MemoryChangeCandidate | None:
        policy = self.dimensions.get(signal.dimension)
        if signal.value not in policy.allowed_values:
            raise ValueError("Unsupported structured signal value.")
        prior = [
            record
            for record in self.memory_service.memory_store.list_active(subject_id)
            if record.metadata.get("signal_dimension") == signal.dimension
            and isinstance(record.metadata.get("signal_value"), str)
        ]
        if not prior:
            return None
        previous_values = list(
            dict.fromkeys(str(record.metadata["signal_value"]) for record in prior)
        )
        if signal.value in previous_values:
            return None
        choices = [
            MemoryChangeChoice.UPDATE_LONG_TERM,
            MemoryChangeChoice.DEFER,
            MemoryChangeChoice.UNCERTAIN,
        ]
        if policy.allow_keep_both:
            choices.insert(1, MemoryChangeChoice.KEEP_BOTH)
        candidate = MemoryChangeCandidate(
            candidate_id=f"memory_change_{uuid4().hex}",
            subject_id=subject_id,
            dimension=signal.dimension,
            previous_memory_refs=[record.memory_id for record in prior],
            previous_values=previous_values,
            current_session_value=signal.value,
            current_display_text=signal.display_label,
            change_kind="structured_same_dimension_change",
            allowed_user_choices=choices,
        )
        self.events.append(
            MemoryEvent(
                event_id=f"memory_event_{uuid4().hex}",
                event_type=EventType.MEMORY_CHANGE_CANDIDATE_CREATED,
                component="MemoryChangeDetector",
                summary="Structured same-dimension change candidate created.",
                safe_metadata={
                    "dimension": signal.dimension,
                    "previous_memory_ids": candidate.previous_memory_refs,
                    "allowed_choices": [item.value for item in choices],
                },
                subject_id=subject_id,
            )
        )
        return candidate


class MemoryChangeService:
    """Explicit write path for resolving a session-only change candidate."""

    def __init__(
        self,
        memory_service: MemoryService,
        *,
        dimensions: StructuredSignalPolicyRegistry | None = None,
    ) -> None:
        self.memory_service = memory_service
        self.dimensions = dimensions or StructuredSignalPolicyRegistry()
        self.events: list[MemoryEvent] = []

    def resolve(
        self,
        candidate: MemoryChangeCandidate,
        choice: MemoryChangeChoice,
    ) -> tuple[MemoryChangeCandidate, MemoryRecord | None]:
        if candidate.status != MemoryChangeStatus.PENDING:
            raise InvalidMemoryTransitionError("Memory change candidate is already resolved.")
        if choice not in candidate.allowed_user_choices:
            raise InvalidMemoryTransitionError("Choice is incompatible with dimension policy.")
        if choice == MemoryChangeChoice.UPDATE_LONG_TERM:
            previous = self._single_previous(candidate)
            version = int(previous.metadata.get("signal_version", 1)) + 1
            record = self.memory_service.supersede(
                candidate.subject_id,
                previous.memory_id,
                content=candidate.current_display_text,
                source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
                confirmed_by_user=True,
                metadata={
                    "signal_dimension": candidate.dimension,
                    "signal_value": candidate.current_session_value,
                    "signal_version": version,
                    "demo_scope": "public_session",
                },
            )
            resolved = candidate.model_copy(update={"status": MemoryChangeStatus.CONFIRMED})
            self._event(EventType.MEMORY_CHANGE_CONFIRMED, resolved, record.memory_id)
            return resolved, record
        if choice == MemoryChangeChoice.KEEP_BOTH:
            if not self.dimensions.get(candidate.dimension).allow_keep_both:
                raise InvalidMemoryTransitionError("Keep-both is not valid for this dimension.")
            record = self.memory_service.create_confirmed(
                subject_id=candidate.subject_id,
                memory_type=MemoryType.CAREER_PREFERENCE,
                content=candidate.current_display_text,
                source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
                confirmed_by_user=True,
                metadata={
                    "signal_dimension": candidate.dimension,
                    "signal_value": candidate.current_session_value,
                    "signal_version": 1,
                    "demo_scope": "public_session",
                },
            )
            resolved = candidate.model_copy(update={"status": MemoryChangeStatus.CONFIRMED})
            self._event(EventType.MEMORY_CHANGE_CONFIRMED, resolved, record.memory_id)
            return resolved, record
        status = (
            MemoryChangeStatus.DEFERRED
            if choice == MemoryChangeChoice.DEFER
            else MemoryChangeStatus.UNCERTAIN
        )
        resolved = candidate.model_copy(update={"status": status})
        self._event(EventType.MEMORY_CHANGE_DEFERRED, resolved, None)
        return resolved, None

    def _single_previous(self, candidate: MemoryChangeCandidate) -> MemoryRecord:
        if len(candidate.previous_memory_refs) != 1:
            raise InvalidMemoryTransitionError("Structured dimension has ambiguous authority.")
        record = self.memory_service.memory_store.get(
            candidate.subject_id, candidate.previous_memory_refs[0]
        )
        if record is None or record.status != MemoryStatus.CONFIRMED:
            raise MemoryNotFoundError("Previous structured Memory is no longer active.")
        return record

    def _event(
        self,
        event_type: EventType,
        candidate: MemoryChangeCandidate,
        memory_id: str | None,
    ) -> None:
        self.events.append(
            MemoryEvent(
                event_id=f"memory_event_{uuid4().hex}",
                event_type=event_type,
                component="MemoryChangeService",
                summary="Explicit structured memory-change decision recorded.",
                safe_metadata={
                    "dimension": candidate.dimension,
                    "status": candidate.status.value,
                    "previous_memory_ids": candidate.previous_memory_refs,
                },
                subject_id=candidate.subject_id,
                memory_id=memory_id,
            )
        )


class ProfileRefinementService:
    """Create a reviewable profile draft from current input plus bounded Memory."""

    def __init__(
        self,
        memory_service: MemoryService,
        coordinator: MemoryContextCoordinator,
    ) -> None:
        self.memory_service = memory_service
        self.coordinator = coordinator
        self.references = MemoryReferenceResolver(memory_service)
        self.profile_refinement_calls = 0
        self.events: list[MemoryEvent] = []

    def refine(
        self,
        *,
        subject_id: str,
        current_input: StructuredSessionSignal,
    ) -> ProfileRefinementResult:
        current_profile = self.memory_service.get_current_confirmed_profile(subject_id)
        if current_profile is None:
            raise ValueError("Profile refinement requires a confirmed profile.")
        query = MemoryQueryBuilder.for_profile_refinement(current_input)
        context = self.coordinator.retrieve(
            subject_id=subject_id,
            use_case=MemoryUseCase.PROFILE_REFINEMENT,
            consumer=MemoryConsumer.PROFILE_REFINEMENT_SERVICE,
            query=query,
        )
        refinement_context = ProfileRefinementContext(
            subject_id=subject_id,
            current_profile=current_profile,
            current_session_signal=current_input,
            memory_context=context,
        )
        statements = self._statements(refinement_context)
        evidence_id = f"profile_refinement_session_{current_profile.version + 1:03d}"
        evidence = [*current_profile.evidence]
        if evidence_id not in {item.id for item in evidence}:
            evidence.append(
                EvidenceItem(
                    id=evidence_id,
                    source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
                    source_name="Phase 7C public profile refinement",
                    statement=current_input.display_label,
                    confidence=1.0,
                    metadata={
                        "signal_dimension": current_input.dimension,
                        "session_order": current_input.session_order,
                    },
                )
            )
        preferences = [*current_profile.career_preferences]
        preference_id = f"preference_refinement_{current_profile.version + 1:03d}"
        preferences.append(
            CareerPreference(
                preference_id=preference_id,
                label=current_input.display_label,
                description="当前会话中的最新明确表达；等待画像复核确认。",
                confidence=1.0,
                evidence_ids=[evidence_id],
                source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
                inference_type=InferenceType.EXPLICIT_FACT,
                needs_confirmation=True,
                confirmed_by_user=False,
            )
        )
        draft = current_profile.create_revision(
            career_preferences=preferences,
            evidence=evidence,
        )
        refs = list(dict.fromkeys(ref for item in statements for ref in item.memory_refs))
        result = ProfileRefinementResult(
            draft_profile=draft,
            memory_aware_statements=statements,
            memory_refs=refs,
        )
        self.profile_refinement_calls += 1
        self.coordinator.record_consumed(
            subject_id=subject_id,
            use_case=MemoryUseCase.PROFILE_REFINEMENT,
            consumer=MemoryConsumer.PROFILE_REFINEMENT_SERVICE,
            context=context,
        )
        return result

    def confirm(
        self,
        subject_id: str,
        result: ProfileRefinementResult,
        *,
        confirmed_by_user: bool,
    ) -> UserProfile:
        if not confirmed_by_user:
            raise InvalidMemoryTransitionError("Profile revision requires explicit review.")
        confirmed = result.draft_profile.confirm()
        self.memory_service.save_confirmed_profile(subject_id, confirmed)
        return confirmed

    def _statements(
        self, context: ProfileRefinementContext
    ) -> list[MemoryAwareStatement]:
        policy = self.coordinator.policies.get(MemoryUseCase.PROFILE_REFINEMENT)
        if not policy.allow_memory_derived_statements:
            return []
        statements: list[MemoryAwareStatement] = []
        for index, item in enumerate(context.memory_context.items, start=1):
            statement = MemoryAwareStatement(
                statement_id=f"profile_memory_statement_{index:03d}",
                text=f"相关的历史信息：{item.content}",
                memory_refs=[item.memory_id],
                use_case=MemoryUseCase.PROFILE_REFINEMENT,
                statement_kind=MemoryStatementKind.RELATED_HISTORY,
                authority_label=MemoryAuthorityLabel.CONFIRMED_HISTORICAL_MEMORY,
                related_session_signal_id=context.current_session_signal.signal_id,
            )
            statements.append(self.references.validate_statement(context.subject_id, statement))
        return statements


class RoleMemoryContextService:
    """Read-only role recall; job facts and MatchResult are never inputs to mutation."""

    def __init__(
        self,
        memory_service: MemoryService,
        coordinator: MemoryContextCoordinator,
    ) -> None:
        self.memory_service = memory_service
        self.coordinator = coordinator
        self.references = MemoryReferenceResolver(memory_service)
        self.events: list[MemoryEvent] = []

    def recall(
        self,
        *,
        subject_id: str,
        role_title: str,
        role_summary: str,
        clarification_topic: str = "",
    ) -> tuple[MemoryContext, tuple[MemoryAwareStatement, ...]]:
        query = MemoryQueryBuilder.for_role_exploration(
            role_title=role_title,
            role_summary=role_summary,
            clarification_topic=clarification_topic,
        )
        context = self.coordinator.retrieve(
            subject_id=subject_id,
            use_case=MemoryUseCase.ROLE_EXPLORATION,
            consumer=MemoryConsumer.ROLE_MEMORY_CONTEXT_SERVICE,
            query=query,
        )
        policy = self.coordinator.policies.get(MemoryUseCase.ROLE_EXPLORATION)
        if not policy.allow_memory_derived_statements:
            self.coordinator.record_consumed(
                subject_id=subject_id,
                use_case=MemoryUseCase.ROLE_EXPLORATION,
                consumer=MemoryConsumer.ROLE_MEMORY_CONTEXT_SERVICE,
                context=context,
            )
            return context, ()
        statements: list[MemoryAwareStatement] = []
        for index, item in enumerate(context.items, start=1):
            statement = MemoryAwareStatement(
                statement_id=f"role_memory_statement_{index:03d}",
                text=f"你之前确认过：{item.content}",
                memory_refs=[item.memory_id],
                use_case=MemoryUseCase.ROLE_EXPLORATION,
                statement_kind=MemoryStatementKind.MEMORY_RECALL,
                authority_label=MemoryAuthorityLabel.CONFIRMED_HISTORICAL_MEMORY,
            )
            statements.append(self.references.validate_statement(subject_id, statement))
        self.coordinator.record_consumed(
            subject_id=subject_id,
            use_case=MemoryUseCase.ROLE_EXPLORATION,
            consumer=MemoryConsumer.ROLE_MEMORY_CONTEXT_SERVICE,
            context=context,
        )
        for statement in statements:
            self.events.append(
                MemoryEvent(
                    event_id=f"memory_event_{uuid4().hex}",
                    event_type=EventType.MEMORY_AWARE_STATEMENT_RENDERED,
                    component="RoleMemoryContextService",
                    summary="Memory-aware statement validated for presentation.",
                    safe_metadata={
                        "use_case": MemoryUseCase.ROLE_EXPLORATION.value,
                        "memory_ids": statement.memory_refs,
                        "statement_kind": statement.statement_kind.value,
                    },
                    subject_id=subject_id,
                )
            )
        return context, tuple(statements)

    def post_match_follow_up(
        self,
        *,
        subject_id: str,
        statements: Sequence[MemoryAwareStatement],
        match_result: MatchResult,
    ) -> MemoryAwareStatement | None:
        del match_result  # Explicitly read-only; authoritative relations are not inspected or patched.
        if not statements:
            return None
        refs = list(dict.fromkeys(ref for item in statements for ref in item.memory_refs))
        follow_up = MemoryAwareStatement(
            statement_id="post_match_memory_context_001",
            text=(
                "你后来确认过一个相关偏好。这里可能值得重新确认，"
                "但当前 MatchResult 本身尚未改变。"
            ),
            memory_refs=refs,
            use_case=MemoryUseCase.ROLE_EXPLORATION,
            statement_kind=MemoryStatementKind.POST_MATCH_CONTEXT,
            authority_label=MemoryAuthorityLabel.CONFIRMED_HISTORICAL_MEMORY,
        )
        return self.references.validate_statement(subject_id, follow_up)
