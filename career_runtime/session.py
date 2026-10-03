"""Consent, idempotent final-turn persistence and transient candidate review."""

from dataclasses import dataclass, replace
from pathlib import Path
import sqlite3
from uuid import uuid4

from career_runtime.engine import OrangeRuntime, TurnComplete, TurnFailed
from career_runtime.streaming import StreamingQwenProvider
from career_runtime.models import SafeFailure, StreamMetrics
from career_runtime.models import PreviousTurn, TurnStatus
from career_runtime.continuity import previous_from_messages, failure_status
from career_runtime.diagnostics import RuntimeDiagnostic
from time import perf_counter
from providers.models import load_llm_settings
from observability.context import diagnostic_scope
from observability.events import emit
from observability.models import DiagnosticComponent as DC, DiagnosticStatus as DS

CONSENT_VERSION = "selected-context-v1"
FAILURE_TEXT = "本次回答未能完整验证或连接中断，未保存临时生成内容。你可以稍后重新发送。"
INTERRUPTED_TEXT = "回答生成中断，未保存未完成的内容。你可以稍后重新发送。"
VALIDATION_TEXT = "回答验证失败，未保存本次生成内容。你可以稍后重新发送。"
PERSISTENCE_TEXT = "回答暂时无法保存，请稍后再试。"


def failure_text(failure):
    if failure is None:
        return FAILURE_TEXT
    if failure.reason == "persistence_error":
        return PERSISTENCE_TEXT
    if failure.reason in {"output_limit", "transport_incomplete", "stream_interrupted"}:
        return INTERRUPTED_TEXT
    if failure.reason in {"invalid_core", "unknown_reference", "invented_candidate", "stream_mismatch", "runtime_history_claim"}:
        return VALIDATION_TEXT
    return FAILURE_TEXT


def completed_metadata(event):
    """Sanitize optional presentation fields BEFORE the strict atomic store call.

    The store itself stays strict. Evidence ownership and candidate authority are
    not optional; neither is reinterpreted by this presentation adapter.
    """
    from ui.conversation_store import _metadata
    metadata = _metadata({"kind": "text", "evidence_refs": event.answer.citations, "agent_turn_status": "COMPLETED"})
    profile = event.registry.profile()
    stamp = event.registry.context_profile_stamp
    if profile is not None and event.answer.citations and stamp == {"profile_id": profile.profile_id, "version": profile.version}:
        metadata.update(_metadata({"agent_profile_stamp": stamp}))
    optional = {"suggestions": lambda: event.answer.suggestions, "agent_usage": lambda: list(event.usage),
        "agent_diagnostics": lambda: [item.model_dump() for item in event.diagnostics],
        "agent_accounting": lambda: event.accounting.model_dump(),
        "agent_provider_attempts": lambda: [item.model_dump() for item in event.provider_attempts],
        "agent_activity": lambda: [item.model_dump() for item in event.activities]}
    degraded = False
    for key, value in optional.items():
        try:
            metadata.update(_metadata({key: value()}))
        except (ValueError, TypeError, AttributeError):
            degraded = True
            if key == "suggestions":
                metadata[key] = []
    metrics = (event.stream_metrics or StreamMetrics()).model_copy(update={"persistence_committed": True})
    if degraded:
        metrics = metrics.model_copy(update={"optional_metadata_valid": False, "degraded_optional_metadata": True})
    metadata["agent_stream"] = metrics.model_dump()
    return metadata, metrics


@dataclass
class PendingTurn:
    turn_id: str
    thread_id: str
    text: str
    source: str
    allow_proposal: bool = False


