"""Scoped local transcript storage, separate from Profile, Memory and checkpoints.

An opaque client scope provides local/demo isolation, NOT authentication. The
database lives in ignored ``data/local/chat``; no transcript enters localStorage.
Presentation snapshots can resume guided UI state, but confer no domain authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Callable, Iterator, Mapping
from uuid import UUID, uuid4

from ui.conversation import ConversationStage, GuidedConversation, QUESTIONS


DEFAULT_CONVERSATION_PATH = (
    Path(__file__).resolve().parents[1] / "data/local/chat/conversations.sqlite3"
)
EMPTY_TITLE = "新对话"
TITLE_LIMIT = 60
INITIAL_TITLE_LIMIT = 24
_SNAPSHOT_KEYS = frozenset(
    ("stage", "answers", "notes", "pending_note", "revising", "selected_role")
)
_METADATA_KEYS = frozenset(
    ("kind", "structured_payload_type", "suggestions", "evidence_refs", "source")
)
_PAYLOAD_KINDS = frozenset(("text", "profile", "directions", "match", "actions", "memory"))
_CREDENTIAL_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r'''(?i)(?:api_key|access_token|password|secret_key)\s*[=:]\s*["']([A-Za-z0-9_+/=-]{20,})["']'''),
    re.compile(r"(?i)Bearer\s+([A-Za-z0-9_+/=-]{20,})"),
)


class ConversationStoreError(ValueError):
    """Safe storage/input error without transcript or credential contents."""


class ConversationNotFoundError(ConversationStoreError):
    """Missing and out-of-scope records intentionally share one error."""


@dataclass(frozen=True)
class ScopeIdentity:
    owner_scope_id: str
    subject_id: str


@dataclass(frozen=True)
class ConversationThread:
    thread_id: str
    owner_scope_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    workflow_thread_id: str | None = None
    profile_id_ref: str | None = None
    profile_version_ref: int | None = None


@dataclass(frozen=True)
class ConversationMessage:
    message_id: str
    thread_id: str
    role: str
    content: str
    created_at: datetime
    metadata: dict[str, object]


def _scope(value: str) -> str:
    try:
        parsed = UUID(value)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ConversationStoreError("Client scope must be an opaque UUID.") from exc
    if str(parsed) != value:
        raise ConversationStoreError("Client scope must use canonical UUID form.")
    return value


def _identifier(value: str | None) -> str | None:
    if value is not None and (
        not isinstance(value, str) or not 1 <= len(value) <= 160
        or any(not (char.isascii() and (char.isalnum() or char in "_.:@-")) for char in value)
    ):
        raise ConversationStoreError("Reference identifier is invalid.")
    if value is not None:
        _no_credentials(value)
    return value


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ConversationStoreError("Conversation timestamps must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _title(value: str, *, limit: int = TITLE_LIMIT) -> str:
    if not isinstance(value, str):
        raise ConversationStoreError("Conversation title must be text.")
    normalized = " ".join(value.split())
    _no_credentials(normalized)
    if not normalized or len(normalized) > limit:
        raise ConversationStoreError("Conversation title is empty or too long.")
    return normalized


def _content(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 20000:
        raise ConversationStoreError("Message content is empty or too long.")
    _no_credentials(value)
    return value


def _no_credentials(value: str) -> None:
    for pattern in _CREDENTIAL_PATTERNS:
        for match in pattern.finditer(value):
            candidate = match.group(1) if match.lastindex else match.group(0)
            if not candidate.lower().startswith(("sk-fake", "sk-test", "fake-", "synthetic-")):
                raise ConversationStoreError("Credential-shaped content cannot be persisted.")


def _metadata(value: Mapping[str, object] | None) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, Mapping) or set(value) - _METADATA_KEYS:
        raise ConversationStoreError("Unsupported presentation metadata.")
    result: dict[str, object] = {}
    if "kind" in value and "structured_payload_type" in value:
        raise ConversationStoreError("Presentation kind must be specified once.")
    for key in ("kind", "structured_payload_type"):
        if key in value:
            if not isinstance(value[key], str) or value[key] not in _PAYLOAD_KINDS:
                raise ConversationStoreError("Unsupported presentation kind.")
            result[key] = value[key]
    if "source" in value:
        if value["source"] not in ("typed", "suggestion"):
            raise ConversationStoreError("Unsupported message source.")
        result["source"] = value["source"]
    for key, item_limit, count_limit in (("suggestions", 500, 32), ("evidence_refs", 160, 100)):
        if key not in value:
            continue
        items = value[key]
        if not isinstance(items, (tuple, list)) or len(items) > count_limit:
            raise ConversationStoreError("Presentation list metadata is invalid.")
        if any(not isinstance(item, str) or not item.strip() or len(item) > item_limit for item in items):
            raise ConversationStoreError("Presentation list metadata is invalid.")
        for item in items:
            _no_credentials(item)
        if key == "evidence_refs":
            for item in items:
                _identifier(item)
        result[key] = list(items)
    return result


def validate_snapshot(value: Mapping[str, object] | None) -> dict[str, object]:
    """Validate a closed presentation snapshot without invoking domain workflows.

    Guided routing is checked on a throwaway presentation state machine. This is
    NOT replay of conversation messages, controller calls, model calls or Memory
    writes. Restoration itself uses the resulting stage/answers/notes directly.
    """
    if value is None:
        value = {}
    if not isinstance(value, Mapping) or set(value) - _SNAPSHOT_KEYS:
        raise ConversationStoreError("Unsupported conversation snapshot fields.")
    stage = value.get("stage", ConversationStage.CAREER_QUESTION.value)
    answers = value.get("answers", {})
    notes = value.get("notes", {})
    pending_note = value.get("pending_note", "")
    revising = value.get("revising", False)
    selected_role = value.get("selected_role")
    try:
        target = ConversationStage(stage)
    except (ValueError, TypeError) as exc:
        raise ConversationStoreError("Conversation stage is invalid.") from exc
    if not isinstance(answers, Mapping) or not isinstance(notes, Mapping):
        raise ConversationStoreError("Guided state must use explicit mappings.")
    if not isinstance(pending_note, str) or len(pending_note) > 240 or type(revising) is not bool:
        raise ConversationStoreError("Conversation presentation state is invalid.")
    _no_credentials(pending_note)
    _identifier(selected_role)
    normalized_answers: dict[str, str | list[str]] = {}
    normalized_notes: dict[str, str] = {}
    remaining = dict(answers)
    guided = GuidedConversation()
    try:
        while guided.stage.value in remaining:
            key = guided.stage.value
            answer = remaining.pop(key)
            question = QUESTIONS[guided.stage]
            if not isinstance(answer, (str, tuple, list)):
                raise ValueError("Invalid guided answer.")
            normalized = guided._normalize_answer(question, answer)
            guided.submit(guided.stage, normalized)
            normalized_answers[key] = list(normalized) if isinstance(normalized, tuple) else normalized
    except (ValueError, TypeError, KeyError) as exc:
        raise ConversationStoreError("Guided snapshot answers are invalid.") from exc
    if remaining or guided.stage != target:
        raise ConversationStoreError("Guided snapshot stage does not match its answers.")
    for key, note in notes.items():
        if key not in normalized_answers or not isinstance(note, str) or len(note) > 240:
            raise ConversationStoreError("Guided snapshot notes are invalid.")
        _no_credentials(note)
        normalized_notes[key] = note
    return {
        "stage": target.value, "answers": normalized_answers, "notes": normalized_notes,
        "pending_note": pending_note, "revising": revising, "selected_role": selected_role,
    }


class ConversationStore:
    """SQLite transcript store: every record operation requires an owner scope."""

    def __init__(self, path: str | Path = DEFAULT_CONVERSATION_PATH, *, clock: Callable[[], datetime] | None = None) -> None:
        self.path = Path(path)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ConversationStoreError("Conversation schema version is unsupported.")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS conversation_owners (
                    owner_scope_id TEXT PRIMARY KEY, subject_id TEXT NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS conversation_threads (
                    owner_scope_id TEXT NOT NULL, thread_id TEXT NOT NULL,
                    title TEXT NOT NULL, title_initialized INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    workflow_thread_id TEXT, profile_id_ref TEXT, profile_version_ref INTEGER,
                    snapshot_json TEXT NOT NULL,
                    PRIMARY KEY (owner_scope_id, thread_id),
                    FOREIGN KEY (owner_scope_id) REFERENCES conversation_owners(owner_scope_id)
                );
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    position INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_scope_id TEXT NOT NULL, message_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                    content TEXT NOT NULL, created_at TEXT NOT NULL, metadata_json TEXT NOT NULL,
                    UNIQUE (owner_scope_id, message_id),
                    FOREIGN KEY (owner_scope_id, thread_id)
                        REFERENCES conversation_threads(owner_scope_id, thread_id)
                );
                CREATE INDEX IF NOT EXISTS conversation_thread_order
                    ON conversation_threads(owner_scope_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS conversation_message_order
                    ON conversation_messages(owner_scope_id, thread_id, position);
                PRAGMA user_version = 1;
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def _now(self, previous: str | None = None) -> datetime:
        now = _aware(self._clock())
        if previous is not None:
            now = max(now, datetime.fromisoformat(previous) + timedelta(microseconds=1))
        return now

    def _updated(self, db: sqlite3.Connection, owner: str) -> str:
        previous = db.execute(
            "SELECT updated_at FROM conversation_threads WHERE owner_scope_id = ? ORDER BY updated_at DESC LIMIT 1",
            (owner,),
        ).fetchone()
        return self._now(previous["updated_at"] if previous is not None else None).isoformat()

    @staticmethod
    def _thread(row: sqlite3.Row) -> ConversationThread:
        return ConversationThread(
            row["thread_id"], row["owner_scope_id"], row["title"],
            datetime.fromisoformat(row["created_at"]), datetime.fromisoformat(row["updated_at"]),
            row["workflow_thread_id"], row["profile_id_ref"], row["profile_version_ref"],
        )

    @staticmethod
    def _message(row: sqlite3.Row) -> ConversationMessage:
        return ConversationMessage(
            row["message_id"], row["thread_id"], row["role"], row["content"],
            datetime.fromisoformat(row["created_at"]), json.loads(row["metadata_json"]),
        )

    @staticmethod
    def _owned(db: sqlite3.Connection, owner: str, thread_id: str) -> sqlite3.Row:
        _identifier(thread_id)
        row = db.execute(
            "SELECT * FROM conversation_threads WHERE owner_scope_id = ? AND thread_id = ?",
            (owner, thread_id),
        ).fetchone()
        if row is None:
            raise ConversationNotFoundError("Conversation is unavailable for this client scope.")
        return row

    def ensure_owner(self, owner_scope_id: str) -> ScopeIdentity:
        """Resolve one stable opaque canonical subject mapping, never a profile."""
        owner = _scope(owner_scope_id)
        with self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO conversation_owners(owner_scope_id, subject_id) VALUES (?, ?)",
                (owner, f"subject_{uuid4().hex}"),
            )
            row = db.execute("SELECT subject_id FROM conversation_owners WHERE owner_scope_id = ?", (owner,)).fetchone()
        return ScopeIdentity(owner, row["subject_id"])

    @staticmethod
    def _refs(workflow: str | None, profile: str | None, version: int | None) -> None:
        _identifier(workflow)
        _identifier(profile)
        if (profile is None) != (version is None) or (version is not None and (type(version) is not int or version < 1)):
            raise ConversationStoreError("Profile references require an ID and positive version.")

    def create_thread(self, owner_scope_id: str, *, workflow_thread_id: str | None = None,
                      profile_id_ref: str | None = None, profile_version_ref: int | None = None,
                      snapshot: Mapping[str, object] | None = None) -> ConversationThread:
        owner = self.ensure_owner(owner_scope_id).owner_scope_id
        self._refs(workflow_thread_id, profile_id_ref, profile_version_ref)
        serialized = json.dumps(validate_snapshot(snapshot), ensure_ascii=False)
        thread_id = f"conversation_{uuid4().hex}"
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            now = self._updated(db, owner)
            db.execute("""INSERT INTO conversation_threads (
                owner_scope_id, thread_id, title, created_at, updated_at,
                workflow_thread_id, profile_id_ref, profile_version_ref, snapshot_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (owner, thread_id, EMPTY_TITLE, now, now, workflow_thread_id, profile_id_ref, profile_version_ref, serialized))
            return self._thread(self._owned(db, owner, thread_id))

    def get_thread(self, owner_scope_id: str, thread_id: str) -> ConversationThread:
        with self._connect() as db:
            return self._thread(self._owned(db, _scope(owner_scope_id), thread_id))

    def list_threads(self, owner_scope_id: str) -> tuple[ConversationThread, ...]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM conversation_threads WHERE owner_scope_id = ? ORDER BY updated_at DESC, thread_id ASC", (_scope(owner_scope_id),)).fetchall()
        return tuple(self._thread(row) for row in rows)

    def list_messages(self, owner_scope_id: str, thread_id: str) -> tuple[ConversationMessage, ...]:
        owner = _scope(owner_scope_id)
        with self._connect() as db:
            self._owned(db, owner, thread_id)
            rows = db.execute("SELECT * FROM conversation_messages WHERE owner_scope_id = ? AND thread_id = ? ORDER BY position ASC", (owner, thread_id)).fetchall()
        return tuple(self._message(row) for row in rows)

    def load_snapshot(self, owner_scope_id: str, thread_id: str) -> dict[str, object]:
        with self._connect() as db:
            row = self._owned(db, _scope(owner_scope_id), thread_id)
        return validate_snapshot(json.loads(row["snapshot_json"]))

    def rename_thread(self, owner_scope_id: str, thread_id: str, title: str) -> ConversationThread:
        owner, normalized = _scope(owner_scope_id), _title(title)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._owned(db, owner, thread_id)
            now = self._updated(db, owner)
            db.execute("UPDATE conversation_threads SET title = ?, title_initialized = 1, updated_at = ? WHERE owner_scope_id = ? AND thread_id = ?", (normalized, now, owner, thread_id))
            return self._thread(self._owned(db, owner, thread_id))

    def delete_thread(self, owner_scope_id: str, thread_id: str) -> ConversationThread:
        """Delete only an owned transcript and its inline presentation state.

        Existing databases need no migration: messages and their metadata are
        removed before the parent row in one explicit transaction. Canonical
        stores and the stable owner/subject mapping are not part of this store.
        """
        owner = _scope(owner_scope_id)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            deleted = self._thread(self._owned(db, owner, thread_id))
            db.execute(
                "DELETE FROM conversation_messages WHERE owner_scope_id = ? AND thread_id = ?",
                (owner, thread_id),
            )
            db.execute(
                "DELETE FROM conversation_threads WHERE owner_scope_id = ? AND thread_id = ?",
                (owner, thread_id),
            )
        return deleted

    def _save(self, db: sqlite3.Connection, owner: str, thread_id: str, row: sqlite3.Row,
              now: str, snapshot: Mapping[str, object] | None, workflow: str | None,
              profile: str | None, version: int | None, title: str | None = None) -> None:
        self._refs(workflow, profile, version)
        serialized = row["snapshot_json"] if snapshot is None else json.dumps(validate_snapshot(snapshot), ensure_ascii=False)
        db.execute("""UPDATE conversation_threads SET updated_at = ?, snapshot_json = ?,
            workflow_thread_id = ?, profile_id_ref = ?, profile_version_ref = ?,
            title = ?, title_initialized = ? WHERE owner_scope_id = ? AND thread_id = ?""",
            (now, serialized, workflow if workflow is not None else row["workflow_thread_id"],
             profile if profile is not None else row["profile_id_ref"],
             version if version is not None else row["profile_version_ref"],
             title if title is not None else row["title"],
             1 if title is not None else row["title_initialized"], owner, thread_id))

    def append_turn(self, owner_scope_id: str, thread_id: str, user_content: str,
                    assistant_content: str, *, user_metadata: Mapping[str, object] | None = None,
                    assistant_metadata: Mapping[str, object] | None = None,
                    snapshot: Mapping[str, object] | None = None,
                    workflow_thread_id: str | None = None, profile_id_ref: str | None = None,
                    profile_version_ref: int | None = None) -> tuple[ConversationMessage, ConversationMessage]:
        """Atomically persist two visible messages and their guided presentation state."""
        owner = _scope(owner_scope_id)
        user, assistant = _content(user_content), _content(assistant_content)
        meta = (_metadata(user_metadata), _metadata(assistant_metadata))
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._owned(db, owner, thread_id)
            now = self._updated(db, owner)
            result = []
            for role, content, metadata in zip(("user", "assistant"), (user, assistant), meta):
                message_id = f"message_{uuid4().hex}"
                db.execute("INSERT INTO conversation_messages(owner_scope_id, message_id, thread_id, role, content, created_at, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (owner, message_id, thread_id, role, content, now, json.dumps(metadata, ensure_ascii=False)))
                result.append(ConversationMessage(message_id, thread_id, role, content, datetime.fromisoformat(now), metadata))
            title = " ".join(user.split())[:INITIAL_TITLE_LIMIT] if not row["title_initialized"] else None
            self._save(db, owner, thread_id, row, now, snapshot, workflow_thread_id, profile_id_ref, profile_version_ref, title)
            return tuple(result)

    def save_snapshot(self, owner_scope_id: str, thread_id: str, snapshot: Mapping[str, object], *,
                      workflow_thread_id: str | None = None, profile_id_ref: str | None = None,
                      profile_version_ref: int | None = None) -> ConversationThread:
        """Save explicit UI state/ref changes without inventing or replaying messages."""
        owner = _scope(owner_scope_id)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._owned(db, owner, thread_id)
            now = self._updated(db, owner)
            self._save(db, owner, thread_id, row, now, snapshot, workflow_thread_id, profile_id_ref, profile_version_ref)
            return self._thread(self._owned(db, owner, thread_id))
