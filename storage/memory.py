"""Process-only canonical stores; the existing confirmation/governance calls own authority."""

from copy import deepcopy
from data.models import UserProfile, ProfileStatus, utc_now
from memory.base import StructuredProfileStore, MemoryStore
from memory.errors import ProfileVersionConflictError, MemoryConflictError, InvalidMemoryTransitionError, MemoryNotFoundError
from memory.models import ProfileReference, ProfileSaveResult, PurgeResult, MemoryStatus
from memory.sqlite_store import (
    _validate_subject_id, _hash_json, _profile_semantic_payload, _memory_semantic_payload,
    _UNCONDITIONAL_PROFILE_SAVE, SQLiteMemoryStore,
)
from storage.contracts import StorageLease


class EphemeralMemoryDatabase:
    """No SQL/connection/path; one atomic lock for canonical records and purge."""

    def __init__(self, lease=None):
        self.lease = lease or StorageLease()
        self.profiles, self.current, self.records = {}, {}, {}

    def clear(self):
        self.profiles.clear(); self.current.clear(); self.records.clear()

    def purge_subject(self, subject_id):
        with self.lease.lock:
            self.lease.check(); subject = _validate_subject_id(subject_id)
            keys = [k for k in self.profiles if k[0] == subject]
            records = [k for k, v in self.records.items() if v.subject_id == subject]
            pointer = int(subject in self.current)
            for key in keys: del self.profiles[key]
            for key in records: del self.records[key]
            self.current.pop(subject, None)
            return PurgeResult(subject_id=subject, profile_versions_deleted=len(keys),
                current_pointer_deleted=pointer, memory_records_deleted=len(records))


class EphemeralProfileStore(StructuredProfileStore):
    def __init__(self, database): self.database = database

    def save_confirmed_profile(self, subject_id, profile, *, expected_current=_UNCONDITIONAL_PROFILE_SAVE,
                               confirmation_guard=None):
        with self.database.lease.lock:
            self.database.lease.check(); subject = _validate_subject_id(subject_id)
            profile = UserProfile.model_validate(profile.model_dump())
            if not profile.confirmed or profile.status != ProfileStatus.CONFIRMED:
                raise ProfileVersionConflictError("Only a confirmed UserProfile may enter the authoritative store.")
            key = (subject, profile.profile_id, profile.version)
            existing = self.database.profiles.get(key); current = self.database.current.get(subject)
            semantic_hash = _hash_json(_profile_semantic_payload(profile))
            if expected_current is not _UNCONDITIONAL_PROFILE_SAVE:
                valid_base = profile.version == 1 if expected_current is None else (
                    isinstance(expected_current, ProfileReference) and expected_current.subject_id == subject and
                    expected_current.profile_id == profile.profile_id and expected_current.version == profile.version - 1)
                if not valid_base:
                    raise ProfileVersionConflictError("PROFILE_VERSION_CONFLICT")
                replay = existing is not None and existing[0] == semantic_hash and current == key
                matches = current is None and profile.version == 1 if expected_current is None else (
                    isinstance(expected_current, ProfileReference) and expected_current.subject_id == subject and
                    current is not None and current[1] == expected_current.profile_id == profile.profile_id and
                    current[2] == expected_current.version == profile.version - 1)
                if not (matches or replay):
                    raise ProfileVersionConflictError("PROFILE_VERSION_CONFLICT")
            reference = ProfileReference(subject_id=subject, profile_id=profile.profile_id, version=profile.version)
            if existing is not None:
                if existing[0] != semantic_hash:
                    raise ProfileVersionConflictError("An immutable profile identity has conflicting content.")
                return ProfileSaveResult(profile=deepcopy(existing[1]), reference=reference, created=False, current=current == key)
            if current is not None and (current[1] != profile.profile_id or profile.version <= current[2]):
                raise ProfileVersionConflictError("Profile identity/version conflict.")
            # Preserve both guard checkpoints and rollback of the SQLite contract.
            if confirmation_guard is not None: confirmation_guard()
            self.database.lease.check()
            # SQLite guard callbacks read through another connection and cannot
            # see its uncommitted pointer. Keep staged data private here too.
            staged = (semantic_hash, deepcopy(profile))
            if confirmation_guard is not None: confirmation_guard()
            self.database.lease.check()
            if self.database.current.get(subject) != current:
                raise ProfileVersionConflictError("PROFILE_VERSION_CONFLICT")
            self.database.profiles[key] = staged; self.database.current[subject] = key
            return ProfileSaveResult(profile=deepcopy(profile), reference=reference, created=True, current=True)

    def get_current_confirmed_profile(self, subject_id):
        with self.database.lease.lock:
            self.database.lease.check(); subject = _validate_subject_id(subject_id)
            key = self.database.current.get(subject)
            return deepcopy(self.database.profiles[key][1]) if key else None

    def get_profile_version(self, subject_id, profile_id, version):
        with self.database.lease.lock:
            self.database.lease.check(); key = (_validate_subject_id(subject_id), profile_id, version)
            stored = self.database.profiles.get(key)
            return deepcopy(stored[1]) if stored else None

    def list_profile_history(self, subject_id):
        with self.database.lease.lock:
            self.database.lease.check(); subject = _validate_subject_id(subject_id)
            return [deepcopy(self.database.profiles[k][1]) for k in sorted(self.database.profiles) if k[0] == subject]


