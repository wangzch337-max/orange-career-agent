"""Curated MemoryRecord lifecycle, authority and isolation tests."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from data.models import EvidenceSourceType
from memory.base import MemoryStore
from memory.errors import InvalidMemoryTransitionError, MemoryConflictError
from memory.models import MemoryRecord, MemoryStatus, MemoryType
from memory.sqlite_store import SQLiteMemoryDatabase, SQLiteMemoryStore


@pytest.fixture
def memory_store(tmp_path):
    store = SQLiteMemoryStore(SQLiteMemoryDatabase(tmp_path / "memory.sqlite3"))
    assert isinstance(store, MemoryStore)
    return store


def test_memory_taxonomies_are_small_and_explicit() -> None:
    assert {item.value for item in MemoryType} == {
        "profile_signal",
        "career_preference",
        "goal",
        "project_evidence",
        "course_evidence",
        "user_feedback",
        "career_insight",
    }
    assert {item.value for item in MemoryStatus} == {
        "candidate",
        "confirmed",
        "superseded",
        "archived",
    }


def test_memory_record_requires_aware_time_and_deduplicates_evidence() -> None:
    with pytest.raises(ValidationError):
        MemoryRecord(
            memory_id="memory_synthetic001",
            subject_id="subject_synthetic001",
            memory_type=MemoryType.GOAL,
            status=MemoryStatus.CANDIDATE,
            content="Synthetic goal",
            source_type=EvidenceSourceType.SYSTEM_FIXTURE,
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
    record = MemoryRecord(
        memory_id="memory_synthetic002",
        subject_id="subject_synthetic001",
        memory_type=MemoryType.GOAL,
        status=MemoryStatus.CANDIDATE,
        content="Synthetic goal",
        source_type=EvidenceSourceType.SYSTEM_FIXTURE,
        evidence_refs=["evidence_a", "evidence_b", "evidence_a"],
    )
    assert record.evidence_refs == ["evidence_a", "evidence_b"]


def test_candidate_and_confirmed_creation_have_explicit_authority(memory_store) -> None:
    candidate = memory_store.create_candidate(
        subject_id="subject_alpha001",
        memory_type=MemoryType.CAREER_INSIGHT,
        content="Model-derived synthetic possibility",
        source_type=EvidenceSourceType.MODEL_INFERENCE,
        confidence=0.99,
    )
    assert candidate.status == MemoryStatus.CANDIDATE
    assert memory_store.list_active("subject_alpha001") == []
    with pytest.raises(InvalidMemoryTransitionError):
        memory_store.create_confirmed(
            subject_id="subject_alpha001",
            memory_type=MemoryType.CAREER_INSIGHT,
            content="High confidence still is not authority",
            source_type=EvidenceSourceType.MODEL_INFERENCE,
            confirmed_by_user=False,
            confidence=1.0,
        )


def test_candidate_confirmation_and_invalid_reverse_transition(memory_store) -> None:
    candidate = memory_store.create_candidate(
        subject_id="subject_alpha001",
        memory_type=MemoryType.USER_FEEDBACK,
        content="I am comfortable with documentation work.",
        source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
    )
    with pytest.raises(InvalidMemoryTransitionError):
        memory_store.confirm(
            "subject_alpha001", candidate.memory_id, confirmed_by_user=False
        )
    confirmed = memory_store.confirm(
        "subject_alpha001", candidate.memory_id, confirmed_by_user=True
    )
    assert confirmed.status == MemoryStatus.CONFIRMED
    assert [item.memory_id for item in memory_store.list_active("subject_alpha001")] == [
        candidate.memory_id
    ]
    archived = memory_store.archive("subject_alpha001", candidate.memory_id)
    assert archived.status == MemoryStatus.ARCHIVED
    with pytest.raises(InvalidMemoryTransitionError):
        memory_store.confirm(
            "subject_alpha001", candidate.memory_id, confirmed_by_user=True
        )


def test_supersede_preserves_history_and_replaces_active_memory(memory_store) -> None:
    old = memory_store.create_confirmed(
        subject_id="subject_alpha001",
        memory_type=MemoryType.CAREER_PREFERENCE,
        content="Primarily exploring Data roles",
        source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
        confirmed_by_user=True,
    )
    new = memory_store.supersede(
        "subject_alpha001",
        old.memory_id,
        content="Primarily exploring AI Application and AI Product roles",
        source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
        confirmed_by_user=True,
    )
    active = memory_store.list_active("subject_alpha001")
    history = memory_store.list_history("subject_alpha001")
    assert [item.memory_id for item in active] == [new.memory_id]
    old_in_history = next(item for item in history if item.memory_id == old.memory_id)
    assert old_in_history.status == MemoryStatus.SUPERSEDED
    assert new.supersedes_memory_id == old.memory_id


def test_archive_preserves_history_but_excludes_active(memory_store) -> None:
    record = memory_store.create_confirmed(
        subject_id="subject_alpha001",
        memory_type=MemoryType.GOAL,
        content="Build a synthetic portfolio project",
        source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
        confirmed_by_user=True,
    )
    archived = memory_store.archive("subject_alpha001", record.memory_id)
    assert archived.status == MemoryStatus.ARCHIVED
    assert memory_store.list_active("subject_alpha001") == []
    assert memory_store.list_history("subject_alpha001")[0].status == MemoryStatus.ARCHIVED


def test_memory_subject_isolation_even_with_similar_content(memory_store) -> None:
    first = memory_store.create_confirmed(
        subject_id="subject_alpha001",
        memory_type=MemoryType.GOAL,
        content="Explore AI roles",
        source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
        confirmed_by_user=True,
    )
    second = memory_store.create_confirmed(
        subject_id="subject_beta002",
        memory_type=MemoryType.GOAL,
        content="Explore AI roles",
        source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
        confirmed_by_user=True,
    )
    assert memory_store.get("subject_beta002", first.memory_id) is None
    assert [item.memory_id for item in memory_store.list_active("subject_alpha001")] == [
        first.memory_id
    ]
    assert [item.memory_id for item in memory_store.list_active("subject_beta002")] == [
        second.memory_id
    ]


def test_memory_identity_conflict_is_rejected(memory_store) -> None:
    memory_store.create_candidate(
        subject_id="subject_alpha001",
        memory_id="memory_opaque_conflict001",
        memory_type=MemoryType.GOAL,
        content="First content",
        source_type=EvidenceSourceType.SYSTEM_FIXTURE,
    )
    with pytest.raises(MemoryConflictError):
        memory_store.create_candidate(
            subject_id="subject_alpha001",
            memory_id="memory_opaque_conflict001",
            memory_type=MemoryType.GOAL,
            content="Conflicting content",
            source_type=EvidenceSourceType.SYSTEM_FIXTURE,
        )
