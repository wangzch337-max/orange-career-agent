"""Independent, ephemeral D.2 selection receipt; never retrieves/writes Memory."""

from dataclasses import dataclass, field
from threading import RLock
from time import perf_counter
from uuid import uuid4

from career_discovery.context import fingerprint
from career_discovery.models import CareerDiscoveryResult, Status as DiscoveryStatus
from career_reality.models import Binding, Dimension, DirectionIdentity, FollowupToken, Status
from career_reality.service import CareerRealityService, explicitly_scoped, followup_dimension
from career_reality.sources import CareerRealitySourceRegistry
from ui.conversation_store import _no_credentials

UNSUPPORTED = "这个方向我现在还没有足够可靠的工作资料，不想为了继续聊而补一个看似合理的版本。我们可以先保留这个问题；没有换成其他方向。"
UNKNOWN = "这份公开合成资料还不能回答这个问题。我先把它保留为未知，不据此判断你适不适合，也不补造岗位要求。你可以继续问工作内容、协作或产出。"


@dataclass(frozen=True)
class RealityMessage:
    anchor: int
    role: str
    text: str = field(default="", repr=False)
    reply: object = field(default=None, repr=False)


@dataclass(frozen=True)
class RealityEvent:
    operation: str
    status: Status
    request_id: str | None = None
    direction_id: str | None = None
    source_count: int = 0
    situation_count: int = 0
    duration_ms: int = 0