class EphemeralMemoryStore(MemoryStore):
    # Reuse ONLY the pure validated record constructor, never SQLite IO.
    _new_record = staticmethod(SQLiteMemoryStore._new_record)

    def __init__(self, database): self.database = database

    def _create(self, status, *, subject_id, memory_type, content, source_type, evidence_refs=(),
                confidence=None, metadata=None, memory_id=None):
        with self.database.lease.lock:
            self.database.lease.check()
            record = self._new_record(subject_id=subject_id, memory_type=memory_type, status=status, content=content,
                source_type=source_type, evidence_refs=evidence_refs, confidence=confidence, metadata=metadata, memory_id=memory_id)
            return self._insert(record)

    def create_candidate(self, **kwargs): return self._create(MemoryStatus.CANDIDATE, **kwargs)

    def create_confirmed(self, *, confirmed_by_user, **kwargs):
        if not confirmed_by_user: raise InvalidMemoryTransitionError("Confirmed memory requires explicit user confirmation.")
        return self._create(MemoryStatus.CONFIRMED, **kwargs)

    def _insert(self, record):
        previous = self.database.records.get(record.memory_id)
        if previous:
            if _hash_json(_memory_semantic_payload(previous)) != _hash_json(_memory_semantic_payload(record)):
                raise MemoryConflictError("Memory ID has conflicting immutable content.")
            return deepcopy(previous)
        self.database.records[record.memory_id] = deepcopy(record)
        return deepcopy(record)

    def get(self, subject_id, memory_id):
        with self.database.lease.lock:
            self.database.lease.check(); subject = _validate_subject_id(subject_id)
            record = self.database.records.get(memory_id)
            return deepcopy(record) if record and record.subject_id == subject else None

    def list_active(self, subject_id, *, memory_types=None, metadata_filters=None):
        return self.list_history(subject_id, statuses=(MemoryStatus.CONFIRMED,),
                                 memory_types=memory_types, metadata_filters=metadata_filters)

    def list_history(self, subject_id, *, statuses=None, memory_types=None, metadata_filters=None):
        with self.database.lease.lock:
            self.database.lease.check(); subject = _validate_subject_id(subject_id)
            values = [r for r in self.database.records.values() if r.subject_id == subject and
                (not statuses or r.status in statuses) and (not memory_types or r.memory_type in memory_types) and
                all(r.metadata.get(k) == v for k, v in (metadata_filters or {}).items())]
            return deepcopy(sorted(values, key=lambda r: (r.created_at, r.memory_id)))

    def _transition(self, subject_id, memory_id, allowed, target):
        with self.database.lease.lock:
            current = self.get(subject_id, memory_id)
            if current is None: raise MemoryNotFoundError("Memory record was not found.")
            if current.status not in allowed: raise InvalidMemoryTransitionError("Memory transition is not allowed.")
            updated = current.model_copy(update={"status": target, "updated_at": utc_now()})
            self.database.records[memory_id] = updated
            return deepcopy(updated)

    def confirm(self, subject_id, memory_id, *, confirmed_by_user):
        if not confirmed_by_user: raise InvalidMemoryTransitionError("Candidate confirmation requires explicit user confirmation.")
        return self._transition(subject_id, memory_id, (MemoryStatus.CANDIDATE,), MemoryStatus.CONFIRMED)

    def archive(self, subject_id, memory_id):
        return self._transition(subject_id, memory_id, (MemoryStatus.CANDIDATE, MemoryStatus.CONFIRMED), MemoryStatus.ARCHIVED)

    def supersede(self, subject_id, memory_id, *, confirmed_by_user, content, source_type, evidence_refs=(),
                  confidence=None, metadata=None, new_memory_id=None):
        if not confirmed_by_user: raise InvalidMemoryTransitionError("Superseding memory requires explicit user confirmation.")
        with self.database.lease.lock:
            previous = self.get(subject_id, memory_id)
            if previous is None: raise MemoryNotFoundError("Memory record was not found.")
            if previous.status != MemoryStatus.CONFIRMED: raise InvalidMemoryTransitionError("Only confirmed memory may be superseded.")
            record = self._new_record(subject_id=subject_id, memory_type=previous.memory_type, status=MemoryStatus.CONFIRMED,
                content=content, source_type=source_type, evidence_refs=evidence_refs, confidence=confidence,
                metadata=metadata, memory_id=new_memory_id, supersedes_memory_id=memory_id)
            self._insert(record)
            self.database.records[memory_id] = previous.model_copy(update={"status": MemoryStatus.SUPERSEDED, "updated_at": utc_now()})
            return deepcopy(record)
