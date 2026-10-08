"""Ports derived from actual Workspace/Runtime calls; no account authority."""

from typing import Protocol
from threading import RLock


class StorageClosedError(ValueError):
    """Released storage cannot be used to publish or restore content."""


class StorageLease:
    """Shared serialization boundary for cleanup and late writes."""

    def __init__(self):
        self.lock = RLock()
        self.closed = False

    def check(self):
        if self.closed:
            raise StorageClosedError("Storage has been released.")


class ConversationStorage(Protocol):
    def ensure_owner(self, owner_scope_id): ...
    def create_thread(self, owner_scope_id, **kwargs): ...
    def get_thread(self, owner_scope_id, thread_id): ...
    def list_threads(self, owner_scope_id): ...
    def list_messages(self, owner_scope_id, thread_id, *, limit=None): ...
    def load_snapshot(self, owner_scope_id, thread_id): ...
    def save_snapshot(self, owner_scope_id, thread_id, snapshot, **kwargs): ...
    def rename_thread(self, owner_scope_id, thread_id, title): ...
    def delete_thread(self, owner_scope_id, thread_id): ...
    def append_turn(self, owner_scope_id, thread_id, user_content, assistant_content, **kwargs): ...
    def get_turn(self, owner_scope_id, thread_id, turn_id): ...
    def annotate_cancelled_turn(self, owner_scope_id, thread_id, turn_id, partial_text, metadata): ...


class ConsentStorage(Protocol):
    def valid(self, owner, category, version, *, request_scope=None): ...
    def set(self, owner, category, version, *, granted, request_scope=None): ...
    def revoke(self, owner, category): ...


class ReceiptStorage(Protocol):
    def get_receipt(self, owner, thread): ...
    def record_receipt(self, owner, thread, turn, status, anchor): ...


class VectorStorage(Protocol):
    def index_record(self, record): ...
    def index_records(self, records): ...
    def remove(self, memory_id): ...
    def query(self, subject_id, query_vector, *, top_k=10, memory_types=None): ...
    def metadata_for(self, memory_id): ...
    def list_entries(self, subject_id): ...
    def count_subject(self, subject_id): ...
    def purge_subject(self, subject_id): ...
    def rebuild_subject_index(self, subject_id, memory_store): ...


class PurgeStorage(Protocol):
    def purge_subject(self, subject_id): ...


class OwnedStore:
    """Bind a port to a Workspace owner/subject; not authentication.

    The underlying stores retain their ordinary ownership validation. This
    additional boundary prevents a Workspace using another Workspace's scope.
    """

    def __init__(self, store, scope, lease, methods, *, closed_reads=()):
        self._store, self._scope, self._lease = store, scope, lease
        self._methods = frozenset(methods)
        self._closed_reads = frozenset(closed_reads)

    def __getattr__(self, name):
        value = getattr(self._store, name)
        if not callable(value):
            return value
        def owned(*args, **kwargs):
            with self._lease.lock:
                if name not in self._closed_reads:
                    self._lease.check()
                actual = args[0] if args else kwargs.get("subject_id", kwargs.get("owner_scope_id"))
                if name in self._methods and actual != self._scope:
                    raise ValueError("Storage scope is unavailable.")
                return value(*args, **kwargs)
        return owned


class OwnedVectorStore(OwnedStore):
    def index_record(self, record):
        return self.index_records((record,))[0]

    def index_records(self, records):
        with self._lease.lock:
            self._lease.check(); records = tuple(records)
            if any(r.subject_id != self._scope for r in records):
                raise ValueError("Vector scope is unavailable.")
            return self._store.index_records(records)

    def metadata_for(self, memory_id):
        with self._lease.lock:
            self._lease.check(); entry = self._store.metadata_for(memory_id)
            return entry if entry is not None and entry.subject_id == self._scope else None

    def remove(self, memory_id):
        with self._lease.lock:
            self._lease.check()
            return self._store.remove(memory_id) if self.metadata_for(memory_id) else False


CONVERSATION_METHODS = {
    "ensure_owner", "create_thread", "get_thread", "list_threads", "list_messages",
    "load_snapshot", "save_snapshot", "rename_thread", "delete_thread", "append_turn",
    "get_turn", "annotate_cancelled_turn",
}
PROFILE_METHODS = {"save_confirmed_profile", "get_current_confirmed_profile", "get_profile_version", "list_profile_history"}
MEMORY_METHODS = {"create_candidate", "create_confirmed", "get", "list_active", "list_history", "confirm", "supersede", "archive"}
