"""Ephemeral owner/thread/parent/source-bound Job Intelligence dialogue."""

from dataclasses import dataclass, field
from threading import RLock
from time import perf_counter
from uuid import uuid4
from career_discovery.context import fingerprint
from specific_role.models import Binding, FollowupToken, Status, Dimension
from specific_role.sources import SpecificRoleRegistry
from specific_role.service import SpecificRoleService, classify, reference_hint, reference_id, PERSONAL, UNSUPPORTED, AMBIGUOUS
from ui.conversation_store import _no_credentials


@dataclass(frozen=True)
class SpecificRoleMessage:
    anchor: int
    reality_offset: int
    landscape_offset: int
    role: str
    text: str = field(default="", repr=False)
    source: object = field(default=None, repr=False)
    reply: object = field(default=None, repr=False)


@dataclass(frozen=True)
class SpecificRoleEvent:
    operation: str
    status: Status
    request_id: str | None = None
    source_version: int = 0
    duration_ms: int = 0


class SpecificRoleSession:
    """No provider, personal role facts, Memory consumer or authority writes."""

    def __init__(self, workspace, *, registry=None, service=None):
        self.workspace = workspace
        self.registry = registry or SpecificRoleRegistry()
        self.service = service or SpecificRoleService()
        self._lock, self.generation = RLock(), 0
        self.invalidate()

    def invalidate(self):
        with self._lock:
            self.generation += 1
            self.binding = self.source = None
            self.status = Status.IDLE
            self.messages, self.events = [], []
            self.turns, self.busy = 0, False

    def _event(self, operation, duration=0):
        b = self.binding
        self.events.append(SpecificRoleEvent(operation, self.status, b.request_id if b else None,
                                            b.source_version if b else 0, duration))
        del self.events[:-40]

    def _message(self, text="", *, role="assistant", reply=None, source=None):
        w = self.workspace
        self.messages.append(SpecificRoleMessage(len(w.chat.messages), len(w.career_reality.messages),
            len(w.role_landscape.messages), role, text, source, reply))
        del self.messages[:-40]

    def _parents(self):
        w = self.workspace
        if w._closed or not w.role_landscape.current() or not w.career_reality.current():
            raise ValueError("MISSING_PARENT")
        w.store.get_thread(w.owner_scope_id, w.thread.thread_id)
        return w.career_reality, w.role_landscape

    def _current(self):
        try:
            w, b = self.workspace, self.binding
            if b is None or w._closed or (b.owner, b.thread) != (w.owner_scope_id, w.thread.thread_id):
                return False
            reality, landscape = self._parents()
            if (reality.binding.discovery_request_id, reality.binding.direction_id, reality.binding.request_id,
                reality.generation, fingerprint(reality.binding.model_dump()), landscape.binding.request_id,
                landscape.generation, fingerprint(landscape.binding.model_dump())) != (
                b.discovery_request_id, b.direction_id, b.reality_request_id, b.reality_generation,
                b.reality_fingerprint, b.landscape_request_id, b.landscape_generation, b.landscape_fingerprint):
                return False
            source = self.registry.resolve(landscape.source, b.direction_id, b.archetype_id)
            return (source.source_id, source.version, fingerprint(source.model_dump(mode="json")),
                    source.representative_role_id) == (
                    b.source_id, b.source_version, b.source_fingerprint, b.representative_role_id)
        except Exception:
            return False

    def current(self):
        with self._lock:
            if self.binding is not None and not self._current():
                self.invalidate()
                self.status = Status.STALE
                self._event("stale")
            return self.status == Status.ACTIVE

    def token(self):
        if not self.current():
            return None
        b = self.binding
        return FollowupToken(owner=b.owner, thread=b.thread, request_id=b.request_id,
            generation=self.generation, context_fingerprint=fingerprint((b.model_dump(), self.turns)))

    def _bind(self, archetype_id):
        reality, landscape = self._parents()
        w = self.workspace
        source = self.registry.resolve(landscape.source, reality.binding.direction_id, archetype_id)
        self.generation += 1
        self.source = source
        self.binding = Binding(owner=w.owner_scope_id, thread=w.thread.thread_id,
            request_id="specific_" + uuid4().hex, discovery_request_id=reality.binding.discovery_request_id,
            direction_id=reality.binding.direction_id, reality_request_id=reality.binding.request_id,
            reality_generation=reality.generation, reality_fingerprint=fingerprint(reality.binding.model_dump()),
            landscape_request_id=landscape.binding.request_id, landscape_generation=landscape.generation,
            landscape_fingerprint=fingerprint(landscape.binding.model_dump()), archetype_id=archetype_id,
            source_id=source.source_id, source_version=source.version,
            source_fingerprint=fingerprint(source.model_dump(mode="json")),
            representative_role_id=source.representative_role_id)
        if not self._current():
            raise ValueError("INVALID_PARENT")
        self.status = Status.ACTIVE

    def submit(self, text, *, token=None):
        with self._lock:
            if token is not None and token != self.token():
                return True  # Stale, replayed or foreign chip never reaches QA.
            intent = classify(text, active=self.binding is not None or self.status != Status.IDLE)
            if intent is None:
                return False
            if intent.kind in ("role", "personal") and intent.reference and not reference_hint(
                    intent.reference, self.workspace.role_landscape.source, self.source):
                return False
            try:
                _no_credentials(text)
            except ValueError:
                return True
            if self.busy or self.workspace.agent_session.busy or self.workspace.role_landscape.busy or self.workspace.career_reality.busy:
                return True
            was_bound = self.binding is not None
            active = self.current()
            if not active and (was_bound or self.status == Status.STALE):
                self._message(UNSUPPORTED)
                return True
            if self.turns >= 24:
                self.status = Status.LIMIT_REACHED
                self._message("本次代表性角色理解已达到有限问答边界，没有扩展资料或调用模型。")
                self._event("limit")
                return True
            if intent.kind in ("personal", "interest"):
                note = PERSONAL
                if intent.kind == "interest":
                    try:
                        _, parent = self._parents()
                        reference_id(intent.reference, parent.source, parent.binding.displayed_role_ids,
                                     self.binding.archetype_id if active else None,
                                     specific_source=self.source if active else None)
                    except Exception:
                        note = AMBIGUOUS
                    else:
                        note = "可以继续了解工作；兴趣仅留在这次聊天，不证明能力，也不确认职业目标或写入长期理解。"
                self.turns += 1
                self._message(text.strip(), role="user")
                self._message(note)
                self._event(intent.kind)
                return True
            try:
                _, parent = self._parents()
            except Exception:
                self.status = Status.UNSUPPORTED
                self._message(UNSUPPORTED)
                self._event("unsupported")
                return True
            try:
                last = self.binding.archetype_id if active else (
                    parent.last_role_ids[0] if len(parent.last_role_ids) == 1 else None)
                archetype_id = reference_id(intent.reference, parent.source, parent.binding.displayed_role_ids, last,
                                            specific_source=self.source if active else None)
            except ValueError:
                self._message(text.strip(), role="user")
                self._message(AMBIGUOUS)
                self.turns += 1
                self._event("ambiguous")
                return True
            try:
                if not active or self.binding.archetype_id != archetype_id:
                    self._bind(archetype_id)
            except Exception:
                self.invalidate()
                self.status = Status.UNSUPPORTED
                self._message(UNSUPPORTED)
                self._event("unsupported")
                return True
            generation, source, self.busy = self.generation, self.source, True
        try:
            started = perf_counter()
            reply = self.service.reply(source, intent.dimension)
            self.service.validate(reply, source)
            note = ""
            if intent.dimension == Dimension.OVERVIEW:
                note = "先看这份独立资料中的一种具体工作形态。接下来可以逐步问协作、交付或决策边界。"
            elif intent.dimension == Dimension.CAPABILITIES:
                note = "这些是示例工作涉及的能力，不表示你已经具备或缺少这些能力。"
            elif intent.dimension == Dimension.UNKNOWN:
                note = "来源未说明的内容保持未知，不补造招聘或个人能力结论。"
            with self._lock:
                if generation != self.generation or not self._current():
                    return True
                self.turns += 1
                self._message(text.strip(), role="user")
                self._message(note, reply=reply, source=source)
                self._event("reply", round((perf_counter() - started) * 1000))
        except Exception:
            with self._lock:
                if generation == self.generation:
                    self.invalidate()
                    self.status = Status.INVALID
                    self._message(UNSUPPORTED)
                    self._event("invalid")
        finally:
            with self._lock:
                if generation == self.generation:
                    self.busy = False
        return True
