"""Authority-preserving semantic and deterministic hybrid retrieval."""

from __future__ import annotations

from collections.abc import Sequence
from time import perf_counter
from uuid import uuid4

from data.models import EventType
from memory.base import MemoryStore
from memory.embeddings import EmbeddingProvider
from memory.errors import EmbeddingProviderError, VectorIndexError
from memory.models import (
    HybridMemoryRetrievalResult,
    MemoryEvent,
    MemoryStatus,
    MemoryType,
    SemanticMemoryRetrievalResult,
    VectorSearchHit,
)
from memory.retriever import DeterministicMemoryRetriever
from memory.vector_index import MemoryVectorIndex, indexed_content_hash


RRF_CONSTANT = 60


class SemanticMemoryRetriever:
    """Resolve vector candidates through canonical Memory before returning them."""

    def __init__(
        self,
        memory_store: MemoryStore,
        vector_index: MemoryVectorIndex,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.memory_store = memory_store
        self.vector_index = vector_index
        self.embedding_provider = embedding_provider
        self.events: list[MemoryEvent] = []

    def retrieve(
        self,
        subject_id: str,
        query: str,
        *,
        memory_types: Sequence[MemoryType] | None = None,
        top_k: int = 10,
    ) -> list[SemanticMemoryRetrievalResult]:
        if not query.strip():
            raise ValueError("Semantic retrieval query cannot be empty.")
        if top_k < 1:
            raise ValueError("Semantic retrieval top_k must be positive.")
        started = perf_counter()
        query_vector = self.embedding_provider.embed_query(query)
        self._record(
            EventType.MEMORY_EMBEDDING_CREATED,
            subject_id,
            metadata={
                "purpose": "query",
                "model_id": query_vector.model_id,
                "dimension": query_vector.dimension,
            },
        )
        # Fetch every derived row for this subject so stale rows cannot consume
        # the caller's authoritative top_k budget before canonical validation.
        candidate_limit = max(top_k, self.vector_index.count_subject(subject_id))
        hits = self.vector_index.query(
            subject_id,
            query_vector.values,
            top_k=candidate_limit,
            memory_types=memory_types,
        )
        accepted: list[tuple[VectorSearchHit, object]] = []
        stale_count = 0
        allowed_types = set(memory_types or ())
        for hit in hits:
            record = self.memory_store.get(subject_id, hit.entry.memory_id)
            active = (
                record is not None
                and record.subject_id == subject_id
                and record.status == MemoryStatus.CONFIRMED
                and (not allowed_types or record.memory_type in allowed_types)
                and indexed_content_hash(record) == hit.entry.content_hash
            )
            if not active:
                stale_count += 1
                self._record(
                    EventType.MEMORY_VECTOR_STALE_FILTERED,
                    subject_id,
                    memory_id=hit.entry.memory_id,
                    metadata={"reason": "canonical_revalidation_failed"},
                )
                continue
            accepted.append((hit, record))
        results = [
            SemanticMemoryRetrievalResult(
                memory=record,
                semantic_rank=rank,
                semantic_distance=hit.distance,
                embedding_provider=hit.entry.embedding_provider,
                embedding_model_id=hit.entry.embedding_model_id,
            )
            for rank, (hit, record) in enumerate(accepted[:top_k], start=1)
        ]
        self._record(
            EventType.MEMORY_SEMANTIC_RETRIEVED,
            subject_id,
            metadata={
                "result_count": len(results),
                "stale_filtered_count": stale_count,
                "model_id": self.embedding_provider.model_id,
                "duration_ms": round((perf_counter() - started) * 1000),
            },
        )
        return results

    def _record(
        self,
        event_type: EventType,
        subject_id: str,
        *,
        memory_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self.events.append(
            MemoryEvent(
                event_id=f"memory_event_{uuid4().hex}",
                event_type=event_type,
                component="SemanticMemoryRetriever",
                summary="Semantic memory retrieval step completed.",
                safe_metadata=dict(metadata or {}),
                subject_id=subject_id,
                memory_id=memory_id,
            )
        )


class HybridMemoryRetriever:
    """Fuse lexical and semantic ranks with fixed one-based RRF."""

    def __init__(
        self,
        lexical_retriever: DeterministicMemoryRetriever,
        semantic_retriever: SemanticMemoryRetriever,
        *,
        rrf_constant: int = RRF_CONSTANT,
        allow_lexical_fallback: bool = True,
    ) -> None:
        if rrf_constant < 1:
            raise ValueError("RRF constant must be positive.")
        self.lexical_retriever = lexical_retriever
        self.semantic_retriever = semantic_retriever
        self.rrf_constant = rrf_constant
        self.allow_lexical_fallback = allow_lexical_fallback
        self.last_mode = "hybrid"
        self.events: list[MemoryEvent] = []

    def retrieve(
        self,
        subject_id: str,
        query: str,
        *,
        memory_types: Sequence[MemoryType] | None = None,
        top_k: int = 10,
    ) -> list[HybridMemoryRetrievalResult]:
        if top_k < 1:
            raise ValueError("Hybrid retrieval top_k must be positive.")
        source_limit = max(top_k * 2, top_k)
        lexical = self.lexical_retriever.retrieve(
            subject_id,
            query,
            memory_types=memory_types,
            limit=source_limit,
        )
        try:
            semantic = self.semantic_retriever.retrieve(
                subject_id,
                query,
                memory_types=memory_types,
                top_k=source_limit,
            )
            self.last_mode = "hybrid"
        except (VectorIndexError, EmbeddingProviderError):
            if not self.allow_lexical_fallback:
                raise
            semantic = []
            self.last_mode = "lexical_only_fallback"

        by_id: dict[str, dict[str, object]] = {}
        for rank, result in enumerate(lexical, start=1):
            by_id[result.memory.memory_id] = {
                "memory": result.memory,
                "lexical_rank": rank,
                "semantic_rank": None,
            }
        for result in semantic:
            entry = by_id.setdefault(
                result.memory.memory_id,
                {
                    "memory": result.memory,
                    "lexical_rank": None,
                    "semantic_rank": None,
                },
            )
            entry["semantic_rank"] = result.semantic_rank

        fused: list[tuple[float, int, object, int | None, int | None]] = []
        for entry in by_id.values():
            lexical_rank = entry["lexical_rank"]
            semantic_rank = entry["semantic_rank"]
            score = sum(
                1.0 / (self.rrf_constant + rank)
                for rank in (lexical_rank, semantic_rank)
                if isinstance(rank, int)
            )
            best_rank = min(
                rank
                for rank in (lexical_rank, semantic_rank)
                if isinstance(rank, int)
            )
            fused.append(
                (score, best_rank, entry["memory"], lexical_rank, semantic_rank)
            )
        fused.sort(
            key=lambda item: (
                -item[0],
                item[1],
                item[2].created_at.isoformat(),
                item[2].memory_id,
            )
        )
        results = [
            HybridMemoryRetrievalResult(
                memory=memory,
                lexical_rank=lexical_rank,
                semantic_rank=semantic_rank,
                fusion_rank=fusion_rank,
                rrf_score=score,
            )
            for fusion_rank, (
                score,
                _,
                memory,
                lexical_rank,
                semantic_rank,
            ) in enumerate(fused[:top_k], start=1)
        ]
        self.events.append(
            MemoryEvent(
                event_id=f"memory_event_{uuid4().hex}",
                event_type=EventType.MEMORY_HYBRID_RETRIEVED,
                component="HybridMemoryRetriever",
                summary="Deterministic reciprocal-rank fusion completed.",
                safe_metadata={
                    "result_count": len(results),
                    "rrf_constant": self.rrf_constant,
                    "mode": self.last_mode,
                },
                subject_id=subject_id,
            )
        )
        return results
