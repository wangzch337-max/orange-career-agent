"""Phase 7C explicit memory-use, authority and change-handling gates."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from data.models import EvidenceSourceType, UserProfile
from memory.embeddings import FakeEmbeddingProvider
from memory.errors import InvalidMemoryTransitionError, MemoryNotFoundError
from memory.integration import (
    MemoryChangeDetector,
    MemoryChangeService,
    MemoryContextCoordinator,
    MemoryPolicyRegistry,
    MemoryQueryBuilder,
    MemoryReferenceResolver,
    ProfileRefinementService,
    RoleMemoryContextService,
    StructuredSignalPolicyRegistry,
)
from memory.models import (
    DimensionCardinality,
    MemoryAuthorityLabel,
    MemoryAwareStatement,
    MemoryChangeChoice,
    MemoryChangeStatus,
    MemoryConsumer,
    MemoryStatementKind,
    MemoryStatus,
    MemoryType,
    MemoryUseCase,
    StructuredSessionSignal,
)
from memory.service import build_semantic_memory_service
from ui.demo_controller import DemoController


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_PROFILE = ROOT / "data" / "fixtures" / "public_confirmed_profile.json"
SUBJECT = "subject_phase7c_public001"


@pytest.fixture
def service(tmp_path):
    return build_semantic_memory_service(
        memory_path=tmp_path / "canonical.sqlite3",
        vector_path=tmp_path / "vectors.sqlite3",
        embedding_provider=FakeEmbeddingProvider(),
    )


def _signal(
    value: str = "product_and_requirement_work",
    *,
    dimension: str = "work_style.primary_focus",
    label: str = "更愿意投入产品沟通与需求分析。",
) -> StructuredSessionSignal:
    return StructuredSessionSignal(
        signal_id="session_signal_001",
        dimension=dimension,
        value=value,
        display_label=label,
        source="explicit_user_input",
        session_order=1,
    )


def _structured_memory(service, *, subject: str = SUBJECT):
    return service.create_confirmed(
        subject_id=subject,
        memory_type=MemoryType.CAREER_PREFERENCE,
        content="更偏好亲手实现。",
        source_type=EvidenceSourceType.SYSTEM_FIXTURE,
        confirmed_by_user=True,
        metadata={
            "signal_dimension": "work_style.primary_focus",
            "signal_value": "hands_on_implementation",
            "signal_version": 1,
        },
    )


def test_memory_use_cases_and_policies_are_closed_deterministic_and_bounded() -> None:
    assert set(MemoryUseCase) == {
        MemoryUseCase.PROFILE_REFINEMENT,
        MemoryUseCase.ROLE_EXPLORATION,
        MemoryUseCase.CAREER_DIRECTION_DISCOVERY,
    }
    registry = MemoryPolicyRegistry()
    refinement = registry.get(MemoryUseCase.PROFILE_REFINEMENT)
    role = registry.get(MemoryUseCase.ROLE_EXPLORATION)
    assert refinement.consumer == MemoryConsumer.PROFILE_REFINEMENT_SERVICE
    assert role.consumer == MemoryConsumer.ROLE_MEMORY_CONTEXT_SERVICE
    assert refinement.top_k <= 8 and role.top_k <= 5
    assert refinement.max_records <= refinement.top_k
    assert role.max_records <= role.top_k
    assert set(role.allowed_memory_types) == {
        MemoryType.CAREER_PREFERENCE,
        MemoryType.GOAL,
        MemoryType.USER_FEEDBACK,
    }
    assert registry.get(MemoryUseCase.ROLE_EXPLORATION) == role
    with pytest.raises(TypeError):
        registry.get("role_exploration")  # type: ignore[arg-type]


def test_phase7b_checkpoint_exists_before_phase7c_work() -> None:
    messages = subprocess.check_output(
        ["git", "log", "--format=%s", "-n", "20"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    assert "feat: add semantic hybrid memory retrieval" in messages


def test_query_builder_is_deterministic_and_contains_no_subject_or_database_ids() -> None:
    signal = _signal()
    assert MemoryQueryBuilder.for_profile_refinement(signal) == (
        MemoryQueryBuilder.for_profile_refinement(signal)
    )
    role_query = MemoryQueryBuilder.for_role_exploration(
        role_title="AI Product Intern",
        role_summary="理解需求并验证产品方案",
        clarification_topic="工作方式",
    )
    assert role_query == (
        "role exploration AI Product Intern 理解需求并验证产品方案 工作方式"
    )
    lowered = role_query.casefold()
    assert "subject_" not in lowered and ".sqlite" not in lowered


def test_coordinator_enforces_consumer_type_filters_budgets_and_read_only(service) -> None:
    allowed = _structured_memory(service)
    excluded = service.create_confirmed(
        subject_id=SUBJECT,
        memory_type=MemoryType.PROJECT_EVIDENCE,
        content="A synthetic project mentioning the same product topic.",
        source_type=EvidenceSourceType.SYSTEM_FIXTURE,
        confirmed_by_user=True,
    )
    before = service.memory_store.list_history(SUBJECT)
    coordinator = MemoryContextCoordinator(service)
    context = coordinator.retrieve(
        subject_id=SUBJECT,
        use_case=MemoryUseCase.ROLE_EXPLORATION,
        consumer=MemoryConsumer.ROLE_MEMORY_CONTEXT_SERVICE,
        query="AI Product hands-on requirements",
    )
    after = service.memory_store.list_history(SUBJECT)
    assert allowed.memory_id in {item.memory_id for item in context.items}
    assert excluded.memory_id not in {item.memory_id for item in context.items}
    assert len(context.items) <= 3 and context.character_count <= 1800
    assert before == after
    with pytest.raises(PermissionError):
        coordinator.retrieve(
            subject_id=SUBJECT,
            use_case=MemoryUseCase.ROLE_EXPLORATION,
            consumer=MemoryConsumer.PROFILE_REFINEMENT_SERVICE,
            query="AI Product",
        )


def test_candidates_superseded_archived_and_wrong_subject_never_enter_context(service) -> None:
    active = _structured_memory(service)
    candidate = service.create_candidate(
        subject_id=SUBJECT,
        memory_type=MemoryType.USER_FEEDBACK,
        content="candidate product preference",
        source_type=EvidenceSourceType.MODEL_INFERENCE,
    )
    archived = service.create_confirmed(
        subject_id=SUBJECT,
        memory_type=MemoryType.GOAL,
        content="archived product goal",
        source_type=EvidenceSourceType.SYSTEM_FIXTURE,
        confirmed_by_user=True,
    )
    service.archive(SUBJECT, archived.memory_id)
    wrong = service.create_confirmed(
        subject_id="subject_other_public002",
        memory_type=MemoryType.GOAL,
        content="other subject product goal",
        source_type=EvidenceSourceType.SYSTEM_FIXTURE,
        confirmed_by_user=True,
    )
    coordinator = MemoryContextCoordinator(service)
    context = coordinator.retrieve(
        subject_id=SUBJECT,
        use_case=MemoryUseCase.ROLE_EXPLORATION,
        consumer=MemoryConsumer.ROLE_MEMORY_CONTEXT_SERVICE,
        query="product preference goal",
    )
    ids = {item.memory_id for item in context.items}
    assert active.memory_id in ids
    assert ids.isdisjoint({candidate.memory_id, archived.memory_id, wrong.memory_id})


def test_only_structured_same_dimension_difference_creates_change_candidate(service) -> None:
    old = _structured_memory(service)
    service.create_confirmed(
        subject_id=SUBJECT,
        memory_type=MemoryType.CAREER_PREFERENCE,
        content="Semantically similar free text with no structured metadata.",
        source_type=EvidenceSourceType.SYSTEM_FIXTURE,
        confirmed_by_user=True,
    )
    detector = MemoryChangeDetector(service)
    candidate = detector.detect(SUBJECT, _signal())
    assert candidate is not None
    assert candidate.previous_memory_refs == [old.memory_id]
    assert candidate.change_kind == "structured_same_dimension_change"
    assert MemoryChangeChoice.KEEP_BOTH not in candidate.allowed_user_choices
    assert detector.detect(
        SUBJECT,
        _signal(
            "hands_on_implementation",
            label="更偏好亲手实现。",
        ),
    ) is None
    assert detector.detect(
        SUBJECT,
        _signal(
            "comfortable",
            dimension="work_style.documentation_tolerance",
            label="可以接受文档工作。",
        ),
    ) is None


def test_explicit_update_supersedes_old_memory_and_vector(service) -> None:
    old = _structured_memory(service)
    candidate = MemoryChangeDetector(service).detect(SUBJECT, _signal())
    assert candidate is not None
    resolved, replacement = MemoryChangeService(service).resolve(
        candidate, MemoryChangeChoice.UPDATE_LONG_TERM
    )
    assert resolved.status == MemoryChangeStatus.CONFIRMED
    assert replacement is not None and replacement.status == MemoryStatus.CONFIRMED
    history = service.memory_store.list_history(SUBJECT)
    assert next(item for item in history if item.memory_id == old.memory_id).status == (
        MemoryStatus.SUPERSEDED
    )
    assert service.vector_index.metadata_for(old.memory_id) is None
    assert service.vector_index.metadata_for(replacement.memory_id) is not None
    results = service.retrieve_hybrid(SUBJECT, "hands-on product", top_k=10)
    assert old.memory_id not in {item.memory.memory_id for item in results}


@pytest.mark.parametrize(
    ("choice", "expected_status"),
    [
        (MemoryChangeChoice.DEFER, MemoryChangeStatus.DEFERRED),
        (MemoryChangeChoice.UNCERTAIN, MemoryChangeStatus.UNCERTAIN),
    ],
)
def test_defer_and_uncertain_choices_make_zero_canonical_or_vector_mutation(
    service, choice, expected_status
) -> None:
    _structured_memory(service)
    candidate = MemoryChangeDetector(service).detect(SUBJECT, _signal())
    before = service.memory_store.list_history(SUBJECT)
    vector_count = service.vector_index.count_subject(SUBJECT)
    resolved, record = MemoryChangeService(service).resolve(candidate, choice)
    assert resolved.status == expected_status and record is None
    assert service.memory_store.list_history(SUBJECT) == before
    assert service.vector_index.count_subject(SUBJECT) == vector_count


def test_keep_both_is_only_offered_and_allowed_for_multi_value_dimensions(service) -> None:
    policy = StructuredSignalPolicyRegistry().get("career_direction.priority")
    assert policy.cardinality == DimensionCardinality.MULTI_VALUE
    assert policy.allow_keep_both is True
    old = service.create_confirmed(
        subject_id=SUBJECT,
        memory_type=MemoryType.CAREER_PREFERENCE,
        content="优先探索 AI 应用。",
        source_type=EvidenceSourceType.SYSTEM_FIXTURE,
        confirmed_by_user=True,
        metadata={
            "signal_dimension": "career_direction.priority",
            "signal_value": "ai_application",
            "signal_version": 1,
        },
    )
    signal = _signal(
        "ai_product",
        dimension="career_direction.priority",
        label="同时探索 AI 产品。",
    )
    candidate = MemoryChangeDetector(service).detect(SUBJECT, signal)
    assert MemoryChangeChoice.KEEP_BOTH in candidate.allowed_user_choices
    _, added = MemoryChangeService(service).resolve(candidate, MemoryChangeChoice.KEEP_BOTH)
    assert added is not None
    assert {item.memory_id for item in service.memory_store.list_active(SUBJECT)}.issuperset(
        {old.memory_id, added.memory_id}
    )


def test_memory_aware_statement_requires_and_revalidates_active_same_subject_refs(service) -> None:
    record = _structured_memory(service)
    statement = MemoryAwareStatement(
        statement_id="statement_001",
        text="你之前确认过：更偏好亲手实现。",
        memory_refs=[record.memory_id],
        use_case=MemoryUseCase.ROLE_EXPLORATION,
        statement_kind=MemoryStatementKind.MEMORY_RECALL,
        authority_label=MemoryAuthorityLabel.CONFIRMED_HISTORICAL_MEMORY,
    )
    resolver = MemoryReferenceResolver(service)
    assert resolver.validate_statement(SUBJECT, statement) == statement
    with pytest.raises(ValidationError):
        MemoryAwareStatement(
            statement_id="statement_empty_refs",
            text="Orange 记得。",
            memory_refs=[],
            use_case=MemoryUseCase.ROLE_EXPLORATION,
            statement_kind=MemoryStatementKind.MEMORY_RECALL,
            authority_label=MemoryAuthorityLabel.CONFIRMED_HISTORICAL_MEMORY,
        )
    with pytest.raises(MemoryNotFoundError):
        resolver.validate_statement("subject_other_public002", statement)
    service.archive(SUBJECT, record.memory_id)
    with pytest.raises(MemoryNotFoundError):
        resolver.validate_statement(SUBJECT, statement)


def test_profile_refinement_is_draft_only_then_explicit_confirmation_versions_profile(service) -> None:
    profile = UserProfile.model_validate_json(PUBLIC_PROFILE.read_text(encoding="utf-8"))
    service.save_confirmed_profile(SUBJECT, profile)
    memory = _structured_memory(service)
    coordinator = MemoryContextCoordinator(service)
    refiner = ProfileRefinementService(service, coordinator)
    result = refiner.refine(subject_id=SUBJECT, current_input=_signal())
    assert result.draft_profile.version == 2
    assert result.draft_profile.confirmed is False
    assert result.requires_profile_review is True
    assert result.current_input_is_newest is True
    assert memory.memory_id in result.memory_refs
    assert refiner.profile_refinement_calls == 1
    assert service.get_current_confirmed_profile(SUBJECT).version == 1
    with pytest.raises(InvalidMemoryTransitionError):
        refiner.confirm(SUBJECT, result, confirmed_by_user=False)
    confirmed = refiner.confirm(SUBJECT, result, confirmed_by_user=True)
    assert confirmed.version == 2 and confirmed.confirmed is True
    assert [item.version for item in service.profile_store.list_profile_history(SUBJECT)] == [
        1,
        2,
    ]


def test_role_recall_and_post_match_context_do_not_mutate_job_or_match() -> None:
    controller = DemoController()
    try:
        controller.start()
        controller.confirm_profile()
        job_before = controller.intelligence_for("job_001").model_dump(mode="json")
        match_before = controller.match_for("job_001").model_dump(mode="json")
        context, statements = controller.role_memory_context("job_001")
        follow_up = controller.memory_aware_match_follow_up("job_001")
        assert context.items and statements and follow_up is not None
        assert all(item.memory_refs for item in statements)
        assert follow_up.memory_refs
        assert controller.intelligence_for("job_001").model_dump(mode="json") == job_before
        assert controller.match_for("job_001").model_dump(mode="json") == match_before
    finally:
        controller.close()


def test_normal_workflow_job_and_match_make_zero_memory_retrieval_calls() -> None:
    controller = DemoController()
    try:
        controller.start()
        controller.confirm_profile()
        assert controller.memory_context_coordinator.events == []
        assert controller.role_memory_service.events == []
        assert controller.state["self_discovery_call_count"] == 1
    finally:
        controller.close()


def test_demo_update_requires_separate_profile_confirmation_and_preserves_match() -> None:
    controller = DemoController()
    try:
        controller.start()
        controller.confirm_profile()
        match_before = controller.match_for("job_001").model_dump(mode="json")
        candidate = controller.submit_structured_preference(
            dimension="work_style.primary_focus",
            value="product_and_requirement_work",
            display_label="更愿意投入产品沟通与需求分析。",
        )
        controller.resolve_memory_change(candidate.candidate_id, MemoryChangeChoice.UPDATE_LONG_TERM)
        assert controller.pending_profile_refinement is not None
        assert controller.current_profile_from_memory().version == 1
        assert controller.match_for("job_001").model_dump(mode="json") == match_before
        controller.confirm_pending_profile_refinement()
        assert controller.current_profile_from_memory().version == 2
        assert controller.match_for("job_001").model_dump(mode="json") == match_before
    finally:
        controller.close()


def test_safe_trace_contains_ids_and_counts_but_not_raw_query_or_memory_content() -> None:
    controller = DemoController()
    try:
        controller.start()
        controller.confirm_profile()
        controller.role_memory_context("job_001")
        trace = controller.safe_trace()
        serialized = str(trace)
        assert "memory_context_requested" in serialized
        assert "memory_context_built" in serialized
        assert "memory_context_consumed" in serialized
        assert "memory_demo_hands_on_preference" in serialized
        assert "更偏好亲手实现" not in serialized
        assert "role exploration AI Product" not in serialized
    finally:
        controller.close()


def test_fresh_controller_resets_all_phase7c_session_state() -> None:
    first = DemoController()
    try:
        first.start()
        first.confirm_profile()
        first.role_memory_context("job_001")
        candidate = first.submit_structured_preference(
            dimension="work_style.primary_focus",
            value="product_and_requirement_work",
            display_label="更愿意投入产品沟通与需求分析。",
        )
        assert candidate is not None
        assert first.role_memory_contexts
        assert first.structured_session_signals
        assert first.memory_change_candidates
        second = DemoController()
        try:
            assert second.subject_id != first.subject_id
            assert second.role_memory_contexts == {}
            assert second.role_memory_statements == {}
            assert second.structured_session_signals == {}
            assert second.memory_change_candidates == {}
            assert second.pending_profile_refinement is None
        finally:
            second.close()
    finally:
        first.close()


def test_job_and_match_agents_have_no_phase7c_memory_consumer_imports() -> None:
    for relative in ("agents/job_intelligence.py", "agents/match_insight.py"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "MemoryContext" not in source
        assert "MemoryService" not in source
        assert "retrieve_context" not in source
    workflow_source = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "workflows").glob("*.py")
    )
    assert "MemoryContextCoordinator" not in workflow_source


def test_frozen_historical_self_discovery_prompts_remain_unchanged() -> None:
    expected = {
        "self_discovery_v1.md": "27ce461b5c1a6b1f062f24f04dfa42aaa90e0d00803d41d579b2ba475134eacb",
        "self_discovery_v2.md": "0b729d850022a5fc7e6ab735052a8d89c581c12bde3836a73b9867074bb33102",
    }
    for name, digest in expected.items():
        payload = (ROOT / "config" / "prompts" / name).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == digest
