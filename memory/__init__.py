"""Curated authoritative Memory plus explicit Phase 7B retrieval."""

from memory.base import MemoryStore, StructuredProfileStore
from memory.context import MemoryContextBuilder
from memory.embeddings import (
    DEFAULT_LOCAL_MODEL_CACHE,
    DEFAULT_LOCAL_MODEL_ID,
    EmbeddingProvider,
    FakeEmbeddingProvider,
    LocalEmbeddingProvider,
)
from memory.models import (
    HybridMemoryRetrievalResult,
    MemoryContext,
    MemoryRecord,
    MemoryRetrievalResult,
    MemoryStatus,
    MemoryType,
    ProfileReference,
    ProfileSaveResult,
    PurgeResult,
    SemanticMemoryRetrievalResult,
    VectorIndexEntry,
    new_memory_id,
    new_subject_id,
)
from memory.retriever import DeterministicMemoryRetriever, MemoryRetriever
from memory.semantic import HybridMemoryRetriever, SemanticMemoryRetriever
from memory.service import (
    MemoryService,
    build_semantic_memory_service,
    build_sqlite_memory_service,
)
from memory.sqlite_store import (
    DEFAULT_MEMORY_DATABASE_PATH,
    MEMORY_SCHEMA_VERSION,
    SQLiteMemoryDatabase,
    SQLiteMemoryStore,
    SQLiteStructuredProfileStore,
)
from memory.vector_index import (
    DEFAULT_VECTOR_DATABASE_PATH,
    VECTOR_INDEX_SCHEMA_VERSION,
    MemoryVectorIndex,
)

__all__ = [
    "DEFAULT_MEMORY_DATABASE_PATH",
    "DEFAULT_VECTOR_DATABASE_PATH",
    "DEFAULT_LOCAL_MODEL_CACHE",
    "DEFAULT_LOCAL_MODEL_ID",
    "MEMORY_SCHEMA_VERSION",
    "DeterministicMemoryRetriever",
    "EmbeddingProvider",
    "FakeEmbeddingProvider",
    "HybridMemoryRetriever",
    "HybridMemoryRetrievalResult",
    "LocalEmbeddingProvider",
    "MemoryContext",
    "MemoryContextBuilder",
    "MemoryRecord",
    "MemoryRetrievalResult",
    "MemoryRetriever",
    "MemoryService",
    "MemoryStatus",
    "MemoryStore",
    "MemoryType",
    "MemoryVectorIndex",
    "ProfileReference",
    "ProfileSaveResult",
    "PurgeResult",
    "SemanticMemoryRetriever",
    "SemanticMemoryRetrievalResult",
    "SQLiteMemoryDatabase",
    "SQLiteMemoryStore",
    "SQLiteStructuredProfileStore",
    "StructuredProfileStore",
    "VECTOR_INDEX_SCHEMA_VERSION",
    "VectorIndexEntry",
    "build_semantic_memory_service",
    "build_sqlite_memory_service",
    "new_memory_id",
    "new_subject_id",
]
