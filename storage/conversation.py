"""Process-only transcript adapter sharing the SQLite input validators."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ui.conversation_store import (
    ConversationThread, ConversationMessage, ScopeIdentity, ConversationStore,
    ConversationStoreError, ConversationNotFoundError, EMPTY_TITLE, INITIAL_TITLE_LIMIT,
    _scope, _identifier, _aware, _title, _content, _metadata, validate_snapshot,
)
from storage.contracts import StorageLease


class EphemeralConversationStore:
    def __init__(self, *, lease=None, clock=None):
        self.lease = lease or StorageLease()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._owners, self._threads, self._messages, self._snapshots, self._titles = {}, {}, {}, {}, set()

    def clear(self):
        self._owners.clear(); self._threads.clear(); self._messages.clear()
        self._snapshots.clear(); self._titles.clear()

    def _key(self, owner, thread):
        self.lease.check()
        key = (_scope(owner), _identifier(thread))
        if key not in self._threads:
            raise ConversationNotFoundError("Conversation is unavailable for this client scope.")
        return key

    def _now(self, owner):
        now = _aware(self._clock())
        previous = [t.updated_at for (o, _), t in self._threads.items() if o == owner]
        return max(now, max(previous) + timedelta(microseconds=1)) if previous else now

    def ensure_owner(self, owner_scope_id):
        with self.lease.lock:
            self.lease.check(); owner = _scope(owner_scope_id)
            if owner not in self._owners:
                self._owners[owner] = ScopeIdentity(owner, "subject_" + uuid4().hex)
            return self._owners[owner]

    def create_thread(self, owner_scope_id, *, workflow_thread_id=None, profile_id_ref=None,
                      profile_version_ref=None, snapshot=None):
        with self.lease.lock:
            owner = self.ensure_owner(owner_scope_id).owner_scope_id
            ConversationStore._refs(workflow_thread_id, profile_id_ref, profile_version_ref)
            snap = deepcopy(validate_snapshot(snapshot)); now = self._now(owner)
            thread = ConversationThread("conversation_" + uuid4().hex, owner, EMPTY_TITLE, now, now,
                                        workflow_thread_id, profile_id_ref, profile_version_ref)
            key = (owner, thread.thread_id)
            self._threads[key], self._messages[key], self._snapshots[key] = thread, [], snap
            return thread

    def get_thread(self, owner_scope_id, thread_id):
        with self.lease.lock:
            return self._threads[self._key(owner_scope_id, thread_id)]

    def list_threads(self, owner_scope_id):
        with self.lease.lock:
            self.lease.check(); owner = _scope(owner_scope_id)
            values = sorted((t for (o, _), t in self._threads.items() if o == owner), key=lambda t: t.thread_id)
            return tuple(sorted(values, key=lambda t: t.updated_at, reverse=True))

    def list_messages(self, owner_scope_id, thread_id, *, limit=None):
        with self.lease.lock:
            key = self._key(owner_scope_id, thread_id)
            if limit is not None and (type(limit) is not int or not 1 <= limit <= 12):
                raise ConversationStoreError("Runtime history limit is invalid.")
            return tuple(deepcopy(self._messages[key][-limit:] if limit else self._messages[key]))

    def load_snapshot(self, owner_scope_id, thread_id):
        with self.lease.lock:
            return deepcopy(validate_snapshot(self._snapshots[self._key(owner_scope_id, thread_id)]))

    def rename_thread(self, owner_scope_id, thread_id, title):
        with self.lease.lock:
            key = self._key(owner_scope_id, thread_id); normalized = _title(title)
            self._threads[key] = replace(self._threads[key], title=normalized, updated_at=self._now(key[0]))
            self._titles.add(key)
            return self._threads[key]

    def delete_thread(self, owner_scope_id, thread_id):
        with self.lease.lock:
            key = self._key(owner_scope_id, thread_id); thread = self._threads.pop(key)
            self._messages.pop(key); self._snapshots.pop(key); self._titles.discard(key)
            return thread

    def _save(self, key, *, snapshot=None, workflow_thread_id=None, profile_id_ref=None, profile_version_ref=None, title=None):
        ConversationStore._refs(workflow_thread_id, profile_id_ref, profile_version_ref)
        snap = deepcopy(validate_snapshot(snapshot)) if snapshot is not None else self._snapshots[key]
        old = self._threads[key]
        new = replace(old, updated_at=self._now(key[0]), title=title if title is not None else old.title,
            workflow_thread_id=workflow_thread_id if workflow_thread_id is not None else old.workflow_thread_id,
            profile_id_ref=profile_id_ref if profile_id_ref is not None else old.profile_id_ref,
            profile_version_ref=profile_version_ref if profile_version_ref is not None else old.profile_version_ref)
        self._threads[key], self._snapshots[key] = new, snap
        if title is not None: self._titles.add(key)
        return new

    def append_turn(self, owner_scope_id, thread_id, user_content, assistant_content, *,
                    user_metadata=None, assistant_metadata=None, snapshot=None,
                    workflow_thread_id=None, profile_id_ref=None, profile_version_ref=None, turn_id=None):
        with self.lease.lock:
            key = self._key(owner_scope_id, thread_id)
            user, assistant = _content(user_content), _content(assistant_content)
            meta = (_metadata(user_metadata), _metadata(assistant_metadata))
            if turn_id is not None:
                _identifier(turn_id); existing = self.get_turn(*key, turn_id)
                if existing:
                    if (existing[0].content, existing[1].content) != (user, assistant):
                        raise ConversationStoreError("Turn identity has already completed.")
                    return existing
                ids = {m.message_id for k, messages in self._messages.items() if k[0] == key[0] for m in messages}
                if any(f"message_{turn_id}_{role}" in ids for role in ("user", "assistant")):
                    raise ConversationStoreError("Turn identity belongs to another conversation.")
            title = " ".join(user.split())[:INITIAL_TITLE_LIMIT] if key not in self._titles else None
            saved = self._save(key, snapshot=snapshot, workflow_thread_id=workflow_thread_id,
                               profile_id_ref=profile_id_ref, profile_version_ref=profile_version_ref, title=title)
            pair = tuple(ConversationMessage(f"message_{turn_id}_{role}" if turn_id else "message_" + uuid4().hex,
                thread_id, role, content, saved.updated_at, deepcopy(metadata))
                for role, content, metadata in zip(("user", "assistant"), (user, assistant), meta))
            self._messages[key].extend(pair)
            return deepcopy(pair)

    def get_turn(self, owner_scope_id, thread_id, turn_id):
        with self.lease.lock:
            key = self._key(owner_scope_id, thread_id); _identifier(turn_id)
            ids = {f"message_{turn_id}_user", f"message_{turn_id}_assistant"}
            pair = tuple(m for m in self._messages[key] if m.message_id in ids)
            if len(pair) not in (0, 2): raise ConversationStoreError("Incomplete stored turn.")
            return deepcopy(pair)

    def annotate_cancelled_turn(self, owner_scope_id, thread_id, turn_id, partial_text, metadata):
        with self.lease.lock:
            key = self._key(owner_scope_id, thread_id); meta = _metadata(metadata)
            pair = self.get_turn(*key, turn_id)
            if (meta.get("agent_turn_status") != "CANCELLED" or meta.get("suggestions") or meta.get("evidence_refs")
                    or "agent_profile_stamp" in meta or "agent_failure" in meta):
                raise ConversationStoreError("Cancelled turns cannot confer authority.")
            if not pair or pair[-1].content != partial_text or pair[-1].metadata.get("agent_turn_status") != "CANCELLED":
                raise ConversationStoreError("Cancelled turn identity is invalid.")
            self._messages[key] = [replace(m, metadata=deepcopy(meta)) if m.message_id == pair[-1].message_id else m
                                   for m in self._messages[key]]

    def save_snapshot(self, owner_scope_id, thread_id, snapshot, **refs):
        with self.lease.lock:
            return self._save(self._key(owner_scope_id, thread_id), snapshot=snapshot, **refs)
