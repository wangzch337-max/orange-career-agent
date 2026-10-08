"""Process-only derived index; canonical retrieval/consumer policies are reused."""

from copy import deepcopy
from math import sqrt
from struct import pack, unpack
from memory.errors import VectorIndexConfigurationError
from memory.models import VectorIndexEntry, VectorSearchHit, VectorIndexRebuildResult
from memory.vector_index import indexed_memory_text, indexed_content_hash, is_index_eligible, VECTOR_INDEX_SCHEMA_VERSION
from data.models import utc_now
from storage.contracts import StorageLease


def float32(values):
    return tuple(unpack("f", pack("f", v))[0] for v in values)


class EphemeralVectorIndex:
    def __init__(self, embedding_provider, lease=None):
        self.embedding_provider = embedding_provider
        self.lease = lease or StorageLease()
        if embedding_provider.dimension < 1: raise VectorIndexConfigurationError("Invalid embedding dimension.")
        self._entries, self._vectors = {}, {}

    def clear(self): self._entries.clear(); self._vectors.clear()

    def schema_version(self):
        self.lease.check(); return VECTOR_INDEX_SCHEMA_VERSION

    def index_record(self, record):
        entries = self.index_records((record,))
        if not entries: raise ValueError("Only active confirmed MemoryRecords are index eligible.")
        return entries[0]

    def index_records(self, records):
        with self.lease.lock:
            self.lease.check(); records = tuple(records)
            if any(not is_index_eligible(r) for r in records): raise ValueError("Only active confirmed MemoryRecords are index eligible.")
            if not records: return []
            vectors = self.embedding_provider.embed_passages([indexed_memory_text(r) for r in records])
            entries, values = [], []
            for record, vector in zip(records, vectors, strict=True):
                if vector.dimension != self.embedding_provider.dimension:
                    raise VectorIndexConfigurationError("Embedding output dimension mismatch.")
                entries.append(VectorIndexEntry(memory_id=record.memory_id, subject_id=record.subject_id,
                    memory_type=record.memory_type, embedding_provider=vector.provider_name, embedding_model_id=vector.model_id,
                    embedding_dimension=vector.dimension, content_hash=indexed_content_hash(record), indexed_at=utc_now(),
                    index_schema_version=VECTOR_INDEX_SCHEMA_VERSION, embedding_normalization_version=vector.normalization_version))
                values.append(float32(vector.values))
            self.lease.check()
            for entry, vector in zip(entries, values): self._entries[entry.memory_id], self._vectors[entry.memory_id] = entry, vector
            return deepcopy(entries)

    def remove(self, memory_id):
        with self.lease.lock:
            self.lease.check(); existed = memory_id in self._entries
            self._entries.pop(memory_id, None); self._vectors.pop(memory_id, None)
            return existed

    def metadata_for(self, memory_id):
        with self.lease.lock:
            self.lease.check(); return deepcopy(self._entries.get(memory_id))

    def list_entries(self, subject_id):
        with self.lease.lock:
            self.lease.check()
            return deepcopy(sorted((e for e in self._entries.values() if e.subject_id == subject_id), key=lambda e: (e.indexed_at, e.memory_id)))

    def count_subject(self, subject_id): return len(self.list_entries(subject_id))

    def clear_subject(self, subject_id):
        with self.lease.lock:
            entries = self.list_entries(subject_id)
            for entry in entries: self.remove(entry.memory_id)
            return len(entries)

    def purge_subject(self, subject_id): return self.clear_subject(subject_id)

    def rebuild_subject_index(self, subject_id, memory_store):
        with self.lease.lock:
            cleared = self.clear_subject(subject_id); records = memory_store.list_active(subject_id)
            indexed = self.index_records(records)
            return VectorIndexRebuildResult(subject_id=subject_id, cleared_count=cleared, eligible_count=len(records), indexed_count=len(indexed))

    def query(self, subject_id, query_vector, *, top_k=10, memory_types=None):
        with self.lease.lock:
            self.lease.check()
            if top_k < 1: raise ValueError("Vector retrieval top_k must be positive.")
            if len(query_vector) != self.embedding_provider.dimension: raise VectorIndexConfigurationError("Query dimension mismatch.")
            q = float32(query_vector); qnorm = sqrt(sum(v*v for v in q)); hits = []
            for entry in self.list_entries(subject_id):
                if memory_types and entry.memory_type not in memory_types: continue
                v = self._vectors[entry.memory_id]; norm = sqrt(sum(x*x for x in v))
                distance = 1 - sum(a*b for a, b in zip(q, v)) / (qnorm*norm) if qnorm and norm else 1.0
                hits.append(VectorSearchHit(entry=entry, distance=max(0.0, min(2.0, distance))))
            return sorted(hits, key=lambda h: (h.distance, h.entry.memory_id))[:top_k]
