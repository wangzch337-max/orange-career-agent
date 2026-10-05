"""Consent, idempotent final-turn persistence and transient candidate review."""

from dataclasses import dataclass, field, replace
from contextlib import closing
from pathlib import Path
import sqlite3
from uuid import uuid4
from threading import Event, Thread, RLock
from types import SimpleNamespace

from career_runtime.engine import OrangeRuntime, TurnComplete, TurnFailed, TurnCancelled, AnswerDelta
from career_runtime.cancellation import TurnControl, CancellationRequested, GenerationIdentity
from career_runtime.streaming import StreamingQwenProvider
from career_runtime.models import SafeFailure, StreamMetrics, Activity, length_bucket
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
CANCELLED_TEXT = "已停止生成"
MAX_TRACKED_EXECUTIONS = 3  # Includes active execution and still-closing generations.


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


class ExecutionView(SimpleNamespace):
    """Borrow pinned canonical state; state access is not a generation lease."""

    @property
    def chat(self):
        """Read-only binding to the chat owned by the original Workspace."""
        return self._canonical_chat


@dataclass
class TurnExecution:
    identity: GenerationIdentity
    pending: PendingTurn
    control: TurnControl
    view: object
    done: Event = field(default_factory=Event)
    worker: Thread | None = None
    provider: object = None
    running: bool = False
    cancel_committed: bool = False
    released: bool = False


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
        self.last_cancelled: TurnCancelled | None = None
        self._control = None
        self._active_pending = None
        self._executing = False
        self._worker = None
        self._worker_done = Event()
        self._lock = RLock()
        self._generation = None
        self._executions = {}
        self._closed = False
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
        if self.busy:
            self.request_cancel()
            return
        if self.pending is not None:
            try:
                messages = self.workspace.store.list_messages(self.workspace.owner_scope_id, self.pending.thread_id, limit=12)
                self._record_turn(self.pending, TurnStatus.CANCELLED, previous_from_messages(messages).assistant_message_id)
            except ValueError:
                pass  # A deleted/out-of-scope conversation is never recreated.
            self.pending = None
            if self._generation is not None:
                self._generation.control.request()
                self._generation.released = True
                self._generation.done.set()
            self._active_pending, self._control = None, None

    @property
    def busy(self):
        generation = self._generation
        return bool(generation and generation.running and not generation.released)

    def _owns(self, generation):
        identity = generation.identity
        return (not self._closed and not self.workspace._closed and self._generation is generation
            and self.workspace.owner_scope_id == identity.owner_scope_id
            and self.workspace.thread.thread_id == identity.thread_id)

    def _new_generation(self, pending):
        self._reap_cleanup()
        if len(self._executions) >= MAX_TRACKED_EXECUTIONS:
            raise ValueError("当前暂时无法开始新回答，请稍后再试。")
        workspace = self.workspace
        if pending.thread_id != workspace.thread.thread_id:
            raise ValueError("Generation must own the selected thread.")
        identity = GenerationIdentity(uuid4().hex, workspace.owner_scope_id, pending.thread_id, pending.turn_id)
        control = TurnControl(lock=self._lock, identity=identity)
        # Pin original thread/controller; old workers never follow navigation.
        view = ExecutionView(owner_scope_id=identity.owner_scope_id, subject_id=workspace.subject_id,
            thread=workspace.thread, controller=workspace.controller, store=workspace.store,
            memory_service=workspace.memory_service, _canonical_chat=workspace.chat)
        generation = TurnExecution(identity, pending, control, view)
        control._owns = lambda: self._owns(generation)
        self._generation = generation
        self._executions[identity.generation_id] = generation
        self._active_pending, self._control = pending, control
        self._worker_done = generation.done
        self._worker = None
        return generation

    def _reap_cleanup(self):
        with self._lock:
            for key, generation in tuple(self._executions.items()):
                if generation.done.is_set() and generation.control.cleanup_idle:
                    if generation.control.requested:
                        generation.control.note("cleanup_finished")
                    generation.control.registry = None
                    generation.control.final_event = None
                    del self._executions[key]

    def cleanup_status(self):
        """Structural lifecycle only; never source/response/provider payloads."""
        self._reap_cleanup()
        return {"tracked": len(self._executions), "limit": MAX_TRACKED_EXECUTIONS,
            "pending_cleanup": sum(item.control.requested for item in self._executions.values())}

    def require_idle(self):
        if self.busy:
            raise ValueError("Stop generation and wait for cancellation before navigation.")

    @property
    def cancellation_requested(self):
        return bool(self._control and self._control.requested)

    def request_cancel(self):
        """One UI action: freeze projection, persist CANCELLED, then close local IO."""
        with self._lock:
            generation = self._generation
            if generation is None or not self._owns(generation):
                return False
            pending, control = generation.pending, generation.control
            stored = self.workspace.store.get_turn(self.workspace.owner_scope_id, pending.thread_id, pending.turn_id)
            if stored:
                control.completed = stored[-1].metadata.get("agent_turn_status") == "COMPLETED"
                return False
            if not control.request():
                return False
            self.last_result = None
            self.last_error = self.last_failure = None
            if not self._persist_cancelled(generation):
                return False  # Never claim UI release before essential persistence.
            generation.cancel_committed = generation.released = True
            if generation.worker is None and not generation.running:
                generation.done.set()  # No physical execution exists to finish later.
            control.note("cancel_committed")
            self._executing = False
            self.pending = None
            self._reload(pending)
            control.ui_release_latency_ms = round((perf_counter()-control.cancel_started)*1000)
            control.note("ui_released")
        return True

    def _persist_cancelled(self, generation, event=None):
        pending, control = generation.pending, generation.control
        text = control.partial
        metrics = (event.stream_metrics if event else None) or (control.provider_metrics[0] if control.response_started else None) or StreamMetrics()
        metrics = metrics.model_copy(update={"cancellation_requested": True, "partial_response": bool(text),
            "core_valid": False, "optional_metadata_valid": False, "persistence_committed": True,
            "visible_length_bucket": length_bucket(len(text)), "local_close_attempted": control.close_attempted,
            "close_failed": metrics.close_failed or control.close_failed})
        if not metrics.transport_completed:
            metrics = metrics.model_copy(update={"provider_finish_category": "cancelled"})
        metadata = {"kind": "text", "agent_turn_status": "CANCELLED", "suggestions": [],
            "agent_stream": metrics.model_dump(), "agent_activity": [],
            "agent_usage": list(event.usage) if event else [],
            "agent_provider_attempts": [item.model_dump() for item in event.provider_attempts] if event else []}
        if event:
            metadata.update(agent_accounting=event.accounting.model_dump(),
                            agent_diagnostics=[item.model_dump() for item in event.diagnostics])
        try:
            messages = self.workspace.store.list_messages(self.workspace.owner_scope_id, pending.thread_id, limit=12)
            self.workspace.store.append_turn(self.workspace.owner_scope_id, pending.thread_id, pending.text,
                text or CANCELLED_TEXT, turn_id=pending.turn_id, user_metadata={"source": pending.source},
                assistant_metadata=metadata)
            if event and generation.cancel_committed:
                self.workspace.store.annotate_cancelled_turn(self.workspace.owner_scope_id, pending.thread_id,
                    pending.turn_id, text or CANCELLED_TEXT, metadata)
            self.failure_persisted = True
            try:
                self._record_turn(pending, TurnStatus.CANCELLED, previous_from_messages(messages).assistant_message_id)
            except (ValueError, sqlite3.Error):
                pass  # Canonical CANCELLED pair is authoritative over a receipt.
            return True
        except (ValueError, sqlite3.Error):
            try:
                pair = self.workspace.store.get_turn(self.workspace.owner_scope_id, pending.thread_id, pending.turn_id)
                if pair and pair[-1].metadata.get("agent_turn_status") == "CANCELLED" and pair[-1].content == (text or CANCELLED_TEXT):
                    self.failure_persisted = True
                    return True  # Reconcile lost acknowledgement without another write.
            except (ValueError, sqlite3.Error):
                pass
            self.last_error = "persistence_error"
            self.last_failure = SafeFailure(category="runtime_failure", stage="persistence", reason="persistence_error", latency_ms=0)
            return False

    def _reload(self, pending):
        if self.workspace.thread.thread_id != pending.thread_id:
            return
        collector, context = self.workspace.controller.diagnostic_collector, self.workspace.controller.diagnostic_context
        events = collector.timeline(context.run_id)
        self.workspace.activate(pending.thread_id)
        self.workspace.controller.diagnostic_context = context
        for event in events:
            self.workspace.controller.diagnostic_collector.record(event)

    def start_pending(self):
        """Owned worker does IO only; it never calls a Streamlit UI API."""
        if self.pending is None or self.busy:
            return
        pending, self.pending = self.pending, None
        generation = self._generation
        self._active_pending = pending
        if self._control is None:
            self._control = TurnControl(background=True)
        self._control.background = True
        generation.control.background = True
        generation.running = True
        def consume():
            try:
                for _event in self.stream_turn(pending, _generation=generation):
                    pass
            finally:
                generation.done.set()
        self._worker = generation.worker = Thread(target=consume, name="orange-agent-turn", daemon=True)
        self._worker.start()
        # Bounded first-frame coalescing avoids flashing a streaming state for
        # locally completed turns. Slow IO stays in the worker, never awaited.
        self._worker_done.wait(.25)

    def progress(self):
        if self._control is None or self._active_pending is None:
            return None
        text, activities, cancelled = self._control.snapshot()
        return self._active_pending, text, activities, cancelled

    def finish_background(self):
        self._reap_cleanup()
        if self._worker is None or not self._worker_done.is_set():
            return False
        self._worker.join()
        self._worker = None
        pending = self._active_pending
        # A completed old worker cannot reload a deleted/navigated/closed view.
        if (pending is not None and not self._closed and not self.workspace._closed
                and self.workspace.thread.thread_id == pending.thread_id
                and self.workspace.store.get_turn(self.workspace.owner_scope_id, pending.thread_id, pending.turn_id)):
            self._reload(pending)
        self._active_pending = None
        return True  # Also restore controls after a sanitized persistence failure.

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
            if not self.busy:
                self.provider = None
            self.pending = None
            self.last_result = None

    def queue(self, text, source, *, allow_proposal=False):
        from ui.conversation_store import _content
        _content(text)
        if not self.consent or source not in {"typed", "suggestion"}:
            raise PermissionError("Provider consent is required.")
        with self._lock:
            if self._closed or len(text) > 2000 or self.pending is not None or self.busy:
                raise ValueError("One bounded turn at a time.")
            pending = PendingTurn(uuid4().hex, self.workspace.thread.thread_id, text, source, allow_proposal)
            self._new_generation(pending)
            self.pending = pending
            self.last_result = self.last_cancelled = None

    def stream_turn(self, pending: PendingTurn, *, _generation=None):
        """No history replay; a committed request ID never runs a provider twice."""
        workspace = self.workspace
        with self._lock:
            if _generation is not None and (not self._owns(_generation) or _generation.control.requested):
                _generation.done.set()
                return
            if self._closed or workspace._closed or workspace.thread.thread_id != pending.thread_id:
                return
            if workspace.store.get_turn(workspace.owner_scope_id, pending.thread_id, pending.turn_id):
                return
            generation = _generation or self._generation
            if generation is None or generation.pending is not pending:
                if self.busy:
                    raise ValueError("Another turn is already executing.")
                generation = self._new_generation(pending)
            control = generation.control
            control.checkpoint()
            generation.running = True
            self._executing = True
            self.last_result, self.last_error = None, None
            self.last_failure, self.failure_persisted = None, False
        finished = False
        started = perf_counter()
        failure, usage = None, ()
        details, accounting, attempts = (), None, ()
        metrics = None
        persisting = False
        cancelled = False
        anchor = ""
        runtime_iterator = None
        try:
            if not self.consent or workspace.thread.thread_id != pending.thread_id:
                raise PermissionError("Turn no longer active.")
            control.checkpoint()
            previous = self.previous_turn(pending.thread_id)
            anchor = previous_from_messages(workspace.store.list_messages(workspace.owner_scope_id, pending.thread_id, limit=12)).assistant_message_id
            persisting = True
            self._record_turn(pending, TurnStatus.UNKNOWN, anchor)
            persisting = False
            provider = self.provider
            if provider is None:
                provider = self.provider_factory()
            with control.lock:
                control.checkpoint()
                generation.provider = provider
                if self.provider is None:
                    self.provider = provider
            runtime = OrangeRuntime(provider, planning_retries=0)
            controller = generation.view.controller
            runtime_iterator = runtime.run(generation.view, pending.text, consent=self.consent,
                proposal_permission=pending.allow_proposal, previous_turn=previous, cancellation=control)
            # Close suspended inner spans BEFORE restoring the outer binding.
            # Otherwise generator cancellation can resurrect an expired scope.
            with diagnostic_scope(controller.diagnostic_collector, controller.diagnostic_context), provider.cancellation_scope(control), closing(runtime_iterator):
                for event in runtime_iterator:
                    if not self.consent or workspace.thread.thread_id != pending.thread_id:
                        raise PermissionError("Turn cancelled.")
                    if isinstance(event, TurnCancelled):
                        with control.lock:
                            if self._owns(generation):
                                self.last_cancelled = event
                        cancelled = True
                        break
                    control.checkpoint()
                    if isinstance(event, Activity):
                        with control.lock:
                            control.checkpoint()
                            control.activities.append(event.model_dump())
                    elif isinstance(event, AnswerDelta):
                        control.project(event.text)
                    elif isinstance(event, TurnComplete):
                        metadata, metrics = completed_metadata(event)
                        details, accounting, attempts, usage = event.diagnostics, event.accounting, event.provider_attempts, event.usage
                        persisting = True
                        with control.lock:
                            control.checkpoint()
                            control.finalizing = True
                            try:
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
                                control.completed = True
                            finally:
                                control.finalizing = False
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
                        with control.lock:
                            control.checkpoint()
                            self.last_error = event.category
                        failure, usage = event.diagnostic, event.usage
                        details, accounting, attempts = event.diagnostics, event.accounting, event.provider_attempts
                        metrics = event.stream_metrics
                    yield event
        except GeneratorExit:
            cancelled = True
            raise
        except CancellationRequested:
            cancelled = True
        except Exception as exc:
            cancelled = isinstance(exc, PermissionError) or control.requested
            with self._lock:
                if self._owns(generation) and not control.requested:
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
            if runtime_iterator is not None:
                runtime_iterator.close()
            cancellation_event = None
            if control.requested and not finished and callable(getattr(control, "final_event", None)):
                cancellation_event = control.final_event()
            # Cleanup may have blocked for minutes. Re-prove this immutable lease
            # before touching ANY current session, receipt, conversation or UI.
            with self._lock:
                if self._owns(generation):
                    self.last_failure = failure
                    if control.requested and not finished:
                        if self.last_cancelled is None:
                            self.last_cancelled = cancellation_event
                        self.last_error = self.last_failure = None
                        self.last_result = None
                        self._persist_cancelled(generation, self.last_cancelled)
                    elif not finished:
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
                    self._executing = False
                    generation.running = False
                    if not control.background:
                        self._reload(pending)
                generation.running = False
                generation.done.set()

    def close(self):
        """Invalidate session authority; daemon cleanup is never joined here."""
        with self._lock:
            self.cancel_pending()
            self._closed = True
            self.last_result = None
            self.pending = None
            self._reap_cleanup()