class AgentSession:
    def __init__(self, workspace, *, provider_factory=None):
        self.workspace = workspace
        self.provider_factory = provider_factory or self._live_provider
        self.provider = None
        self.pending: PendingTurn | None = None
        self.last_result: TurnComplete | None = None
        self.last_error: str | None = None
        self.last_failure: SafeFailure | None = None
        self.failure_persisted = False
        self.path = workspace.runtime_root / "agent_settings.sqlite3"
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS consent (owner TEXT PRIMARY KEY, version TEXT NOT NULL, granted INTEGER NOT NULL CHECK(granted IN (0,1)))")
            # Additive, content-free receipt. Separate settings storage can retain
            # a failed-persistence/cancelled attempt when no message pair exists.
            db.execute("""CREATE TABLE IF NOT EXISTS turn_receipts (
                owner TEXT NOT NULL, thread_id TEXT NOT NULL, turn_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('COMPLETED','FAILED_TRANSPORT','FAILED_VALIDATION','FAILED_PERSISTENCE','CANCELLED','UNKNOWN')),
                previous_assistant_id TEXT NOT NULL, PRIMARY KEY(owner,thread_id))""")

    def previous_turn(self, thread_id=None):
        thread_id = thread_id or self.workspace.thread.thread_id
        messages = self.workspace.store.list_messages(self.workspace.owner_scope_id, thread_id, limit=12)
        previous = previous_from_messages(messages)
        with sqlite3.connect(self.path) as db:
            receipt = db.execute("SELECT turn_id,status,previous_assistant_id FROM turn_receipts WHERE owner=? AND thread_id=?",
                (self.workspace.owner_scope_id, thread_id)).fetchone()
        if receipt:
            turn_id, status, anchor = receipt
            stored = self.workspace.store.get_turn(self.workspace.owner_scope_id, thread_id, turn_id)
            if stored and previous.assistant_message_id == stored[-1].message_id:
                return previous  # Canonical message commit beats a lost receipt acknowledgement.
            if previous.assistant_message_id == anchor:
                return PreviousTurn(status=TurnStatus.UNKNOWN if status == "COMPLETED" else TurnStatus(status))
        return previous

    def _record_turn(self, pending, status, anchor):
        self.workspace.store.get_thread(self.workspace.owner_scope_id, pending.thread_id)
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO turn_receipts VALUES (?,?,?,?,?) ON CONFLICT(owner,thread_id) DO UPDATE SET turn_id=excluded.turn_id,status=excluded.status,previous_assistant_id=excluded.previous_assistant_id",
                (self.workspace.owner_scope_id, pending.thread_id, pending.turn_id, TurnStatus(status).value, anchor))

    def cancel_pending(self):
        if self.pending is not None:
            try:
                messages = self.workspace.store.list_messages(self.workspace.owner_scope_id, self.pending.thread_id, limit=12)
                self._record_turn(self.pending, TurnStatus.CANCELLED, previous_from_messages(messages).assistant_message_id)
            except ValueError:
                pass  # A deleted/out-of-scope conversation is never recreated.
            self.pending = None

    @staticmethod
    def _live_provider():
        settings = load_llm_settings(Path(__file__).resolve().parents[1])
        return StreamingQwenProvider.from_settings(settings)

    @property
    def consent(self):
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT version, granted FROM consent WHERE owner = ?", (self.workspace.owner_scope_id,)).fetchone()
        return bool(row and row == (CONSENT_VERSION, 1))

    def set_consent(self, *, granted: bool):
        if type(granted) is not bool:
            raise ValueError("Consent must be explicit.")
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO consent VALUES (?, ?, ?) ON CONFLICT(owner) DO UPDATE SET version=excluded.version, granted=excluded.granted",
                       (self.workspace.owner_scope_id, CONSENT_VERSION, int(granted)))
        if not granted:
            self.cancel_pending()
            self.provider = None
            self.pending = None
            self.last_result = None

    def queue(self, text, source, *, allow_proposal=False):
        from ui.conversation_store import _content
        _content(text)
        if not self.consent or source not in {"typed", "suggestion"}:
            raise PermissionError("Provider consent is required.")
        if len(text) > 2000 or self.pending is not None:
            raise ValueError("One bounded turn at a time.")
        self.pending = PendingTurn(uuid4().hex, self.workspace.thread.thread_id, text, source, allow_proposal)

    def stream_turn(self, pending: PendingTurn):
        """No history replay; a committed request ID never runs a provider twice."""
        workspace = self.workspace
        if workspace.store.get_turn(workspace.owner_scope_id, pending.thread_id, pending.turn_id):
            return
        finished = False
        started = perf_counter()
        failure, usage = None, ()
        details, accounting, attempts = (), None, ()
        metrics = None
        persisting = False
        cancelled = False
        anchor = ""
        self.last_result, self.last_error = None, None
        self.last_failure, self.failure_persisted = None, False
        try:
            if not self.consent or workspace.thread.thread_id != pending.thread_id:
                raise PermissionError("Turn no longer active.")
            previous = self.previous_turn(pending.thread_id)
            anchor = previous_from_messages(workspace.store.list_messages(workspace.owner_scope_id, pending.thread_id, limit=12)).assistant_message_id
            persisting = True
            self._record_turn(pending, TurnStatus.UNKNOWN, anchor)
            persisting = False
            if self.provider is None:
                self.provider = self.provider_factory()
            runtime = OrangeRuntime(self.provider, planning_retries=0)
            controller = workspace.controller
            with diagnostic_scope(controller.diagnostic_collector, controller.diagnostic_context):
                for event in runtime.run(workspace, pending.text, consent=self.consent,
                                         proposal_permission=pending.allow_proposal, previous_turn=previous):
                    if not self.consent or workspace.thread.thread_id != pending.thread_id:
                        raise PermissionError("Turn cancelled.")
                    if isinstance(event, TurnComplete):
                        metadata, metrics = completed_metadata(event)
                        details, accounting, attempts, usage = event.diagnostics, event.accounting, event.provider_attempts, event.usage
                        persisting = True
                        try:
                            workspace.store.append_turn(workspace.owner_scope_id, pending.thread_id, pending.text,
                                event.answer.visible_response, turn_id=pending.turn_id,
                                user_metadata={"source": pending.source}, assistant_metadata=metadata,
                                snapshot=workspace._snapshot())
                        except (ValueError, sqlite3.Error):
                            # Reconcile a lost commit acknowledgement WITHOUT another write/model call.
                            stored = workspace.store.get_turn(workspace.owner_scope_id, pending.thread_id, pending.turn_id)
                            if not stored or (stored[0].content, stored[1].content) != (pending.text, event.answer.visible_response):
                                raise
                        event = replace(event, stream_metrics=metrics)
                        self.last_result = event
                        finished = True
                        try:
                            self._record_turn(pending, TurnStatus.COMPLETED, anchor)
                        except (ValueError, sqlite3.Error):
                            pass  # Committed message metadata remains authoritative.
                        emit(DC.CONVERSATION, "agent_turn", DS.SUCCEEDED, agent_detail=RuntimeDiagnostic(
                            stage="persistence", status="succeeded", error_category="none", stream=metrics))
                    elif isinstance(event, TurnFailed):
                        self.last_error = event.category
                        failure, usage = event.diagnostic, event.usage
                        details, accounting, attempts = event.diagnostics, event.accounting, event.provider_attempts
                        metrics = event.stream_metrics
                    yield event
        except GeneratorExit:
            cancelled = True
            raise
        except Exception as exc:
            cancelled = isinstance(exc, PermissionError)
            self.last_error = self.last_error or "provider_unavailable"
            failure = failure or SafeFailure(category="runtime_failure" if persisting else "provider_unavailable",
                stage="persistence" if persisting else "provider_setup", reason="persistence_error" if persisting else "execution_error",
                latency_ms=round((perf_counter()-started)*1000))
            if persisting:
                metrics = metrics.model_copy(update={"persistence_committed": False}) if metrics else None
                detail = RuntimeDiagnostic(stage="persistence", status="failed", error_category="validation_failure", stream=metrics)
                details = (*details, detail)
                emit(DC.CONVERSATION, "agent_turn", DS.FAILED, agent_detail=detail)
        finally:
            self.last_failure = failure
            if not finished:
                status = TurnStatus.CANCELLED if cancelled else failure_status(failure)
                try:
                    self._record_turn(pending, status, anchor)
                except (ValueError, sqlite3.Error):
                    pass  # Initial UNKNOWN receipt never claims an unavailable commit.
                try:
                    workspace.store.append_turn(workspace.owner_scope_id, pending.thread_id, pending.text,
                        failure_text(failure), turn_id=pending.turn_id, user_metadata={"source": pending.source},
                        assistant_metadata={"kind": "text", "agent_turn_status": status.value, "agent_usage": list(usage),
                            "agent_diagnostics": [item.model_dump() for item in details],
                            "agent_provider_attempts": [item.model_dump() for item in attempts],
                            **({"agent_accounting": accounting.model_dump()} if accounting is not None else {}),
                            **({"agent_stream": metrics.model_dump()} if metrics is not None else {}),
                            **({"agent_failure": failure.model_dump()} if failure is not None else {}),
                            "agent_activity": [{"stage": "failed", "status": "failed"}]})
                    self.failure_persisted = True
                except (ValueError, sqlite3.Error):
                    pass  # Deleted/out-of-scope threads are never recreated.
            if workspace.thread.thread_id == pending.thread_id:
                collector, context = workspace.controller.diagnostic_collector, workspace.controller.diagnostic_context
                events = collector.timeline(context.run_id)
                workspace.activate(pending.thread_id)
                workspace.controller.diagnostic_context = context
                for event in events:
                    workspace.controller.diagnostic_collector.record(event)
