"""Consent and content-free receipts; preserve the existing SQLite tables."""

from enum import Enum
import sqlite3
from pathlib import Path
from ui.conversation_store import _identifier
from career_runtime.models import TurnStatus
from storage.contracts import StorageLease


class ConsentCategory(str, Enum):
    AI_CHAT = "ai_chat"
    RESUME_ANALYSIS = "resume_analysis"
    PROFILE_REVIEW = "profile_review"


def scope_key(category, version, request_scope):
    category = ConsentCategory(category).value
    _identifier(version)
    if not version: raise ValueError("Consent version is required.")
    if request_scope is not None and (not isinstance(request_scope, str) or not request_scope):
        raise ValueError("Consent request scope must be an opaque binding.")
    _identifier(request_scope)
    return category, version, request_scope


class EphemeralSettingsStore:
    def __init__(self, owner, conversations, lease=None):
        self.owner, self.conversations = owner, conversations
        self.lease = lease or StorageLease()
        self._consent, self._receipts, self._requests = {}, {}, {}

    def open(self): self.lease.check()

    def _check(self, owner, thread=None):
        self.lease.check()
        if owner != self.owner: raise ValueError("Settings scope is unavailable.")
        if thread is not None: self.conversations.get_thread(owner, thread)

    def valid(self, owner, category, version, *, request_scope=None):
        with self.lease.lock:
            self._check(owner); c, v, s = scope_key(category, version, request_scope)
            return self._consent.get(c) == (v, s, True)

    def set(self, owner, category, version, *, granted, request_scope=None):
        with self.lease.lock:
            self._check(owner); c, v, s = scope_key(category, version, request_scope)
            if type(granted) is not bool: raise ValueError("Consent must be explicit.")
            self._consent[c] = (v, s, granted)

    def revoke(self, owner, category):
        with self.lease.lock:
            self._check(owner); self._consent.pop(ConsentCategory(category).value, None)

    def get_receipt(self, owner, thread):
        with self.lease.lock:
            self._check(owner, thread); return self._receipts.get(thread)

    def record_receipt(self, owner, thread, turn, status, anchor):
        with self.lease.lock:
            self._check(owner, thread); _identifier(turn)
            if not turn: raise ValueError("Request identity is required.")
            if anchor: _identifier(anchor)
            status = TurnStatus(status).value
            if turn in self._requests and self._requests[turn] != thread:
                raise ValueError("Request identity belongs to another conversation.")
            self._requests[turn] = thread
            self._receipts[thread] = (turn, status, anchor)

    def clear(self): self._consent.clear(); self._receipts.clear(); self._requests.clear()


