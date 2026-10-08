"""Explicit storage composition. No Guest identity, network or data migration."""

from contextlib import ExitStack
from pathlib import Path
from uuid import UUID
from memory.embeddings import FakeEmbeddingProvider
from memory.service import MemoryService, build_semantic_memory_service
from memory.retriever import DeterministicMemoryRetriever
from memory.semantic import SemanticMemoryRetriever, HybridMemoryRetriever
from memory.context import MemoryContextBuilder
from ui.conversation_store import ConversationStore, _scope
from workflows.langgraph_checkpoint import create_memory_checkpointer, sqlite_checkpointer
from storage.contracts import (StorageLease, StorageClosedError, OwnedStore, OwnedVectorStore, CONVERSATION_METHODS, PROFILE_METHODS, MEMORY_METHODS)
from storage.conversation import EphemeralConversationStore
from storage.memory import EphemeralMemoryDatabase, EphemeralProfileStore, EphemeralMemoryStore
from storage.vector import EphemeralVectorIndex
from storage.settings import EphemeralSettingsStore, SQLiteSettingsStore
from storage.checkpoint import OwnedCheckpointer


class WorkspaceStorage:
    """One-use bundle; close revokes writes, ephemeral close also drops content."""

    def __init__(self, owner, conversations, service, saver, settings_factory, *, lease,
                 ephemeral, root=None, runtime_root=None, stack=None):
        self.owner_scope_id = _scope(owner); self.lease = lease
        identity = conversations.ensure_owner(owner); self.subject_id = identity.subject_id
        self.conversations = OwnedStore(conversations, owner, lease, CONVERSATION_METHODS,
            closed_reads=() if ephemeral else {"get_thread", "list_threads", "list_messages", "load_snapshot", "get_turn"})
        self.memory_service = service
        service.profile_store = OwnedStore(service.profile_store, self.subject_id, lease, PROFILE_METHODS,
            closed_reads=() if ephemeral else {"get_current_confirmed_profile", "get_profile_version", "list_profile_history"})
        service.memory_store = OwnedStore(service.memory_store, self.subject_id, lease, MEMORY_METHODS,
            closed_reads=() if ephemeral else {"get", "list_active", "list_history"})
        service.retriever.store = service.memory_store
        service.semantic_retriever.memory_store = service.memory_store
        self._database = service.database
        service.database = OwnedStore(service.database, self.subject_id, lease, {"purge_subject"})
        self._vector = service.vector_index
        if self._vector:
            vector = OwnedVectorStore(self._vector, self.subject_id, lease,
                {"query", "list_entries", "count_subject", "purge_subject", "clear_subject", "rebuild_subject_index"})
            service.vector_index = vector
            service.semantic_retriever.vector_index = vector
        self.checkpointer = OwnedCheckpointer(saver, owner, self.conversations, lease)
        self.checkpointer.issued_workflows = set()
        self.checkpointer.retired_workflows = set()
        self.checkpointer.workflow_bindings = {}
        self.settings = settings_factory(self.conversations)
        self.ephemeral, self.root, self.runtime_root = ephemeral, root, runtime_root
        self._raw_conversations, self._stack, self._claimed = conversations, stack or ExitStack(), False
        self._cleanup_complete = False

    def claim(self, owner):
        with self.lease.lock:
            self.lease.check()
            if _scope(owner) != self.owner_scope_id or self._claimed:
                raise ValueError("Storage bundle is unavailable for this Workspace.")
            self._claimed = True

    def register_workflow(self, workflow, thread_id):
        with self.lease.lock:
            self.lease.check()
            thread = self.conversations.get_thread(self.owner_scope_id, thread_id)
            if thread.workflow_thread_id not in (None, workflow):
                raise ValueError("Workflow binding is unavailable.")
            self.checkpointer.issued_workflows.add(workflow)
            self.checkpointer.workflow_bindings[workflow] = thread_id

    def retire_transient_thread(self, thread_id):
        """Drop issued orphan workflows for a deleted legacy empty conversation."""
        with self.lease.lock:
            self.lease.check()
            referenced = {t.workflow_thread_id for t in self.conversations.list_threads(self.owner_scope_id)}
            for workflow, thread in tuple(self.checkpointer.workflow_bindings.items()):
                if thread == thread_id and workflow not in referenced:
                    self.checkpointer.delete_thread(workflow)

    def close(self):
        with self.lease.lock:
            if self._cleanup_complete: return
            # Deny publication before touching any backing data.
            self.lease.closed = True
            cleanup_failed = False
            cleanups = []
            if self.ephemeral:
                cleanups.extend((self.checkpointer.clear, self.settings.clear, self._raw_conversations.clear,
                                 self._database.clear, self._vector.clear, self.memory_service.events.clear,
                                 self.memory_service.vector_sync_diagnostics.clear))
            cleanups.append(self._stack.close)
            for cleanup in cleanups:
                try:
                    cleanup()
                except Exception:
                    # One failed store must not retain every other store's
                    # content. Keep the lease closed and allow cleanup retry.
                    cleanup_failed = True
            self._cleanup_complete = not cleanup_failed
            if cleanup_failed:
                raise StorageClosedError("Storage cleanup is incomplete.")


def ephemeral_storage(owner_scope_id, *, embedding_provider=None):
    owner = _scope(owner_scope_id)
    lease = StorageLease(); provider = embedding_provider or FakeEmbeddingProvider()
    conversations = EphemeralConversationStore(lease=lease)
    database = EphemeralMemoryDatabase(lease); profile = EphemeralProfileStore(database); memory = EphemeralMemoryStore(database)
    vector = EphemeralVectorIndex(provider, lease); lexical = DeterministicMemoryRetriever(memory)
    semantic = SemanticMemoryRetriever(memory, vector, provider)
    service = MemoryService(profile_store=profile, memory_store=memory, retriever=lexical, database=database,
        vector_index=vector, semantic_retriever=semantic, hybrid_retriever=HybridMemoryRetriever(lexical, semantic),
        context_builder=MemoryContextBuilder())
    return WorkspaceStorage(owner, conversations, service, create_memory_checkpointer(),
        lambda c: EphemeralSettingsStore(owner, c, lease), lease=lease, ephemeral=True)


def sqlite_storage(owner_scope_id, root):
    owner = _scope(owner_scope_id); root = Path(root); runtime = root / "runtime" / UUID(owner).hex
    lease = StorageLease(); stack = ExitStack()
    try:
        conversations = ConversationStore(root / "conversations.sqlite3")
        service = build_semantic_memory_service(memory_path=runtime / "memory.sqlite3", vector_path=runtime / "vectors.sqlite3",
                                               embedding_provider=FakeEmbeddingProvider())
        saver = stack.enter_context(sqlite_checkpointer(runtime / "checkpoints.sqlite3"))
        return WorkspaceStorage(owner, conversations, service, saver,
            lambda c: SQLiteSettingsStore(owner, c, runtime / "agent_settings.sqlite3", lease),
            lease=lease, ephemeral=False, root=root, runtime_root=runtime, stack=stack)
    except Exception:
        stack.close(); raise
