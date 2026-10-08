"""Owner/thread-scoped facade over the existing LangGraph savers."""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver


class OwnedCheckpointer(BaseCheckpointSaver):
    def __init__(self, saver, owner, conversations, lease):
        super().__init__(serde=saver.serde)
        self.saver, self.owner, self.conversations, self.lease = saver, owner, conversations, lease

    @property
    def config_specs(self): return self.saver.config_specs

    def _check(self, config):
        self.lease.check()
        thread = config.get("configurable", {}).get("thread_id")
        if thread not in self._current_workflows():
            raise ValueError("Checkpoint workflow is unavailable for this Workspace.")

    def _current_workflows(self):
        threads = {t.thread_id: t for t in self.conversations.list_threads(self.owner)}
        canonical = {t.workflow_thread_id for t in threads.values() if t.workflow_thread_id}
        # Legacy empty conversations have no stored workflow ref. Bind their
        # freshly created controller in process, without writing on activation.
        transient = {workflow for workflow, thread in self.workflow_bindings.items()
                     if thread in threads and threads[thread].workflow_thread_id in (None, workflow)}
        return canonical | transient

    def _read_check(self, config):
        self.lease.check()
        if config.get("configurable", {}).get("thread_id") not in self.issued_workflows | self.retired_workflows:
            raise ValueError("Checkpoint workflow is unavailable for this Workspace.")

    def get_tuple(self, config):
        with self.lease.lock:
            self._read_check(config)
            return self.saver.get_tuple(config)

    def put(self, config, checkpoint, metadata, new_versions):
        with self.lease.lock:
            self._check(config); return self.saver.put(config, checkpoint, metadata, new_versions)

    def put_writes(self, config, writes, task_id, task_path=""):
        with self.lease.lock:
            self._check(config); return self.saver.put_writes(config, writes, task_id, task_path)

    def list(self, config, *, filter=None, before=None, limit=None):
        with self.lease.lock:
            self.lease.check()
            if config is not None: self._read_check(config)
            if before is not None: self._read_check(before)
            allowed = self._current_workflows()
            rows = [row for row in self.saver.list(config, filter=filter, before=before)
                    if row.config.get("configurable", {}).get("thread_id") in allowed]
            rows = rows if limit is None else rows[:limit]
        for row in rows:
            self.lease.check()
            yield row

    def cursor(self, *, transaction=True):
        """Preserve the installed SQLite diagnostic API, not a Runtime port."""
        self.lease.check()
        return self.saver.cursor(transaction=transaction)

    def delete_thread(self, thread_id):
        # Workspace calls this only after deleting an owned conversation. The
        # bundle records issued workflow identities without retaining content.
        with self.lease.lock:
            self.lease.check()
            if thread_id not in self.issued_workflows:
                raise ValueError("Checkpoint workflow is unavailable for this Workspace.")
            self.saver.delete_thread(thread_id)
            self.issued_workflows.discard(thread_id)
            self.retired_workflows.add(thread_id)
            self.workflow_bindings.pop(thread_id, None)

    def get_next_version(self, current, channel):
        return self.saver.get_next_version(current, channel)

    def clear(self):
        if isinstance(self.saver, InMemorySaver):
            # This saver belongs exclusively to the one-use storage bundle.
            # Drop every bucket, including orphaned writes/blobs, without
            # depending on best-effort per-thread cleanup succeeding.
            self.saver.storage.clear()
            self.saver.writes.clear()
            self.saver.blobs.clear()
        else:
            for thread in tuple(self.issued_workflows): self.saver.delete_thread(thread)
        self.issued_workflows.clear()
        self.retired_workflows.clear()
        self.workflow_bindings.clear()
