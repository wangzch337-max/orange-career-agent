"""Standard-library SQLite persistence for Phase 7A long-term memory."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Mapping, Sequence

from pydantic import ValidationError

from data.models import EvidenceSourceType, ProfileStatus, UserProfile, utc_now
from memory.base import MemoryStore, StructuredProfileStore
from memory.errors import (
    CorruptStoredProfileError,
    InvalidMemoryTransitionError,
    MemoryConflictError,
    MemoryNotFoundError,
    MemoryStoreError,
    ProfileVersionConflictError,
)
from memory.models import (
    MemoryRecord,
    MemoryStatus,
    MemoryType,
    ProfileReference,
    ProfileSaveResult,
    PurgeResult,
    new_memory_id,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MEMORY_DATABASE_PATH = (
    PROJECT_ROOT / "data" / "private" / "memory" / "orange_memory.sqlite3"
)
MEMORY_SCHEMA_VERSION = 1


def _validate_subject_id(subject_id: str) -> str:
    value = subject_id.strip()
    if not value or "@" in value or any(character.isspace() for character in value):
        raise ValueError("subject_id must be an opaque non-contact identifier")
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _hash_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _profile_semantic_payload(profile: UserProfile) -> dict[str, object]:
    payload = profile.model_dump(mode="json")
    # Confirmation timestamps may be regenerated if a resumable graph node is
    # replayed; they do not alter the confirmed profile's semantic content.
    payload.pop("confirmed_at", None)
    payload.pop("updated_at", None)
    return payload


def _memory_semantic_payload(record: MemoryRecord) -> dict[str, object]:
    payload = record.model_dump(mode="json")
    # Lifecycle status is mutable through explicit transitions; it is not part
    # of the record's immutable semantic identity.
    payload.pop("status", None)
    payload.pop("created_at", None)
    payload.pop("updated_at", None)
    return payload


class SQLiteMemoryDatabase:
    """Connection/schema owner shared by profile and curated-memory stores."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        try:
            with self.connection() as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS schema_metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS profile_versions (
                        subject_id TEXT NOT NULL,
                        profile_id TEXT NOT NULL,
                        version INTEGER NOT NULL CHECK (version >= 1),
                        payload_json TEXT NOT NULL,
                        semantic_hash TEXT NOT NULL,
                        stored_at TEXT NOT NULL,
                        PRIMARY KEY (subject_id, profile_id, version)
                    );

                    CREATE TABLE IF NOT EXISTS current_profiles (
                        subject_id TEXT PRIMARY KEY,
                        profile_id TEXT NOT NULL,
                        version INTEGER NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY (subject_id, profile_id, version)
                            REFERENCES profile_versions(subject_id, profile_id, version)
                            ON DELETE RESTRICT
                    );

                    CREATE TABLE IF NOT EXISTS memory_records (
                        memory_id TEXT PRIMARY KEY,
                        subject_id TEXT NOT NULL,
                        memory_type TEXT NOT NULL,
                        status TEXT NOT NULL,
                        content TEXT NOT NULL,
                        source_type TEXT NOT NULL,
                        evidence_refs_json TEXT NOT NULL,
                        confidence REAL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        supersedes_memory_id TEXT,
                        metadata_json TEXT NOT NULL,
                        semantic_hash TEXT NOT NULL,
                        FOREIGN KEY (supersedes_memory_id)
                            REFERENCES memory_records(memory_id)
                            ON DELETE RESTRICT
                    );

                    CREATE INDEX IF NOT EXISTS idx_profile_versions_subject
                        ON profile_versions(subject_id, profile_id, version);
                    CREATE INDEX IF NOT EXISTS idx_memory_subject_status_type
                        ON memory_records(subject_id, status, memory_type);
                    CREATE INDEX IF NOT EXISTS idx_memory_subject_created
                        ON memory_records(subject_id, created_at, memory_id);
                    """
                )
                existing = connection.execute(
                    "SELECT value FROM schema_metadata WHERE key = ?",
                    ("schema_version",),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        "INSERT INTO schema_metadata(key, value) VALUES (?, ?)",
                        ("schema_version", str(MEMORY_SCHEMA_VERSION)),
                    )
                elif existing["value"] != str(MEMORY_SCHEMA_VERSION):
                    raise MemoryStoreError("Unsupported memory database schema version.")
                connection.commit()
        except sqlite3.DatabaseError as exc:
            raise MemoryStoreError("Memory database initialization failed.") from exc

    def schema_version(self) -> int:
        try:
            with self.connection() as connection:
                row = connection.execute(
                    "SELECT value FROM schema_metadata WHERE key = ?",
                    ("schema_version",),
                ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise MemoryStoreError("Memory schema version lookup failed.") from exc
        if row is None:
            raise MemoryStoreError("Memory database schema version is missing.")
        return int(row["value"])

    def purge_subject(self, subject_id: str) -> PurgeResult:
        subject = _validate_subject_id(subject_id)
        try:
            with self.connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                pointer_count = connection.execute(
                    "DELETE FROM current_profiles WHERE subject_id = ?", (subject,)
                ).rowcount
                profile_count = connection.execute(
                    "DELETE FROM profile_versions WHERE subject_id = ?", (subject,)
                ).rowcount
                connection.execute(
                    """
                    UPDATE memory_records
                    SET supersedes_memory_id = NULL
                    WHERE subject_id = ? AND supersedes_memory_id IS NOT NULL
                    """,
                    (subject,),
                )
                memory_count = connection.execute(
                    "DELETE FROM memory_records WHERE subject_id = ?", (subject,)
                ).rowcount
                connection.commit()
        except sqlite3.DatabaseError as exc:
            raise MemoryStoreError("Memory purge transaction failed.") from exc
        return PurgeResult(
            subject_id=subject,
            profile_versions_deleted=profile_count,
            current_pointer_deleted=pointer_count,
            memory_records_deleted=memory_count,
        )


class SQLiteStructuredProfileStore(StructuredProfileStore):
    def __init__(self, database: SQLiteMemoryDatabase) -> None:
        self.database = database

    def save_confirmed_profile(
        self, subject_id: str, profile: UserProfile
    ) -> ProfileSaveResult:
        subject = _validate_subject_id(subject_id)
        if not profile.confirmed or profile.status != ProfileStatus.CONFIRMED:
            raise ProfileVersionConflictError(
                "Only a confirmed UserProfile may enter the authoritative store."
            )
        payload_json = _canonical_json(profile.model_dump(mode="json"))
        semantic_hash = _hash_json(_profile_semantic_payload(profile))
        reference = ProfileReference(
            subject_id=subject,
            profile_id=profile.profile_id,
            version=profile.version,
        )
        try:
            with self.database.connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    """
                    SELECT payload_json, semantic_hash
                    FROM profile_versions
                    WHERE subject_id = ? AND profile_id = ? AND version = ?
                    """,
                    (subject, profile.profile_id, profile.version),
                ).fetchone()
                current = connection.execute(
                    "SELECT profile_id, version FROM current_profiles WHERE subject_id = ?",
                    (subject,),
                ).fetchone()
                if existing is not None:
                    if existing["semantic_hash"] != semantic_hash:
                        raise ProfileVersionConflictError(
                            "An immutable profile identity has conflicting content."
                        )
                    stored = self._decode_profile(existing["payload_json"])
                    connection.commit()
                    return ProfileSaveResult(
                        profile=stored,
                        reference=reference,
                        created=False,
                        current=(
                            current is not None
                            and current["profile_id"] == profile.profile_id
                            and current["version"] == profile.version
                        ),
                    )
                if current is not None:
                    if current["profile_id"] != profile.profile_id:
                        raise ProfileVersionConflictError(
                            "A subject cannot silently switch profile identity."
                        )
                    if profile.version <= current["version"]:
                        raise ProfileVersionConflictError(
                            "Profile version regression is not allowed."
                        )
                connection.execute(
                    """
                    INSERT INTO profile_versions(
                        subject_id, profile_id, version, payload_json,
                        semantic_hash, stored_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        subject,
                        profile.profile_id,
                        profile.version,
                        payload_json,
                        semantic_hash,
                        utc_now().isoformat(),
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO current_profiles(subject_id, profile_id, version, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(subject_id) DO UPDATE SET
                        profile_id = excluded.profile_id,
                        version = excluded.version,
                        updated_at = excluded.updated_at
                    """,
                    (
                        subject,
                        profile.profile_id,
                        profile.version,
                        utc_now().isoformat(),
                    ),
                )
                connection.commit()
        except sqlite3.DatabaseError as exc:
            raise MemoryStoreError("Confirmed profile persistence failed.") from exc
        return ProfileSaveResult(
            profile=profile,
            reference=reference,
            created=True,
            current=True,
        )

    def get_current_confirmed_profile(self, subject_id: str) -> UserProfile | None:
        subject = _validate_subject_id(subject_id)
        try:
            with self.database.connection() as connection:
                row = connection.execute(
                    """
                    SELECT versions.payload_json
                    FROM current_profiles AS current
                    JOIN profile_versions AS versions
                      ON versions.subject_id = current.subject_id
                     AND versions.profile_id = current.profile_id
                     AND versions.version = current.version
                    WHERE current.subject_id = ?
                    """,
                    (subject,),
                ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise MemoryStoreError("Current profile lookup failed.") from exc
        return None if row is None else self._decode_profile(row["payload_json"])

    def get_profile_version(
        self, subject_id: str, profile_id: str, version: int
    ) -> UserProfile | None:
        subject = _validate_subject_id(subject_id)
        try:
            with self.database.connection() as connection:
                row = connection.execute(
                    """
                    SELECT payload_json FROM profile_versions
                    WHERE subject_id = ? AND profile_id = ? AND version = ?
                    """,
                    (subject, profile_id, version),
                ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise MemoryStoreError("Profile version lookup failed.") from exc
        return None if row is None else self._decode_profile(row["payload_json"])

    def list_profile_history(self, subject_id: str) -> list[UserProfile]:
        subject = _validate_subject_id(subject_id)
        try:
            with self.database.connection() as connection:
                rows = connection.execute(
                    """
                    SELECT payload_json FROM profile_versions
                    WHERE subject_id = ?
                    ORDER BY profile_id ASC, version ASC
                    """,
                    (subject,),
                ).fetchall()
        except sqlite3.DatabaseError as exc:
            raise MemoryStoreError("Profile history lookup failed.") from exc
        return [self._decode_profile(row["payload_json"]) for row in rows]

    @staticmethod
    def _decode_profile(payload_json: str) -> UserProfile:
        try:
            profile = UserProfile.model_validate(json.loads(payload_json))
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            raise CorruptStoredProfileError(
                "Stored profile failed current UserProfile validation."
            ) from exc
        if not profile.confirmed:
            raise CorruptStoredProfileError(
                "Authoritative profile storage contains an unconfirmed profile."
            )
        return profile


class SQLiteMemoryStore(MemoryStore):
    def __init__(self, database: SQLiteMemoryDatabase) -> None:
        self.database = database

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
        record = self._new_record(
            subject_id=subject_id,
            memory_type=memory_type,
            status=MemoryStatus.CANDIDATE,
            content=content,
            source_type=source_type,
            evidence_refs=evidence_refs,
            confidence=confidence,
            metadata=metadata,
            memory_id=memory_id,
        )
        return self._insert(record)

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
        if not confirmed_by_user:
            raise InvalidMemoryTransitionError(
                "Confirmed memory requires explicit user confirmation."
            )
        record = self._new_record(
            subject_id=subject_id,
            memory_type=memory_type,
            status=MemoryStatus.CONFIRMED,
            content=content,
            source_type=source_type,
            evidence_refs=evidence_refs,
            confidence=confidence,
            metadata=metadata,
            memory_id=memory_id,
        )
        return self._insert(record)

    def get(self, subject_id: str, memory_id: str) -> MemoryRecord | None:
        subject = _validate_subject_id(subject_id)
        try:
            with self.database.connection() as connection:
                row = connection.execute(
                    "SELECT * FROM memory_records WHERE subject_id = ? AND memory_id = ?",
                    (subject, memory_id),
                ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise MemoryStoreError("Memory lookup failed.") from exc
        return None if row is None else self._decode_record(row)

    def list_active(
        self,
        subject_id: str,
        *,
        memory_types: Sequence[MemoryType] | None = None,
        metadata_filters: Mapping[str, object] | None = None,
    ) -> list[MemoryRecord]:
        return self.list_history(
            subject_id,
            statuses=(MemoryStatus.CONFIRMED,),
            memory_types=memory_types,
            metadata_filters=metadata_filters,
        )

    def list_history(
        self,
        subject_id: str,
        *,
        statuses: Sequence[MemoryStatus] | None = None,
        memory_types: Sequence[MemoryType] | None = None,
        metadata_filters: Mapping[str, object] | None = None,
    ) -> list[MemoryRecord]:
        subject = _validate_subject_id(subject_id)
        clauses = ["subject_id = ?"]
        parameters: list[object] = [subject]
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            clauses.append(f"status IN ({placeholders})")
            parameters.extend(item.value for item in statuses)
        if memory_types:
            placeholders = ",".join("?" for _ in memory_types)
            clauses.append(f"memory_type IN ({placeholders})")
            parameters.extend(item.value for item in memory_types)
        query = (
            "SELECT * FROM memory_records WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at ASC, memory_id ASC"
        )
        try:
            with self.database.connection() as connection:
                rows = connection.execute(query, tuple(parameters)).fetchall()
        except sqlite3.DatabaseError as exc:
            raise MemoryStoreError("Memory history lookup failed.") from exc
        records = [self._decode_record(row) for row in rows]
        if metadata_filters:
            records = [
                record
                for record in records
                if all(record.metadata.get(key) == value for key, value in metadata_filters.items())
            ]
        return records

    def confirm(
        self, subject_id: str, memory_id: str, *, confirmed_by_user: bool
    ) -> MemoryRecord:
        if not confirmed_by_user:
            raise InvalidMemoryTransitionError(
                "Candidate confirmation requires explicit user confirmation."
            )
        return self._transition(
            subject_id,
            memory_id,
            allowed=(MemoryStatus.CANDIDATE,),
            target=MemoryStatus.CONFIRMED,
        )

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
        if not confirmed_by_user:
            raise InvalidMemoryTransitionError(
                "Superseding memory requires explicit user confirmation."
            )
        subject = _validate_subject_id(subject_id)
        try:
            with self.database.connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM memory_records WHERE subject_id = ? AND memory_id = ?",
                    (subject, memory_id),
                ).fetchone()
                if row is None:
                    raise MemoryNotFoundError("Memory record was not found.")
                previous = self._decode_record(row)
                if previous.status != MemoryStatus.CONFIRMED:
                    raise InvalidMemoryTransitionError(
                        "Only confirmed memory may be superseded."
                    )
                replacement = self._new_record(
                    subject_id=subject,
                    memory_type=previous.memory_type,
                    status=MemoryStatus.CONFIRMED,
                    content=content,
                    source_type=source_type,
                    evidence_refs=evidence_refs,
                    confidence=confidence,
                    metadata=metadata,
                    memory_id=new_memory_id,
                    supersedes_memory_id=previous.memory_id,
                )
                self._insert_with_connection(connection, replacement)
                connection.execute(
                    "UPDATE memory_records SET status = ?, updated_at = ? WHERE memory_id = ?",
                    (
                        MemoryStatus.SUPERSEDED.value,
                        utc_now().isoformat(),
                        previous.memory_id,
                    ),
                )
                connection.commit()
        except sqlite3.DatabaseError as exc:
            raise MemoryStoreError("Memory supersession failed.") from exc
        return replacement

    def archive(self, subject_id: str, memory_id: str) -> MemoryRecord:
        return self._transition(
            subject_id,
            memory_id,
            allowed=(MemoryStatus.CANDIDATE, MemoryStatus.CONFIRMED),
            target=MemoryStatus.ARCHIVED,
        )

    def _transition(
        self,
        subject_id: str,
        memory_id: str,
        *,
        allowed: Sequence[MemoryStatus],
        target: MemoryStatus,
    ) -> MemoryRecord:
        subject = _validate_subject_id(subject_id)
        try:
            with self.database.connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM memory_records WHERE subject_id = ? AND memory_id = ?",
                    (subject, memory_id),
                ).fetchone()
                if row is None:
                    raise MemoryNotFoundError("Memory record was not found.")
                current = self._decode_record(row)
                if current.status not in allowed:
                    raise InvalidMemoryTransitionError(
                        "The requested memory status transition is not allowed."
                    )
                updated_at = utc_now()
                connection.execute(
                    "UPDATE memory_records SET status = ?, updated_at = ? WHERE memory_id = ?",
                    (target.value, updated_at.isoformat(), memory_id),
                )
                connection.commit()
        except sqlite3.DatabaseError as exc:
            raise MemoryStoreError("Memory status transition failed.") from exc
        return current.model_copy(update={"status": target, "updated_at": updated_at})

    def _insert(self, record: MemoryRecord) -> MemoryRecord:
        try:
            with self.database.connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                stored = self._insert_with_connection(connection, record)
                connection.commit()
                return stored
        except sqlite3.DatabaseError as exc:
            raise MemoryStoreError("Memory creation failed.") from exc

    def _insert_with_connection(
        self, connection: sqlite3.Connection, record: MemoryRecord
    ) -> MemoryRecord:
        semantic_hash = _hash_json(_memory_semantic_payload(record))
        existing = connection.execute(
            "SELECT * FROM memory_records WHERE memory_id = ?", (record.memory_id,)
        ).fetchone()
        if existing is not None:
            if existing["semantic_hash"] != semantic_hash:
                raise MemoryConflictError("Memory ID has conflicting immutable content.")
            return self._decode_record(existing)
        connection.execute(
            """
            INSERT INTO memory_records(
                memory_id, subject_id, memory_type, status, content, source_type,
                evidence_refs_json, confidence, created_at, updated_at,
                supersedes_memory_id, metadata_json, semantic_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.memory_id,
                record.subject_id,
                record.memory_type.value,
                record.status.value,
                record.content,
                record.source_type.value,
                _canonical_json(record.evidence_refs),
                record.confidence,
                record.created_at.isoformat(),
                record.updated_at.isoformat(),
                record.supersedes_memory_id,
                _canonical_json(record.metadata),
                semantic_hash,
            ),
        )
        return record

    @staticmethod
    def _new_record(
        *,
        subject_id: str,
        memory_type: MemoryType,
        status: MemoryStatus,
        content: str,
        source_type: EvidenceSourceType,
        evidence_refs: Sequence[str],
        confidence: float | None,
        metadata: Mapping[str, object] | None,
        memory_id: str | None,
        supersedes_memory_id: str | None = None,
    ) -> MemoryRecord:
        now = utc_now()
        return MemoryRecord(
            memory_id=memory_id or new_memory_id(),
            subject_id=_validate_subject_id(subject_id),
            memory_type=memory_type,
            status=status,
            content=content,
            source_type=source_type,
            evidence_refs=list(evidence_refs),
            confidence=confidence,
            created_at=now,
            updated_at=now,
            supersedes_memory_id=supersedes_memory_id,
            metadata=dict(metadata or {}),
        )

    @staticmethod
    def _decode_record(row: sqlite3.Row) -> MemoryRecord:
        try:
            return MemoryRecord(
                memory_id=row["memory_id"],
                subject_id=row["subject_id"],
                memory_type=row["memory_type"],
                status=row["status"],
                content=row["content"],
                source_type=row["source_type"],
                evidence_refs=json.loads(row["evidence_refs_json"]),
                confidence=row["confidence"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                supersedes_memory_id=row["supersedes_memory_id"],
                metadata=json.loads(row["metadata_json"]),
            )
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            raise MemoryStoreError("Stored memory record failed validation.") from exc
