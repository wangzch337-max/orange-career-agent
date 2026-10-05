"""One turn's local cancellation and atomic-completion arbitration, not routing."""

from dataclasses import dataclass
from threading import RLock, Thread
from time import perf_counter


@dataclass(frozen=True)
class GenerationIdentity:
    """Immutable local write lease; never provider-controlled or prompt content."""
    generation_id: str
    owner_scope_id: str
    thread_id: str
    turn_id: str


class CancellationRequested(Exception):
    """Content-free cooperative exit; never a transport-failure diagnosis."""


class TurnControl:
    def __init__(self, *, background=False, identity=None, lock=None, owns=None):
        self.lock = lock or RLock()
        self.identity = identity
        self._owns = owns
        self.background = background
        self.requested = False
        self.completed = False
        self.finalizing = False
        self.text = ""
        self.displayed = ""
        self.partial = ""
        self.activities = []
        self.close_attempted = False
        self.close_failed = False
        self.response_started = False
        self._closers = []
        self._close_workers = []
        self._close_keys = set()
        self.registry = None
        self.provider_attempts = []
        self.provider_metrics = [None]
        self.lifecycle = []
        self.cancel_started = None
        self.ui_release_latency_ms = None

    def note(self, event):
        # Closed structural events only, no text, source data or exception values.
        allowed = {"cancel_requested", "cancel_committed", "ui_released", "cleanup_started", "cleanup_finished"}
        if event not in allowed:
            raise ValueError("Unknown cancellation lifecycle event.")
        with self.lock:
            if event not in self.lifecycle:
                self.lifecycle.append(event)

    @property
    def cleanup_idle(self):
        return not any(worker.is_alive() for worker in self._close_workers)

    def checkpoint(self):
        with self.lock:
            if self.requested or (self._owns is not None and not self._owns()):
                raise CancellationRequested()

    def project(self, text):
        with self.lock:
            self.checkpoint()
            self.text += text

    def snapshot(self):
        with self.lock:
            if not self.requested:
                self.displayed = self.text
            return self.partial if self.requested else self.displayed, tuple(self.activities), self.requested

    def request(self):
        """Accept only before the completed commit; close IO off the UI thread."""
        with self.lock:
            if self.completed or self.finalizing or self.requested:
                return False
            self.requested = True
            self.cancel_started = perf_counter()
            self.note("cancel_requested")
            self.partial = self.displayed if self.background else self.text
            if self.registry is not None:
                self.registry.discard_pending()
            closers = tuple(self._closers)
        for close in closers:
            self._close_async(close)
        return True

    def _close_async(self, close):
        # A request has at most the owned client and its response stream. Do not
        # spawn one forgotten thread per Stop/rerender/duplicate attachment.
        with self.lock:
            key = (id(getattr(close, "__self__", close)), getattr(close, "__name__", "close"))
            if key in self._close_keys:
                return
            if len(self._close_keys) >= 2:
                self.close_failed = True
                return
            self._close_keys.add(key)
            self.close_attempted = True
            self.note("cleanup_started")
        def cleanup():
            try:
                close()
            except Exception:
                self.close_failed = True  # Never retain untrusted exception text.
        worker = Thread(target=cleanup, name="orange-stream-close", daemon=True)
        with self.lock:
            self._close_workers.append(worker)
            worker.start()

    def attach_close(self, close):
        """Bind the SDK response/client close, never close an executing generator."""
        if not callable(close):
            return lambda: None
        with self.lock:
            requested = self.requested
            if not requested:
                self._closers.append(close)
        if requested:
            self._close_async(close)
        def detach():
            with self.lock:
                if close in self._closers:
                    self._closers.remove(close)
        return detach