class CareerRealitySession:
    """Deterministic work projection. No provider, personal content or write tools."""

    def __init__(self, workspace, *, registry=None, service=None):
        self.workspace = workspace
        self.registry = registry or CareerRealitySourceRegistry()
        self.service = service or CareerRealityService()
        self._lock, self.generation = RLock(), 0
        self._used = set()
        self.invalidate()

    def invalidate(self):
        with self._lock:
            self.generation += 1
            self.status = Status.IDLE
            self.binding = self.source = None
            self.messages, self.events = [], []
            self.turns = self.situation_index = 0
            self.busy = False

    def _event(self, operation, duration_ms=0):
        self.events.append(RealityEvent(operation, self.status,
            self.binding.request_id if self.binding else None,
            self.binding.direction_id if self.binding else None,
            int(self.source is not None), len(self.source.situations) if self.source else 0, duration_ms))
        del self.events[:-40]

    def _profile(self):
        # Only a version/fingerprint check. No fields enter the explanation.
        w = self.workspace
        return w.memory_service.get_current_confirmed_profile(w.subject_id)

    def _current(self):
        w, b = self.workspace, self.binding
        try:
            if b is None or w._closed or w.owner_scope_id != b.owner or w.thread.thread_id != b.thread:
                return False
            w.store.get_thread(b.owner, b.thread)
            profile = self._profile()
            if profile is None or not profile.confirmed or (
                profile.profile_id, profile.version, fingerprint(profile.model_dump(mode="json"))) != (
                    b.profile_id, b.profile_version, b.profile_fingerprint):
                return False
            source = self.registry.resolve(b.direction_identity.family, b.direction_identity.title, b.direction_id)
            if source is None or (source.source_id, source.version, fingerprint(source.model_dump(mode="json"))) != (
                b.source_id, b.source_version, b.source_fingerprint):
                return False
            discovery = w.career_discovery
            if discovery.status == DiscoveryStatus.STALE:
                return False
            if discovery.result is not None and (discovery.result.request_id != b.discovery_request_id or
                    discovery.selected_direction_id != b.direction_id):
                return False
            # Normal QA clears D.1 review, not this separately validated receipt.
            return True
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
        return FollowupToken(owner=self.binding.owner, thread=self.binding.thread,
            request_id=self.binding.request_id, generation=self.generation,
            context_fingerprint=fingerprint((self.binding.model_dump(), self.turns, self.situation_index)))

    def _message(self, text="", *, role="assistant", reply=None):
        self.messages.append(RealityMessage(len(self.workspace.chat.messages), role, text, reply))
        del self.messages[:-40]

    def start(self, selection_token, selected_id):
        """Called only AFTER D.1.select succeeds; do not reread D.1 Memory here."""
        with self._lock:
            if self.busy or self.workspace.agent_session.busy:
                return False
            discovery = self.workspace.career_discovery
            key = (getattr(selection_token, "request_id", None), selected_id)
            if key in self._used:
                return self.current() and self.binding.direction_id == selected_id
            self.invalidate()
            try:
                w = self.workspace
                result = CareerDiscoveryResult.model_validate(discovery.result.model_dump())
                old = discovery.binding
                if (selection_token is None or old is None or discovery.status != DiscoveryStatus.SELECTED or
                    discovery.selected_direction_id != selected_id or
                    (selection_token.owner_scope_id, selection_token.conversation_id, selection_token.request_id,
                     selection_token.result_fingerprint) !=
                    (w.owner_scope_id, w.thread.thread_id, result.request_id, fingerprint(result.model_dump(mode="json"))) or
                    (old.owner_scope_id, old.conversation_id) != (w.owner_scope_id, w.thread.thread_id) or
                    old.statement_fingerprint != fingerprint(discovery._statement) or
                    old.recent_fingerprint != fingerprint(tuple((m.role, m.content) for m in w.chat.messages[-4:]))):
                    raise ValueError("INVALID_SELECTION")
                if len(self._used) >= 64:
                    self.status = Status.LIMIT_REACHED
                    return False
                self._used.add(key)
                candidate = next(d for d in result.directions if d.direction_id == selected_id)
                source = self.registry.resolve(candidate.direction_family, candidate.title, selected_id)
                if source is None:
                    self.status = Status.UNSUPPORTED
                    self._message(UNSUPPORTED)
                    self._event("unsupported")
                    return False
                self.source = source
                self.binding = Binding(owner=w.owner_scope_id, thread=w.thread.thread_id,
                    request_id="reality_" + uuid4().hex, discovery_request_id=result.request_id,
                    direction_id=selected_id, direction_identity=DirectionIdentity(family=candidate.direction_family, title=candidate.title),
                    profile_id=old.profile_id, profile_version=old.profile_version, profile_fingerprint=old.profile_fingerprint,
                    source_id=source.source_id, source_version=source.version,
                    source_fingerprint=fingerprint(source.model_dump(mode="json")))
                if not self._current():
                    raise ValueError("STALE_SELECTION")
                generation, self.busy = self.generation, True
            except Exception:
                self.invalidate()
                self.status = Status.INVALID
                self._message("这次选择对应的信息已经变化，暂时不能继续。没有替换方向或修改长期理解。")
                self._event("invalid")
                return False
        try:
            started = perf_counter()
            reply = self.service.reply(source, Dimension.SITUATION, opening=True)
            self.service.validate(reply, source)
            with self._lock:
                if generation != self.generation or not self._current():
                    return False
                self.status = Status.ACTIVE
                self._message("这个名字听起来有点抽象，我们把它拆成工作看看。先不急着判断适不适合你，先看看这种工作在解决什么问题。", reply=reply)
                self._event("opened", round((perf_counter() - started) * 1000))
                return True
        except Exception:
            with self._lock:
                if generation == self.generation:
                    self.invalidate()
                    self.status = Status.INVALID
                    self._message(UNSUPPORTED)
                    self._event("invalid")
            return False
        finally:
            with self._lock:
                if generation == self.generation:
                    self.busy = False

    def submit(self, text, *, token=None):
        with self._lock:
            if not isinstance(text, str) or not 0 < len(text.strip()) <= 2000:
                return self.binding is not None
            if token is not None and token != self.token():
                return True  # Old chips must not fall through to QA/provider.
            if self.status == Status.LIMIT_REACHED:
                return followup_dimension(text) is not None or explicitly_scoped(text)
            if not self.current():
                return False
            if self.busy or self.workspace.agent_session.busy:
                return True
            dimension = followup_dimension(text)
            if dimension is None and not explicitly_scoped(text):
                return False
            if self.turns >= 16:
                self.status = Status.LIMIT_REACHED
                self._event("limit")
                self._message("我们先停在这份有限的工作理解上；本次没有自动扩展资料或调用模型。")
                return True
            try:
                if not isinstance(text, str) or not 0 < len(text.strip()) <= 2000:
                    return True
                _no_credentials(text)
            except ValueError:
                return True
            generation, source, self.busy = self.generation, self.source, True
            next_index = self.situation_index + int(dimension == Dimension.SITUATION)
        try:
            started = perf_counter()
            note, reply = "", None
            if dimension is None:
                note = UNKNOWN
            elif next_index >= len(source.situations):
                note = "这份资料里暂时没有更多已批准的情境。我不补造例子；我们仍可以继续了解当前情境的任务、协作或产出。"
            else:
                reply = self.service.reply(source, dimension, next_index)
                self.service.validate(reply, source)
                if dimension == Dimension.CAPABILITIES:
                    note = "这里说的是示例工作涉及的能力，不是在判断你已经具备或缺少这些能力。技术深度也不能只凭方向名称确定。"
                elif dimension == Dimension.VARIATIONS:
                    note = "同一个方向可能有不同工作形态。先看这份资料支持的差异，不把它们变成要投递的岗位清单。"
            with self._lock:
                if generation != self.generation or not self._current():
                    return True
                self.turns += 1
                self._message(text.strip(), role="user")
                self._message(note, reply=reply)
                if reply:
                    self.situation_index = next_index
                self._event("followup", round((perf_counter() - started) * 1000))
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
