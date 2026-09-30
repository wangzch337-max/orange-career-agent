"""Deterministic lexical retrieval and hard privacy purge tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.match_insight_demo import load_public_profile
from data.models import EvidenceSourceType
from memory.errors import MemoryStoreError
from memory.models import MemoryStatus, MemoryType
from memory.service import build_sqlite_memory_service


@pytest.fixture
def service(tmp_path):
    return build_sqlite_memory_service(tmp_path / "memory.sqlite3")


def test_exact_metadata_and_type_filters(service) -> None:
    target = service.create_confirmed(
        subject_id="subject_alpha001",
        memory_type=MemoryType.CAREER_PREFERENCE,
        content="Explore AI Application roles",
        source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
        confirmed_by_user=True,
        metadata={"region": "hong_kong", "scope": "career"},
    )
    service.create_confirmed(
        subject_id="subject_alpha001",
        memory_type=MemoryType.GOAL,
        content="Explore AI Application roles",
        source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
        confirmed_by_user=True,
        metadata={"region": "mainland_china", "scope": "learning"},
    )
    records = service.memory_store.list_active(
        "subject_alpha001",
        memory_types=(MemoryType.CAREER_PREFERENCE,),
        metadata_filters={"region": "hong_kong"},
    )
    assert [item.memory_id for item in records] == [target.memory_id]


def test_lexical_retrieval_is_deterministic_and_preserves_authority(service) -> None:
    exact = service.create_confirmed(
        subject_id="subject_alpha001",
        memory_type=MemoryType.CAREER_PREFERENCE,
        content="AI Application roles are my primary exploration direction",
        source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
        confirmed_by_user=True,
    )
    service.create_confirmed(
        subject_id="subject_alpha001",
        memory_type=MemoryType.GOAL,
        content="Build one AI portfolio application",
        source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
        confirmed_by_user=True,
    )
    candidate = service.create_candidate(
        subject_id="subject_alpha001",
        memory_type=MemoryType.CAREER_INSIGHT,
        content="AI Application roles might be relevant",
        source_type=EvidenceSourceType.MODEL_INFERENCE,
        confidence=0.99,
    )
    first = service.retrieve("subject_alpha001", "AI Application roles")
    second = service.retrieve("subject_alpha001", "AI Application roles")
    assert [item.memory.memory_id for item in first] == [
        item.memory.memory_id for item in second
    ]
    assert first[0].memory.memory_id == exact.memory_id
    assert all(item.memory.status == MemoryStatus.CONFIRMED for item in first)
    assert candidate.memory_id not in {item.memory.memory_id for item in first}
    assert service.memory_store.get(
        "subject_alpha001", exact.memory_id
    ).status == MemoryStatus.CONFIRMED


def test_history_retrieval_requires_explicit_option(service) -> None:
    candidate = service.create_candidate(
        subject_id="subject_alpha001",
        memory_type=MemoryType.CAREER_INSIGHT,
        content="Documentation work may be acceptable",
        source_type=EvidenceSourceType.MODEL_INFERENCE,
    )
    assert service.retrieve("subject_alpha001", "documentation") == []
    history = service.retrieve(
        "subject_alpha001",
        "documentation",
        include_history=True,
        statuses=(MemoryStatus.CANDIDATE,),
    )
    assert history[0].memory.memory_id == candidate.memory_id
    assert history[0].memory.status == MemoryStatus.CANDIDATE


def test_explicit_user_feedback_supersedes_uncertain_candidate(service) -> None:
    uncertain = service.create_candidate(
        subject_id="subject_alpha001",
        memory_type=MemoryType.USER_FEEDBACK,
        content="The user may dislike documentation-heavy work",
        source_type=EvidenceSourceType.MODEL_INFERENCE,
    )
    feedback = service.record_user_feedback(
        "subject_alpha001",
        "I am comfortable with documentation work.",
        confirmed_by_user=True,
    )
    active = service.retrieve("subject_alpha001", "documentation work")
    assert feedback.memory_id in {item.memory.memory_id for item in active}
    assert uncertain.memory_id not in {item.memory.memory_id for item in active}
    assert all(item.memory.memory_type == MemoryType.USER_FEEDBACK for item in active)


def test_hard_purge_is_subject_scoped_and_leaves_workflow_db(service, tmp_path) -> None:
    workflow_db = tmp_path / "orange_workflow.sqlite3"
    workflow_db.write_bytes(b"workflow-checkpoint-sentinel")
    service.save_confirmed_profile("subject_alpha001", load_public_profile())
    service.save_confirmed_profile("subject_beta002", load_public_profile())
    service.create_confirmed(
        subject_id="subject_alpha001",
        memory_type=MemoryType.GOAL,
        content="Synthetic goal A",
        source_type=EvidenceSourceType.SYSTEM_FIXTURE,
        confirmed_by_user=True,
    )
    other = service.create_confirmed(
        subject_id="subject_beta002",
        memory_type=MemoryType.GOAL,
        content="Synthetic goal B",
        source_type=EvidenceSourceType.SYSTEM_FIXTURE,
        confirmed_by_user=True,
    )
    result = service.purge_subject("subject_alpha001")
    assert result.profile_versions_deleted == 1
    assert result.current_pointer_deleted == 1
    assert result.memory_records_deleted == 1
    assert service.get_current_confirmed_profile("subject_alpha001") is None
    assert service.memory_store.list_history("subject_alpha001") == []
    assert service.get_current_confirmed_profile("subject_beta002") is not None
    assert service.memory_store.get("subject_beta002", other.memory_id) is not None
    assert workflow_db.read_bytes() == b"workflow-checkpoint-sentinel"


def test_purge_rolls_back_transaction_on_failure(service) -> None:
    service.save_confirmed_profile("subject_alpha001", load_public_profile())
    memory = service.create_confirmed(
        subject_id="subject_alpha001",
        memory_type=MemoryType.GOAL,
        content="Synthetic protected goal",
        source_type=EvidenceSourceType.SYSTEM_FIXTURE,
        confirmed_by_user=True,
    )
    with service.database.connection() as connection:
        connection.execute(
            """
            CREATE TRIGGER abort_memory_delete
            BEFORE DELETE ON memory_records
            BEGIN
                SELECT RAISE(ABORT, 'forced rollback');
            END;
            """
        )
        connection.commit()
    with pytest.raises(MemoryStoreError):
        service.purge_subject("subject_alpha001")
    assert service.get_current_confirmed_profile("subject_alpha001") is not None
    assert service.memory_store.get("subject_alpha001", memory.memory_id) is not None


def test_schema_contains_no_transcript_or_vector_tables(service) -> None:
    with service.database.connection() as connection:
        names = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert names == {
        "schema_metadata",
        "profile_versions",
        "current_profiles",
        "memory_records",
    }
    assert not any("message" in name or "chat" in name or "vector" in name for name in names)
