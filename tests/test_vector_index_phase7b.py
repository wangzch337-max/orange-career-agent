"""Derived sqlite-vec lifecycle, isolation and rebuild tests."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pysqlite3
import pytest

from agents.match_insight_demo import load_public_profile
from data.models import EvidenceSourceType
from memory.embeddings import FakeEmbeddingProvider
from memory.errors import VectorIndexConfigurationError
from memory.models import MemoryStatus, MemoryType
from memory.service import build_semantic_memory_service, build_sqlite_memory_service
from memory.sqlite_store import DEFAULT_MEMORY_DATABASE_PATH
from memory.vector_index import (
    DEFAULT_VECTOR_DATABASE_PATH,
    VECTOR_INDEX_SCHEMA_VERSION,
    MemoryVectorIndex,
    indexed_content_hash,
    indexed_memory_text,
)


@pytest.fixture
def semantic_service(tmp_path):
    return build_semantic_memory_service(
        memory_path=tmp_path / "canonical.sqlite3",
        vector_path=tmp_path / "vectors.sqlite3",
        embedding_provider=FakeEmbeddingProvider(),
    )


def confirmed(service, subject: str, content: str, memory_type=MemoryType.GOAL):
    return service.create_confirmed(
        subject_id=subject,
        memory_type=memory_type,
        content=content,
        source_type=EvidenceSourceType.SYSTEM_FIXTURE,
        confirmed_by_user=True,
    )


def test_canonical_and_vector_default_paths_are_separate_and_private() -> None:
    assert DEFAULT_MEMORY_DATABASE_PATH != DEFAULT_VECTOR_DATABASE_PATH
    assert DEFAULT_VECTOR_DATABASE_PATH.as_posix().endswith(
        "data/private/memory/orange_vectors.sqlite3"
    )


def test_vector_index_uses_pysqlite_without_global_replacement(semantic_service) -> None:
    assert sys.modules["sqlite3"] is sqlite3
    with semantic_service.database.connection() as canonical:
        assert type(canonical).__module__ == "sqlite3"
    with semantic_service.vector_index.connection() as derived:
        assert type(derived).__module__ == "pysqlite3.dbapi2"
        assert derived.execute("select vec_version()").fetchone()[0] == "v0.1.9"
    assert sqlite3 is not pysqlite3


def test_vector_schema_version_and_provider_metadata_exist(semantic_service) -> None:
    assert semantic_service.vector_index.schema_version() == VECTOR_INDEX_SCHEMA_VERSION
    metadata = semantic_service.vector_index._schema_metadata()
    assert metadata["embedding_provider"] == "fake_local"
    assert metadata["embedding_model_id"] == "stable-sha256-projection-v1"
    assert metadata["embedding_dimension"] == "48"


def test_indexed_text_and_content_hash_are_stable_and_minimal(semantic_service) -> None:
    record = confirmed(semantic_service, "subject_a", "Build local AI applications")
    assert indexed_memory_text(record) == "goal\nBuild local AI applications"
    assert indexed_content_hash(record) == indexed_content_hash(record)
    indexed = indexed_memory_text(record)
    assert record.subject_id not in indexed
    assert record.memory_id not in indexed
    assert record.created_at.isoformat() not in indexed


def test_only_confirmed_records_enter_index_by_default(semantic_service) -> None:
    candidate = semantic_service.create_candidate(
        subject_id="subject_a",
        memory_type=MemoryType.CAREER_INSIGHT,
        content="Highly relevant candidate",
        source_type=EvidenceSourceType.MODEL_INFERENCE,
    )
    assert semantic_service.vector_index.count_subject("subject_a") == 0
    with pytest.raises(ValueError):
        semantic_service.vector_index.index_record(candidate)
    confirmed_record = confirmed(semantic_service, "subject_a", "Confirmed evidence")
    entries = semantic_service.vector_index.list_entries("subject_a")
    assert [entry.memory_id for entry in entries] == [confirmed_record.memory_id]
    assert entries[0].content_hash == indexed_content_hash(confirmed_record)


def test_candidate_confirmation_adds_vector(semantic_service) -> None:
    candidate = semantic_service.create_candidate(
        subject_id="subject_a",
        memory_type=MemoryType.USER_FEEDBACK,
        content="Documentation work is acceptable",
        source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
    )
    assert semantic_service.vector_index.metadata_for(candidate.memory_id) is None
    confirmed_record = semantic_service.confirm_candidate(
        "subject_a", candidate.memory_id, confirmed_by_user=True
    )
    assert confirmed_record.status == MemoryStatus.CONFIRMED
    assert semantic_service.vector_index.metadata_for(candidate.memory_id) is not None


def test_supersede_removes_old_and_indexes_replacement(semantic_service) -> None:
    old = confirmed(semantic_service, "subject_a", "Prioritize data roles")
    replacement = semantic_service.supersede(
        "subject_a",
        old.memory_id,
        content="Prioritize AI Application roles",
        source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
        confirmed_by_user=True,
    )
    assert semantic_service.vector_index.metadata_for(old.memory_id) is None
    assert semantic_service.vector_index.metadata_for(replacement.memory_id) is not None
    assert semantic_service.memory_store.get("subject_a", old.memory_id).status == (
        MemoryStatus.SUPERSEDED
    )


@pytest.mark.parametrize("candidate_first", (False, True))
def test_archive_ensures_vector_absent(semantic_service, candidate_first) -> None:
    if candidate_first:
        record = semantic_service.create_candidate(
            subject_id="subject_a",
            memory_type=MemoryType.USER_FEEDBACK,
            content="Temporary candidate",
            source_type=EvidenceSourceType.MODEL_INFERENCE,
        )
    else:
        record = confirmed(semantic_service, "subject_a", "Confirmed then archived")
    semantic_service.archive("subject_a", record.memory_id)
    assert semantic_service.vector_index.metadata_for(record.memory_id) is None


def test_subject_query_isolation_with_identical_content(semantic_service) -> None:
    first = confirmed(semantic_service, "subject_a", "identical semantic content")
    second = confirmed(semantic_service, "subject_b", "identical semantic content")
    results = semantic_service.retrieve_semantic(
        "subject_a", "identical semantic content", top_k=10
    )
    ids = {item.memory.memory_id for item in results}
    assert first.memory_id in ids
    assert second.memory_id not in ids
    assert all(item.memory.subject_id == "subject_a" for item in results)


def test_dimension_and_model_identity_mismatch_are_rejected(tmp_path) -> None:
    path = tmp_path / "vectors.sqlite3"
    MemoryVectorIndex(path, FakeEmbeddingProvider(dimension=48))
    with pytest.raises(VectorIndexConfigurationError):
        MemoryVectorIndex(path, FakeEmbeddingProvider(dimension=64))
    other = FakeEmbeddingProvider(dimension=48)
    other.model_id = "different-fake-model"
    with pytest.raises(VectorIndexConfigurationError):
        MemoryVectorIndex(path, other)


def test_delete_recreate_and_rebuild_preserves_canonical_memory(tmp_path) -> None:
    memory_path = tmp_path / "canonical.sqlite3"
    vector_path = tmp_path / "vectors.sqlite3"
    service = build_semantic_memory_service(
        memory_path=memory_path,
        vector_path=vector_path,
        embedding_provider=FakeEmbeddingProvider(),
    )
    records = [
        confirmed(service, "subject_a", "Build AI applications"),
        confirmed(service, "subject_a", "Write product documents"),
    ]
    vector_path.unlink()
    service.vector_index = MemoryVectorIndex(vector_path, FakeEmbeddingProvider())
    service.semantic_retriever.vector_index = service.vector_index
    result = service.rebuild_subject_index("subject_a")
    assert result.cleared_count == 0
    assert result.eligible_count == result.indexed_count == 2
    assert {item.memory_id for item in service.memory_store.list_active("subject_a")} == {
        item.memory_id for item in records
    }
    assert service.retrieve_semantic("subject_a", "Build AI applications")


def test_profile_store_is_not_bulk_vectorized(semantic_service) -> None:
    semantic_service.save_confirmed_profile("subject_a", load_public_profile())
    assert semantic_service.vector_index.count_subject("subject_a") == 0


def test_canonical_writes_survive_corrupt_vector_index(tmp_path) -> None:
    vector_path = tmp_path / "vectors.sqlite3"
    service = build_semantic_memory_service(
        memory_path=tmp_path / "canonical.sqlite3",
        vector_path=vector_path,
        embedding_provider=FakeEmbeddingProvider(),
    )
    vector_path.unlink()
    vector_path.write_bytes(b"not a sqlite database")
    record = confirmed(service, "subject_a", "Canonical write must survive")
    assert service.memory_store.get("subject_a", record.memory_id) is not None
    assert service.vector_sync_diagnostics


def test_default_canonical_service_requires_no_vector_database(tmp_path) -> None:
    service = build_sqlite_memory_service(tmp_path / "canonical.sqlite3")
    record = confirmed(service, "subject_a", "Canonical only")
    assert service.vector_index is None
    assert service.memory_store.get("subject_a", record.memory_id) is not None


def test_coordinated_purge_removes_vectors_but_not_workflow_file(
    semantic_service, tmp_path
) -> None:
    workflow = tmp_path / "orange_workflow.sqlite3"
    workflow.write_bytes(b"workflow checkpoint sentinel")
    confirmed(semantic_service, "subject_a", "Memory to purge")
    result = semantic_service.purge_subject("subject_a")
    assert result.memory_records_deleted == 1
    assert result.vector_records_deleted == 1
    assert result.vector_cleanup_required is False
    assert semantic_service.memory_store.list_history("subject_a") == []
    assert semantic_service.vector_index.count_subject("subject_a") == 0
    assert workflow.read_bytes() == b"workflow checkpoint sentinel"
