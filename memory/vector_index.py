"""Disposable sqlite-vec index backed only by pysqlite3 connections."""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence
from uuid import uuid4

import pysqlite3
import sqlite_vec

from data.models import EventType, utc_now
from memory.base import MemoryStore
from memory.embeddings import EmbeddingProvider
from memory.errors import VectorIndexConfigurationError, VectorIndexError
from memory.models import (
    MemoryEvent,
    MemoryRecord,
    MemoryStatus,
    MemoryType,
    VectorIndexEntry,
    VectorIndexRebuildResult,
    VectorSearchHit,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VECTOR_DATABASE_PATH = (
    PROJECT_ROOT / "data" / "private" / "memory" / "orange_vectors.sqlite3"
)
VECTOR_INDEX_SCHEMA_VERSION = 1


def indexed_memory_text(record: MemoryRecord) -> str:
    """Return the sole deterministic text representation sent to embeddings."""

    return f"{record.memory_type.value}\n{record.content.strip()}"


def indexed_content_hash(record: MemoryRecord) -> str:
    return hashlib.sha256(indexed_memory_text(record).encode("utf-8")).hexdigest()


def is_index_eligible(record: MemoryRecord) -> bool:
    return record.status == MemoryStatus.CONFIRMED


class MemoryVectorIndex:
    """Derived acceleration layer; it never performs canonical lifecycle writes."""

    def __init__(self, path: Path, embedding_provider: EmbeddingProvider) -> None:
        self.path = path.resolve()
        self.embedding_provider = embedding_provider
        self.events: list[MemoryEvent] = []
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[pysqlite3.Connection]:
        connection = None
        try:
            connection = pysqlite3.connect(str(self.path))
            connection.row_factory = pysqlite3.Row
            connection.enable_load_extension(True)
            sqlite_vec.load(connection)
            connection.enable_load_extension(False)
            yield connection
        except pysqlite3.DatabaseError as exc:
            raise VectorIndexError("Derived vector-index operation failed.") from exc
        finally:
            if connection is not None:
                connection.close()

    def initialize(self) -> None:
        dimension = self.embedding_provider.dimension
        if dimension < 1:
            raise VectorIndexConfigurationError("Embedding dimension must be positive.")
        try:
            with self.connection() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS vector_schema_metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                    """
                )
                existing = {
                    row["key"]: row["value"]
                    for row in connection.execute(
                        "SELECT key, value FROM vector_schema_metadata"
                    ).fetchall()
                }
                expected = self._expected_configuration()
                if existing:
                    mismatches = {
                        key for key, value in expected.items() if existing.get(key) != value
                    }
                    if mismatches:
                        raise VectorIndexConfigurationError(
                            "Derived vector index embedding configuration mismatch."
                        )
                else:
                    connection.executemany(
                        "INSERT INTO vector_schema_metadata(key, value) VALUES (?, ?)",
                        tuple(expected.items()),
                    )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memory_vector_metadata (
                        memory_id TEXT PRIMARY KEY,
                        subject_id TEXT NOT NULL,
                        memory_type TEXT NOT NULL,
                        embedding_provider TEXT NOT NULL,
                        embedding_model_id TEXT NOT NULL,
                        embedding_dimension INTEGER NOT NULL,
                        content_hash TEXT NOT NULL,
                        indexed_at TEXT NOT NULL,
                        index_schema_version INTEGER NOT NULL,
                        embedding_normalization_version TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_vector_metadata_subject
                    ON memory_vector_metadata(subject_id, memory_type, memory_id)
                    """
                )
                connection.execute(
                    f"""
                    CREATE VIRTUAL TABLE IF NOT EXISTS memory_vectors USING vec0(
                        memory_id text primary key,
                        subject_id text partition key,
                        memory_type text,
                        embedding float[{dimension}] distance_metric=cosine
                    )
                    """
                )
                connection.commit()
        except VectorIndexConfigurationError:
            raise
        except VectorIndexError:
            raise
        except Exception as exc:
            raise VectorIndexError("Derived vector-index initialization failed.") from exc

    def schema_version(self) -> int:
        return int(self._schema_metadata()["schema_version"])

    def index_record(self, record: MemoryRecord) -> VectorIndexEntry:
        entries = self.index_records((record,))
        if not entries:
            raise ValueError("Only active confirmed MemoryRecords are index eligible.")
        return entries[0]

    def index_records(self, records: Sequence[MemoryRecord]) -> list[VectorIndexEntry]:
        values = tuple(records)
        if any(not is_index_eligible(record) for record in values):
            raise ValueError("Only active confirmed MemoryRecords are index eligible.")
        if not values:
            return []
        vectors = self.embedding_provider.embed_passages(
            [indexed_memory_text(record) for record in values]
        )
        indexed_at = utc_now()
        entries: list[VectorIndexEntry] = []
        try:
            with self.connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                for record, vector in zip(values, vectors, strict=True):
                    if vector.dimension != self.embedding_provider.dimension:
                        raise VectorIndexConfigurationError(
                            "Embedding output dimension does not match index configuration."
                        )
                    entry = VectorIndexEntry(
                        memory_id=record.memory_id,
                        subject_id=record.subject_id,
                        memory_type=record.memory_type,
                        embedding_provider=vector.provider_name,
                        embedding_model_id=vector.model_id,
                        embedding_dimension=vector.dimension,
                        content_hash=indexed_content_hash(record),
                        indexed_at=indexed_at,
                        index_schema_version=VECTOR_INDEX_SCHEMA_VERSION,
                        embedding_normalization_version=vector.normalization_version,
                    )
                    connection.execute(
                        "DELETE FROM memory_vectors WHERE memory_id = ?",
                        (record.memory_id,),
                    )
                    connection.execute(
                        "DELETE FROM memory_vector_metadata WHERE memory_id = ?",
                        (record.memory_id,),
                    )
                    connection.execute(
                        """
                        INSERT INTO memory_vectors(
                            memory_id, subject_id, memory_type, embedding
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (
                            record.memory_id,
                            record.subject_id,
                            record.memory_type.value,
                            sqlite_vec.serialize_float32(vector.values),
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO memory_vector_metadata(
                            memory_id, subject_id, memory_type,
                            embedding_provider, embedding_model_id,
                            embedding_dimension, content_hash, indexed_at,
                            index_schema_version, embedding_normalization_version
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            entry.memory_id,
                            entry.subject_id,
                            entry.memory_type.value,
                            entry.embedding_provider,
                            entry.embedding_model_id,
                            entry.embedding_dimension,
                            entry.content_hash,
                            entry.indexed_at.isoformat(),
                            entry.index_schema_version,
                            entry.embedding_normalization_version,
                        ),
                    )
                    entries.append(entry)
                connection.commit()
        except VectorIndexConfigurationError:
            raise
        except VectorIndexError:
            raise
        except Exception as exc:
            raise VectorIndexError("Memory vector indexing failed.") from exc
        for entry in entries:
            self._record(
                EventType.MEMORY_VECTOR_INDEXED,
                entry.subject_id,
                memory_id=entry.memory_id,
                metadata={
                    "model_id": entry.embedding_model_id,
                    "dimension": entry.embedding_dimension,
                    "index_schema_version": entry.index_schema_version,
                },
            )
        return entries

    def remove(self, memory_id: str) -> bool:
        existing = self.metadata_for(memory_id)
        if existing is None:
            return False
        try:
            with self.connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "DELETE FROM memory_vectors WHERE memory_id = ?", (memory_id,)
                )
                connection.execute(
                    "DELETE FROM memory_vector_metadata WHERE memory_id = ?", (memory_id,)
                )
                connection.commit()
        except VectorIndexError:
            raise
        except Exception as exc:
            raise VectorIndexError("Memory vector removal failed.") from exc
        self._record(
            EventType.MEMORY_VECTOR_REMOVED,
            existing.subject_id,
            memory_id=memory_id,
        )
        return True

    def clear_subject(self, subject_id: str) -> int:
        entries = self.list_entries(subject_id)
        try:
            with self.connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                for entry in entries:
                    connection.execute(
                        "DELETE FROM memory_vectors WHERE memory_id = ?",
                        (entry.memory_id,),
                    )
                connection.execute(
                    "DELETE FROM memory_vector_metadata WHERE subject_id = ?",
                    (subject_id,),
                )
                connection.commit()
        except VectorIndexError:
            raise
        except Exception as exc:
            raise VectorIndexError("Subject vector cleanup failed.") from exc
        return len(entries)

    def purge_subject(self, subject_id: str) -> int:
        return self.clear_subject(subject_id)

    def rebuild_subject_index(
        self, subject_id: str, memory_store: MemoryStore
    ) -> VectorIndexRebuildResult:
        cleared = self.clear_subject(subject_id)
        eligible = memory_store.list_active(subject_id)
        indexed = self.index_records(eligible)
        result = VectorIndexRebuildResult(
            subject_id=subject_id,
            cleared_count=cleared,
            eligible_count=len(eligible),
            indexed_count=len(indexed),
        )
        self._record(
            EventType.MEMORY_VECTOR_INDEX_REBUILT,
            subject_id,
            metadata={
                "cleared_count": result.cleared_count,
                "eligible_count": result.eligible_count,
                "indexed_count": result.indexed_count,
            },
        )
        return result

    def query(
        self,
        subject_id: str,
        query_vector: Sequence[float],
        *,
        top_k: int = 10,
        memory_types: Sequence[MemoryType] | None = None,
    ) -> list[VectorSearchHit]:
        if top_k < 1:
            raise ValueError("Vector retrieval top_k must be positive.")
        if len(query_vector) != self.embedding_provider.dimension:
            raise VectorIndexConfigurationError(
                "Query dimension does not match vector index configuration."
            )
        parameters = sqlite_vec.serialize_float32(list(query_vector))
        raw_hits: dict[str, float] = {}
        try:
            with self.connection() as connection:
                if memory_types:
                    for memory_type in memory_types:
                        rows = connection.execute(
                            """
                            SELECT memory_id, distance FROM memory_vectors
                            WHERE embedding MATCH ? AND k = ?
                              AND subject_id = ? AND memory_type = ?
                            ORDER BY distance
                            """,
                            (parameters, top_k, subject_id, memory_type.value),
                        ).fetchall()
                        for row in rows:
                            current = raw_hits.get(row["memory_id"])
                            if current is None or row["distance"] < current:
                                raw_hits[row["memory_id"]] = float(row["distance"])
                else:
                    rows = connection.execute(
                        """
                        SELECT memory_id, distance FROM memory_vectors
                        WHERE embedding MATCH ? AND k = ? AND subject_id = ?
                        ORDER BY distance
                        """,
                        (parameters, top_k, subject_id),
                    ).fetchall()
                    raw_hits = {
                        row["memory_id"]: float(row["distance"]) for row in rows
                    }
        except VectorIndexError:
            raise
        except Exception as exc:
            raise VectorIndexError("Subject-scoped vector query failed.") from exc
        hits: list[VectorSearchHit] = []
        for memory_id, distance in sorted(
            raw_hits.items(), key=lambda item: (item[1], item[0])
        )[:top_k]:
            entry = self.metadata_for(memory_id)
            if entry is not None and entry.subject_id == subject_id:
                hits.append(VectorSearchHit(entry=entry, distance=distance))
        return hits

    def metadata_for(self, memory_id: str) -> VectorIndexEntry | None:
        try:
            with self.connection() as connection:
                row = connection.execute(
                    "SELECT * FROM memory_vector_metadata WHERE memory_id = ?",
                    (memory_id,),
                ).fetchone()
        except VectorIndexError:
            raise
        except Exception as exc:
            raise VectorIndexError("Vector metadata lookup failed.") from exc
        return None if row is None else self._decode_entry(row)

    def list_entries(self, subject_id: str) -> list[VectorIndexEntry]:
        try:
            with self.connection() as connection:
                rows = connection.execute(
                    """
                    SELECT * FROM memory_vector_metadata
                    WHERE subject_id = ? ORDER BY indexed_at, memory_id
                    """,
                    (subject_id,),
                ).fetchall()
        except VectorIndexError:
            raise
        except Exception as exc:
            raise VectorIndexError("Subject vector metadata lookup failed.") from exc
        return [self._decode_entry(row) for row in rows]

    def count_subject(self, subject_id: str) -> int:
        return len(self.list_entries(subject_id))

    def _schema_metadata(self) -> dict[str, str]:
        try:
            with self.connection() as connection:
                return {
                    row["key"]: row["value"]
                    for row in connection.execute(
                        "SELECT key, value FROM vector_schema_metadata"
                    ).fetchall()
                }
        except VectorIndexError:
            raise
        except Exception as exc:
            raise VectorIndexError("Vector schema metadata lookup failed.") from exc

    def _expected_configuration(self) -> dict[str, str]:
        return {
            "schema_version": str(VECTOR_INDEX_SCHEMA_VERSION),
            "embedding_provider": self.embedding_provider.provider_name,
            "embedding_model_id": self.embedding_provider.model_id,
            "embedding_dimension": str(self.embedding_provider.dimension),
            "embedding_normalization_version": (
                self.embedding_provider.normalization_version
            ),
        }

    @staticmethod
    def _decode_entry(row) -> VectorIndexEntry:
        return VectorIndexEntry(
            memory_id=row["memory_id"],
            subject_id=row["subject_id"],
            memory_type=row["memory_type"],
            embedding_provider=row["embedding_provider"],
            embedding_model_id=row["embedding_model_id"],
            embedding_dimension=row["embedding_dimension"],
            content_hash=row["content_hash"],
            indexed_at=row["indexed_at"],
            index_schema_version=row["index_schema_version"],
            embedding_normalization_version=row[
                "embedding_normalization_version"
            ],
        )

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
                component="MemoryVectorIndex",
                summary="Derived vector index operation completed.",
                safe_metadata=dict(metadata or {}),
                subject_id=subject_id,
                memory_id=memory_id,
            )
        )
