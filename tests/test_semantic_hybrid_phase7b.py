"""Semantic authority defense, hybrid RRF and context tests."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from data.models import EvidenceSourceType
from memory.context import MemoryContextBuilder
from memory.embeddings import FakeEmbeddingProvider
from memory.models import (
    HybridMemoryRetrievalResult,
    MemoryStatus,
    MemoryType,
)
from memory.semantic import RRF_CONSTANT, HybridMemoryRetriever
from memory.semantic_demo import run_public_semantic_demo
from memory.service import build_semantic_memory_service


@pytest.fixture
def service(tmp_path):
    return build_semantic_memory_service(
        memory_path=tmp_path / "canonical.sqlite3",
        vector_path=tmp_path / "vectors.sqlite3",
        embedding_provider=FakeEmbeddingProvider(),
        context_max_records=2,
        context_max_characters=80,
    )


def add_confirmed(service, content: str, memory_type=MemoryType.GOAL):
    return service.create_confirmed(
        subject_id="subject_a",
        memory_type=memory_type,
        content=content,
        source_type=EvidenceSourceType.SYSTEM_FIXTURE,
        confirmed_by_user=True,
    )


def test_semantic_result_is_structured_and_canonically_resolved(service) -> None:
    record = add_confirmed(service, "Build tested API integrations")
    result = service.retrieve_semantic("subject_a", "Build tested API integrations")[0]
    assert result.memory == service.memory_store.get("subject_a", record.memory_id)
    assert result.memory.status == MemoryStatus.CONFIRMED
    assert result.semantic_rank == 1
    assert result.semantic_distance >= 0
    assert result.embedding_provider == "fake_local"
    assert result.embedding_model_id == "stable-sha256-projection-v1"


def test_highly_relevant_candidate_is_excluded(service) -> None:
    candidate = service.create_candidate(
        subject_id="subject_a",
        memory_type=MemoryType.CAREER_PREFERENCE,
        content="I want AI Application roles AI Application roles",
        source_type=EvidenceSourceType.MODEL_INFERENCE,
    )
    active = add_confirmed(service, "I enjoy building software systems")
    results = service.retrieve_semantic(
        "subject_a", "I want AI Application roles AI Application roles"
    )
    ids = {item.memory.memory_id for item in results}
    assert candidate.memory_id not in ids
    assert active.memory_id in ids


@pytest.mark.parametrize(
    "inactive_status", (MemoryStatus.CANDIDATE, MemoryStatus.ARCHIVED)
)
def test_stale_vector_for_inactive_canonical_status_is_filtered(
    service, inactive_status
) -> None:
    record = add_confirmed(service, "Near identical inactive memory")
    with service.database.connection() as connection:
        connection.execute(
            "UPDATE memory_records SET status = ? WHERE memory_id = ?",
            (inactive_status.value, record.memory_id),
        )
        connection.commit()
    results = service.retrieve_semantic(
        "subject_a", "Near identical inactive memory", top_k=10
    )
    assert record.memory_id not in {item.memory.memory_id for item in results}
    assert any(
        event.event_type.value == "memory_vector_stale_filtered"
        for event in service.semantic_retriever.events
    )


def test_stale_superseded_vector_is_filtered(service) -> None:
    old = add_confirmed(service, "I primarily want Data Analyst roles")
    replacement = service.memory_store.supersede(
        "subject_a",
        old.memory_id,
        content="I prioritize AI Application roles",
        source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
        confirmed_by_user=True,
    )
    assert service.vector_index.metadata_for(old.memory_id) is not None
    results = service.retrieve_semantic(
        "subject_a", "I primarily want Data Analyst roles", top_k=10
    )
    ids = {item.memory.memory_id for item in results}
    assert old.memory_id not in ids
    assert replacement.memory_id not in ids  # replacement was not silently indexed


def test_semantic_memory_type_filter_and_top_k(service) -> None:
    goal = add_confirmed(service, "Build an AI portfolio", MemoryType.GOAL)
    add_confirmed(
        service,
        "Build an AI portfolio with APIs",
        MemoryType.PROJECT_EVIDENCE,
    )
    results = service.retrieve_semantic(
        "subject_a",
        "Build an AI portfolio",
        memory_types=(MemoryType.GOAL,),
        top_k=1,
    )
    assert [item.memory.memory_id for item in results] == [goal.memory_id]


def test_hybrid_rrf_is_deterministic_and_deduplicates_dual_source(service) -> None:
    record = add_confirmed(service, "Build APIs with automated testing")
    first = service.retrieve_hybrid(
        "subject_a", "Build APIs with automated testing", top_k=10
    )
    second = service.retrieve_hybrid(
        "subject_a", "Build APIs with automated testing", top_k=10
    )
    assert first == second
    assert len([item for item in first if item.memory.memory_id == record.memory_id]) == 1
    result = first[0]
    assert result.lexical_rank == result.semantic_rank == result.fusion_rank == 1
    assert result.rrf_score == pytest.approx(2 / (RRF_CONSTANT + 1))


def test_hybrid_preserves_lexical_only_and_semantic_only_results(service) -> None:
    lexical_only = service.memory_store.create_confirmed(
        subject_id="subject_a",
        memory_type=MemoryType.GOAL,
        content="Unique lexical lighthouse phrase",
        source_type=EvidenceSourceType.SYSTEM_FIXTURE,
        confirmed_by_user=True,
    )
    semantic_only = add_confirmed(service, "Completely different indexed passage")
    results = service.retrieve_hybrid(
        "subject_a", "Unique lexical lighthouse phrase", top_k=10
    )
    by_id = {item.memory.memory_id: item for item in results}
    assert by_id[lexical_only.memory_id].lexical_rank == 1
    assert by_id[lexical_only.memory_id].semantic_rank is None
    assert by_id[semantic_only.memory_id].semantic_rank is not None
    assert by_id[semantic_only.memory_id].lexical_rank is None


def test_rrf_source_uses_no_raw_score_weighted_sum() -> None:
    source = inspect.getsource(HybridMemoryRetriever.retrieve)
    assert "self.rrf_constant + rank" in source
    assert "relevance.score +" not in source
    assert "semantic_distance +" not in source


def test_hybrid_returns_active_confirmed_only(service) -> None:
    active = add_confirmed(service, "Confirmed active direction")
    candidate = service.create_candidate(
        subject_id="subject_a",
        memory_type=MemoryType.GOAL,
        content="Confirmed active direction candidate",
        source_type=EvidenceSourceType.MODEL_INFERENCE,
    )
    results = service.retrieve_hybrid("subject_a", "Confirmed active direction")
    assert active.memory_id in {item.memory.memory_id for item in results}
    assert candidate.memory_id not in {item.memory.memory_id for item in results}
    assert all(item.memory.status == MemoryStatus.CONFIRMED for item in results)


def test_context_builder_preserves_authority_and_provenance_with_bounds(service) -> None:
    add_confirmed(service, "API testing")
    add_confirmed(service, "API integration")
    add_confirmed(service, "API documentation")
    context = service.retrieve_context("subject_a", "API", top_k=10)
    assert len(context.items) == 2
    assert context.truncated is True
    assert context.character_count <= 80
    assert all(item.authority == "active_confirmed" for item in context.items)
    assert all(item.status == MemoryStatus.CONFIRMED for item in context.items)
    assert all(item.fusion_rank >= 1 for item in context.items)


def test_context_builder_omits_non_authoritative_and_wrong_subject(service) -> None:
    confirmed = add_confirmed(service, "Authoritative context")
    candidate = confirmed.model_copy(update={"status": MemoryStatus.CANDIDATE})
    wrong_subject = confirmed.model_copy(update={"subject_id": "subject_b"})
    results = [
        HybridMemoryRetrievalResult(
            memory=candidate,
            semantic_rank=1,
            fusion_rank=1,
            rrf_score=0.1,
        ),
        HybridMemoryRetrievalResult(
            memory=wrong_subject,
            semantic_rank=2,
            fusion_rank=2,
            rrf_score=0.09,
        ),
    ]
    context = MemoryContextBuilder().build("subject_a", results)
    assert context.items == []


def test_missing_vector_database_surfaces_lexical_fallback(service) -> None:
    record = add_confirmed(service, "Lexical fallback phrase")
    Path(service.vector_index.path).unlink()
    results = service.retrieve_hybrid("subject_a", "Lexical fallback phrase")
    assert [item.memory.memory_id for item in results] == [record.memory_id]
    assert service.hybrid_retriever.last_mode == "lexical_only_fallback"


def test_safe_events_omit_raw_content_query_and_vectors(service) -> None:
    marker = "PRIVATE_QUERY_AND_MEMORY_MARKER_7B"
    add_confirmed(service, marker)
    service.retrieve_hybrid("subject_a", marker)
    payload = "".join(
        event.model_dump_json()
        for owner in (
            service,
            service.vector_index,
            service.semantic_retriever,
            service.hybrid_retriever,
        )
        for event in owner.events
    )
    assert marker not in payload
    assert "values" not in payload


def test_public_semantic_demo_covers_lifecycle_rebuild_and_purge() -> None:
    result = run_public_semantic_demo()
    assert result["provider"] == "fake_local"
    assert result["superseded_memory_excluded"] is True
    assert result["stale_archived_filtered"] is True
    assert result["rebuild"]["indexed_count"] == result["rebuild"]["eligible_count"]
    assert result["canonical_after_purge"] == 0
    assert result["vectors_after_purge"] == 0


def test_no_agent_or_graph_auto_retrieval_was_added() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = list((root / "agents").rglob("*.py")) + list(
        (root / "workflows").rglob("*.py")
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "HybridMemoryRetriever" not in source
    assert "SemanticMemoryRetriever" not in source
    assert "retrieve_context(" not in source
