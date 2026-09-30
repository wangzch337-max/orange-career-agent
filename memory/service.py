"""Small facade coordinating profile, memory, retrieval and privacy purge."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence
from uuid import uuid4

from data.models import EventType, EvidenceSourceType, UserProfile
from memory.base import MemoryStore, StructuredProfileStore
from memory.models import (
    MemoryEvent,
    MemoryRecord,
    MemoryRetrievalResult,
    MemoryStatus,
    MemoryType,
    ProfileSaveResult,
    PurgeResult,
)
from memory.retriever import DeterministicMemoryRetriever, MemoryRetriever
from memory.sqlite_store import (
    DEFAULT_MEMORY_DATABASE_PATH,
    SQLiteMemoryDatabase,
    SQLiteMemoryStore,
    SQLiteStructuredProfileStore,
)


class MemoryService:
    """Domain-facing facade; Agents never see SQL or SQLite schemas."""

    def __init__(
        self,
        *,
        profile_store: StructuredProfileStore,
        memory_store: MemoryStore,
        retriever: MemoryRetriever,
        database: SQLiteMemoryDatabase,
    ) -> None:
        self.profile_store = profile_store
        self.memory_store = memory_store
        self.retriever = retriever
        self.database = database
        self.events: list[MemoryEvent] = []

    def save_confirmed_profile(
        self, subject_id: str, profile: UserProfile
    ) -> ProfileSaveResult:
        result = self.profile_store.save_confirmed_profile(subject_id, profile)
        self._record(
            EventType.MEMORY_PROFILE_SAVED,
            subject_id,
            "Confirmed profile version persisted idempotently.",
            profile_version=profile.version,
            metadata={"created": result.created, "current": result.current},
        )
        return result

    def get_current_confirmed_profile(self, subject_id: str) -> UserProfile | None:
        return self.profile_store.get_current_confirmed_profile(subject_id)

    def create_candidate(
        self,
        *,
        subject_id: str,
        memory_type: MemoryType,
        content: str,
        source_type: EvidenceSourceType,
        evidence_refs: Sequence[str] = (),
        confidence: float | None = None,
        metadata: Mapping[str, object] | None = None,
        memory_id: str | None = None,
    ) -> MemoryRecord:
        record = self.memory_store.create_candidate(
            subject_id=subject_id,
            memory_type=memory_type,
            content=content,
            source_type=source_type,
            evidence_refs=evidence_refs,
            confidence=confidence,
            metadata=metadata,
            memory_id=memory_id,
        )
        self._record(
            EventType.MEMORY_CANDIDATE_CREATED,
            subject_id,
            "Candidate memory created without authoritative status.",
            memory=record,
        )
        return record

    def create_confirmed(
        self,
        *,
        subject_id: str,
        memory_type: MemoryType,
        content: str,
        source_type: EvidenceSourceType,
        confirmed_by_user: bool,
        evidence_refs: Sequence[str] = (),
        confidence: float | None = None,
        metadata: Mapping[str, object] | None = None,
        memory_id: str | None = None,
    ) -> MemoryRecord:
        record = self.memory_store.create_confirmed(
            subject_id=subject_id,
            memory_type=memory_type,
            content=content,
            source_type=source_type,
            confirmed_by_user=confirmed_by_user,
            evidence_refs=evidence_refs,
            confidence=confidence,
            metadata=metadata,
            memory_id=memory_id,
        )
        self._record(
            EventType.MEMORY_CONFIRMED,
            subject_id,
            "Explicitly confirmed memory created.",
            memory=record,
        )
        return record

    def record_user_feedback(
        self,
        subject_id: str,
        content: str,
        *,
        confirmed_by_user: bool,
        metadata: Mapping[str, object] | None = None,
    ) -> MemoryRecord:
        if confirmed_by_user:
            return self.create_confirmed(
                subject_id=subject_id,
                memory_type=MemoryType.USER_FEEDBACK,
                content=content,
                source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
                confirmed_by_user=True,
                metadata=metadata,
            )
        return self.create_candidate(
            subject_id=subject_id,
            memory_type=MemoryType.USER_FEEDBACK,
            content=content,
            source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
            metadata=metadata,
        )

    def confirm_candidate(
        self, subject_id: str, memory_id: str, *, confirmed_by_user: bool
    ) -> MemoryRecord:
        record = self.memory_store.confirm(
            subject_id, memory_id, confirmed_by_user=confirmed_by_user
        )
        self._record(
            EventType.MEMORY_CONFIRMED,
            subject_id,
            "Candidate memory explicitly confirmed.",
            memory=record,
        )
        return record

    def supersede(
        self,
        subject_id: str,
        memory_id: str,
        *,
        content: str,
        source_type: EvidenceSourceType,
        confirmed_by_user: bool,
        evidence_refs: Sequence[str] = (),
        confidence: float | None = None,
        metadata: Mapping[str, object] | None = None,
        new_memory_id: str | None = None,
    ) -> MemoryRecord:
        record = self.memory_store.supersede(
            subject_id,
            memory_id,
            content=content,
            source_type=source_type,
            confirmed_by_user=confirmed_by_user,
            evidence_refs=evidence_refs,
            confidence=confidence,
            metadata=metadata,
            new_memory_id=new_memory_id,
        )
        self._record(
            EventType.MEMORY_SUPERSEDED,
            subject_id,
            "Confirmed memory superseded while history was preserved.",
            memory=record,
        )
        return record

    def archive(self, subject_id: str, memory_id: str) -> MemoryRecord:
        record = self.memory_store.archive(subject_id, memory_id)
        self._record(
            EventType.MEMORY_ARCHIVED,
            subject_id,
            "Memory archived and excluded from active authority.",
            memory=record,
        )
        return record

    def retrieve(
        self,
        subject_id: str,
        query: str,
        *,
        memory_types: Sequence[MemoryType] | None = None,
        metadata_filters: Mapping[str, object] | None = None,
        include_history: bool = False,
        statuses: Sequence[MemoryStatus] | None = None,
        limit: int = 10,
    ) -> list[MemoryRetrievalResult]:
        results = self.retriever.retrieve(
            subject_id,
            query,
            memory_types=memory_types,
            metadata_filters=metadata_filters,
            include_history=include_history,
            statuses=statuses,
            limit=limit,
        )
        self._record(
            EventType.MEMORY_RETRIEVED,
            subject_id,
            "Deterministic lexical memory retrieval completed.",
            metadata={
                "result_count": len(results),
                "include_history": include_history,
            },
        )
        return results

    def purge_subject(self, subject_id: str) -> PurgeResult:
        result = self.database.purge_subject(subject_id)
        self._record(
            EventType.MEMORY_SUBJECT_PURGED,
            subject_id,
            "Subject-owned long-term memory was hard-purged transactionally.",
            metadata={
                "profile_versions_deleted": result.profile_versions_deleted,
                "memory_records_deleted": result.memory_records_deleted,
            },
        )
        return result

    def _record(
        self,
        event_type: EventType,
        subject_id: str,
        summary: str,
        *,
        memory: MemoryRecord | None = None,
        profile_version: int | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        safe_metadata = dict(metadata or {})
        if memory is not None:
            safe_metadata.update(
                memory_type=memory.memory_type.value,
                status=memory.status.value,
            )
        self.events.append(
            MemoryEvent(
                event_id=f"memory_event_{uuid4().hex}",
                event_type=event_type,
                component="MemoryService",
                summary=summary,
                safe_metadata=safe_metadata,
                subject_id=subject_id,
                memory_id=memory.memory_id if memory else None,
                profile_version=profile_version,
            )
        )


def build_sqlite_memory_service(
    path: Path = DEFAULT_MEMORY_DATABASE_PATH,
) -> MemoryService:
    database = SQLiteMemoryDatabase(path)
    profile_store = SQLiteStructuredProfileStore(database)
    memory_store = SQLiteMemoryStore(database)
    return MemoryService(
        profile_store=profile_store,
        memory_store=memory_store,
        retriever=DeterministicMemoryRetriever(memory_store),
        database=database,
    )
