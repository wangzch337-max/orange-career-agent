"""Small facade coordinating profile, memory, retrieval and privacy purge."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence
from uuid import uuid4

from data.models import EventType, EvidenceSourceType, UserProfile
from memory.base import MemoryStore, StructuredProfileStore
from memory.context import MemoryContextBuilder
from memory.embeddings import EmbeddingProvider
from memory.errors import EmbeddingProviderError, VectorIndexError
from memory.models import (
    HybridMemoryRetrievalResult,
    MemoryContext,
    MemoryEvent,
    MemoryRecord,
    MemoryRetrievalResult,
    MemoryStatus,
    MemoryType,
    ProfileSaveResult,
    PurgeResult,
    SemanticMemoryRetrievalResult,
    VectorIndexRebuildResult,
    VectorSyncDiagnostic,
)
from memory.retriever import DeterministicMemoryRetriever, MemoryRetriever
from memory.semantic import HybridMemoryRetriever, SemanticMemoryRetriever
from memory.sqlite_store import (
    DEFAULT_MEMORY_DATABASE_PATH,
    SQLiteMemoryDatabase,
    SQLiteMemoryStore,
    SQLiteStructuredProfileStore,
)
from memory.vector_index import DEFAULT_VECTOR_DATABASE_PATH, MemoryVectorIndex
from storage.contracts import PurgeStorage, VectorStorage


from observability.instrumentation import observe
from observability.models import DiagnosticComponent as DC


class MemoryService:
    """Domain-facing facade; Agents never see SQL or SQLite schemas."""

    def __init__(
        self,
        *,
        profile_store: StructuredProfileStore,
        memory_store: MemoryStore,
        retriever: MemoryRetriever,
        database: PurgeStorage,
        vector_index: VectorStorage | None = None,
        semantic_retriever: SemanticMemoryRetriever | None = None,
        hybrid_retriever: HybridMemoryRetriever | None = None,
        context_builder: MemoryContextBuilder | None = None,
    ) -> None:
        self.profile_store = profile_store
        self.memory_store = memory_store
        self.retriever = retriever
        self.database = database
        self.vector_index = vector_index
        self.semantic_retriever = semantic_retriever
        self.hybrid_retriever = hybrid_retriever
        self.context_builder = context_builder
        self.events: list[MemoryEvent] = []
        self.vector_sync_diagnostics: list[VectorSyncDiagnostic] = []

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

    @observe(DC.MEMORY, "memory_candidate")
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

    @observe(DC.MEMORY, "memory_confirm")
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
        self._index_record(record, operation="create_confirmed")
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

    @observe(DC.MEMORY, "memory_confirm")
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
        self._index_record(record, operation="confirm_candidate")
        return record

    @observe(DC.MEMORY, "memory_supersede")
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
        self._remove_vector(
            subject_id,
            memory_id,
            operation="supersede_remove_previous",
        )
        self._index_record(record, operation="supersede_index_replacement")
        return record

    @observe(DC.MEMORY, "memory_archive")
    def archive(self, subject_id: str, memory_id: str) -> MemoryRecord:
        record = self.memory_store.archive(subject_id, memory_id)
        self._record(
            EventType.MEMORY_ARCHIVED,
            subject_id,
            "Memory archived and excluded from active authority.",
            memory=record,
        )
        self._remove_vector(subject_id, memory_id, operation="archive")
        return record

    @observe(DC.MEMORY_RETRIEVAL, "memory_retrieve")
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

    @observe(DC.MEMORY_RETRIEVAL, "memory_retrieve")
    def retrieve_semantic(
        self,
        subject_id: str,
        query: str,
        *,
        memory_types: Sequence[MemoryType] | None = None,
        top_k: int = 10,
    ) -> list[SemanticMemoryRetrievalResult]:
        if self.semantic_retriever is None:
            raise VectorIndexError("Semantic retrieval is not configured.")
        return self.semantic_retriever.retrieve(
            subject_id,
            query,
            memory_types=memory_types,
            top_k=top_k,
        )

    @observe(DC.MEMORY_RETRIEVAL, "memory_retrieve")
    def retrieve_hybrid(
        self,
        subject_id: str,
        query: str,
        *,
        memory_types: Sequence[MemoryType] | None = None,
        top_k: int = 10,
    ) -> list[HybridMemoryRetrievalResult]:
        if self.hybrid_retriever is None:
            raise VectorIndexError("Hybrid retrieval is not configured.")
        return self.hybrid_retriever.retrieve(
            subject_id,
            query,
            memory_types=memory_types,
            top_k=top_k,
        )

    @observe(DC.MEMORY_CONTEXT, "memory_context_build")
    def retrieve_context(
        self,
        subject_id: str,
        query: str,
        *,
        memory_types: Sequence[MemoryType] | None = None,
        top_k: int = 10,
    ) -> MemoryContext:
        if self.context_builder is None:
            raise VectorIndexError("Memory context retrieval is not configured.")
        results = self.retrieve_hybrid(
            subject_id,
            query,
            memory_types=memory_types,
            top_k=top_k,
        )
        return self.context_builder.build(subject_id, results)

    @observe(DC.VECTOR_INDEX, "vector_rebuild")
    def rebuild_subject_index(self, subject_id: str) -> VectorIndexRebuildResult:
        if self.vector_index is None:
            raise VectorIndexError("Derived vector index is not configured.")
        return self.vector_index.rebuild_subject_index(subject_id, self.memory_store)

    @observe(DC.MEMORY, "memory_purge")
    def purge_subject(self, subject_id: str) -> PurgeResult:
        result = self.database.purge_subject(subject_id)
        vector_deleted = 0
        cleanup_required = False
        if self.vector_index is not None:
            try:
                vector_deleted = self.vector_index.purge_subject(subject_id)
            except VectorIndexError:
                cleanup_required = True
                self.vector_sync_diagnostics.append(
                    VectorSyncDiagnostic(
                        operation="purge_subject",
                        subject_id=subject_id,
                        cleanup_required=True,
                    )
                )
        result = result.model_copy(
            update={
                "vector_records_deleted": vector_deleted,
                "vector_cleanup_required": cleanup_required,
            }
        )
        self._record(
            EventType.MEMORY_SUBJECT_PURGED,
            subject_id,
            "Subject-owned long-term memory was hard-purged transactionally.",
            metadata={
                "profile_versions_deleted": result.profile_versions_deleted,
                "memory_records_deleted": result.memory_records_deleted,
                "vector_records_deleted": result.vector_records_deleted,
                "vector_cleanup_required": result.vector_cleanup_required,
            },
        )
        return result

    def _index_record(self, record: MemoryRecord, *, operation: str) -> None:
        if self.vector_index is None:
            return
        try:
            self.vector_index.index_record(record)
        except (VectorIndexError, EmbeddingProviderError):
            self.vector_sync_diagnostics.append(
                VectorSyncDiagnostic(
                    operation=operation,
                    subject_id=record.subject_id,
                    memory_id=record.memory_id,
                    cleanup_required=False,
                )
            )

    def _remove_vector(
        self,
        subject_id: str,
        memory_id: str,
        *,
        operation: str,
    ) -> None:
        if self.vector_index is None:
            return
        try:
            self.vector_index.remove(memory_id)
        except VectorIndexError:
            self.vector_sync_diagnostics.append(
                VectorSyncDiagnostic(
                    operation=operation,
                    subject_id=subject_id,
                    memory_id=memory_id,
                    cleanup_required=True,
                )
            )

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


def build_semantic_memory_service(
    *,
    memory_path: Path = DEFAULT_MEMORY_DATABASE_PATH,
    vector_path: Path = DEFAULT_VECTOR_DATABASE_PATH,
    embedding_provider: EmbeddingProvider,
    context_max_records: int = 8,
    context_max_characters: int | None = 6000,
) -> MemoryService:
    """Build explicit Phase 7B retrieval without changing default MemoryService."""

    database = SQLiteMemoryDatabase(memory_path)
    profile_store = SQLiteStructuredProfileStore(database)
    memory_store = SQLiteMemoryStore(database)
    lexical = DeterministicMemoryRetriever(memory_store)
    vector_index = MemoryVectorIndex(vector_path, embedding_provider)
    semantic = SemanticMemoryRetriever(
        memory_store,
        vector_index,
        embedding_provider,
    )
    hybrid = HybridMemoryRetriever(lexical, semantic)
    return MemoryService(
        profile_store=profile_store,
        memory_store=memory_store,
        retriever=lexical,
        database=database,
        vector_index=vector_index,
        semantic_retriever=semantic,
        hybrid_retriever=hybrid,
        context_builder=MemoryContextBuilder(
            max_records=context_max_records,
            max_characters=context_max_characters,
        ),
    )