class SQLiteSettingsStore(EphemeralSettingsStore):
    """Old AI-chat/receipt schema unchanged; extra scoped categories use a separate file.

    The additional file is created only by an explicit scoped-consent operation,
    never by migration of an existing private database.
    """

    def __init__(self, owner, conversations, path, lease=None):
        super().__init__(owner, conversations, lease)
        self.path = Path(path)
        self._initialized = False

    def _initialize(self):
        self.lease.check()
        if self._initialized: return
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS consent (owner TEXT PRIMARY KEY, version TEXT NOT NULL, granted INTEGER NOT NULL CHECK(granted IN (0,1)))")
            db.execute("""CREATE TABLE IF NOT EXISTS turn_receipts (
                owner TEXT NOT NULL, thread_id TEXT NOT NULL, turn_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('COMPLETED','FAILED_TRANSPORT','FAILED_VALIDATION','FAILED_PERSISTENCE','CANCELLED','UNKNOWN')),
                previous_assistant_id TEXT NOT NULL, PRIMARY KEY(owner,thread_id))""")
        self._initialized = True

    def open(self):
        with self.lease.lock: self._initialize()

    def _scoped(self):
        path = self.path.with_name("scoped_consent.sqlite3")
        db = sqlite3.connect(path)
        db.execute("CREATE TABLE IF NOT EXISTS scoped_consent (owner TEXT NOT NULL, category TEXT NOT NULL, version TEXT NOT NULL, scope TEXT, granted INTEGER NOT NULL, PRIMARY KEY(owner,category))")
        return db

    def valid(self, owner, category, version, *, request_scope=None):
        with self.lease.lock:
            self._check(owner); c, v, s = scope_key(category, version, request_scope)
            if c == ConsentCategory.AI_CHAT and s is None:
                self._initialize()
                with sqlite3.connect(self.path) as db:
                    row = db.execute("SELECT version, granted FROM consent WHERE owner=?", (owner,)).fetchone()
                return bool(row and row == (v, 1))
            path = self.path.with_name("scoped_consent.sqlite3")
            if not path.exists(): return False
            db = self._scoped()
            try:
                row = db.execute("SELECT version,scope,granted FROM scoped_consent WHERE owner=? AND category=?", (owner,c)).fetchone()
                return bool(row and row == (v,s,1))
            finally: db.close()

    def _write_ai_consent(self, owner, version, scope, granted, *, revoke=False):
        """Replace broad/scoped AI consent atomically, without migrating old tables."""
        self._initialize()
        scoped_path = self.path.with_name("scoped_consent.sqlite3")
        if scope is not None:
            # Only an explicit scoped operation creates this separate store.
            self._scoped().close()
        with sqlite3.connect(self.path) as db:
            attached = scoped_path.exists()
            if attached:
                db.execute("ATTACH DATABASE ? AS scoped", (str(scoped_path),))
            # Both deletes and the replacement share one rollback transaction.
            db.execute("DELETE FROM consent WHERE owner=?", (owner,))
            if attached:
                db.execute("DELETE FROM scoped.scoped_consent WHERE owner=? AND category=?", (owner, ConsentCategory.AI_CHAT.value))
            if not revoke:
                if scope is None:
                    db.execute("INSERT INTO consent VALUES (?,?,?)", (owner, version, int(granted)))
                else:
                    db.execute("INSERT INTO scoped.scoped_consent VALUES (?,?,?,?,?)", (owner, ConsentCategory.AI_CHAT.value, version, scope, int(granted)))

    def set(self, owner, category, version, *, granted, request_scope=None):
        with self.lease.lock:
            self._check(owner); c, v, s = scope_key(category, version, request_scope)
            if type(granted) is not bool: raise ValueError("Consent must be explicit.")
            if c == ConsentCategory.AI_CHAT:
                self._write_ai_consent(owner, v, s, granted)
            else:
                db = self._scoped()
                try:
                    with db: db.execute("INSERT INTO scoped_consent VALUES (?,?,?,?,?) ON CONFLICT(owner,category) DO UPDATE SET version=excluded.version,scope=excluded.scope,granted=excluded.granted", (owner,c,v,s,int(granted)))
                finally: db.close()

    def revoke(self, owner, category):
        with self.lease.lock:
            self._check(owner); c = ConsentCategory(category).value
            if c == ConsentCategory.AI_CHAT:
                self._write_ai_consent(owner, None, None, False, revoke=True)
            elif self.path.with_name("scoped_consent.sqlite3").exists():
                db = self._scoped()
                try:
                    with db: db.execute("DELETE FROM scoped_consent WHERE owner=? AND category=?", (owner,c))
                finally: db.close()

    def get_receipt(self, owner, thread):
        with self.lease.lock:
            self._check(owner,thread); self._initialize()
            with sqlite3.connect(self.path) as db:
                return db.execute("SELECT turn_id,status,previous_assistant_id FROM turn_receipts WHERE owner=? AND thread_id=?", (owner,thread)).fetchone()

    def record_receipt(self, owner, thread, turn, status, anchor):
        with self.lease.lock:
            self._check(owner,thread); _identifier(turn)
            if not turn: raise ValueError("Request identity is required.")
            if anchor: _identifier(anchor)
            status = TurnStatus(status).value; self._initialize()
            if turn in self._requests and self._requests[turn] != thread:
                raise ValueError("Request identity belongs to another conversation.")
            with sqlite3.connect(self.path) as db:
                if db.execute("SELECT 1 FROM turn_receipts WHERE owner=? AND turn_id=? AND thread_id!=?", (owner,turn,thread)).fetchone():
                    raise ValueError("Request identity belongs to another conversation.")
                db.execute("INSERT INTO turn_receipts VALUES (?,?,?,?,?) ON CONFLICT(owner,thread_id) DO UPDATE SET turn_id=excluded.turn_id,status=excluded.status,previous_assistant_id=excluded.previous_assistant_id", (owner,thread,turn,status,anchor))
            self._requests[turn] = thread
