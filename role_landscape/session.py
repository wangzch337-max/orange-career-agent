"""Owner/thread/D.2/source-bound ephemeral dialogue. No provider or write tools."""

from dataclasses import dataclass, field
from threading import RLock
from time import perf_counter
from uuid import uuid4
from career_discovery.context import fingerprint
from role_landscape.models import Binding, FollowupToken, Status, Dimension
from role_landscape.sources import RoleLandscapeRegistry
from role_landscape.service import RoleLandscapeService, classify, references, normalized
from ui.conversation_store import _no_credentials

UNSUPPORTED = "当前方向或角色资料不足、已变化，暂时不能解释这些角色。没有换成其他岗位，也没有调用模型补造。请先回到有效的方向探索。"
PERSONAL = "这里可以解释不同角色在做什么，但不能据此判断哪个更适合你。那需要另行明确授权的 Match 与个人证据核对；本次没有推荐、排序或确认职业目标。"
AMBIGUOUS = "这个角色引用还不能唯一对应当前展示的类型。可以用刚才的序号或完整角色名再问；我没有猜测或替换角色。"


@dataclass(frozen=True)
class LandscapeMessage:
    anchor: int
    reality_offset: int
    role: str
    text: str = field(default="", repr=False)
    reply: object = field(default=None, repr=False)


@dataclass(frozen=True)
class LandscapeEvent:
    operation: str
    status: Status
    request_id: str | None = None
    direction_id: str | None = None
    source_version: int = 0
    role_count: int = 0
    duration_ms: int = 0


class RoleLandscapeSession:
    def __init__(self, workspace, *, registry=None, service=None):
        self.workspace = workspace
        self.registry = registry or RoleLandscapeRegistry()
        self.service = service or RoleLandscapeService()
        self._lock, self.generation = RLock(), 0
        self.invalidate()

    def invalidate(self):
        with self._lock:
            self.generation += 1
            self.status = Status.IDLE
            self.binding = self.source = None
            self.messages, self.events = [], []
            self.turns, self.last_role_ids, self.busy = 0, (), False

    def _event(self, operation, duration=0):
        b = self.binding
        self.events.append(LandscapeEvent(operation, self.status, b.request_id if b else None,
            b.direction_id if b else None, b.source_version if b else 0,
            len(b.displayed_role_ids) if b else 0, duration))
        del self.events[:-40]

    def _message(self, text="", *, role="assistant", reply=None):
        w = self.workspace
        self.messages.append(LandscapeMessage(len(w.chat.messages), len(w.career_reality.messages), role, text, reply))
        del self.messages[:-40]

    def _current(self):
        try:
            w, b = self.workspace, self.binding
            parent = w.career_reality
            if b is None or w._closed or (w.owner_scope_id, w.thread.thread_id) != (b.owner, b.thread):
                return False
            w.store.get_thread(b.owner, b.thread)
            if not parent.current() or (parent.generation, parent.binding.request_id,
                    fingerprint(parent.binding.model_dump())) != (
                    b.parent_generation, b.parent_request_id, b.parent_fingerprint):
                return False
            identity = parent.binding.direction_identity
            source = self.registry.resolve(identity.family, identity.title, b.direction_id)
            return source is not None and (source.source_id, source.version,
                fingerprint(source.model_dump(mode="json")), tuple(r.role_id for r in source.roles)) == (
                    b.source_id, b.source_version, b.source_fingerprint, b.displayed_role_ids)
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
            generation=self.generation, context_fingerprint=fingerprint((b.model_dump(), self.turns, self.last_role_ids)))

    def _bind(self):
        """Bind existing valid parent receipt only; never fetch Profile/Memory facts."""
        w, parent = self.workspace, self.workspace.career_reality
        if not parent.current() or w._closed:
            raise ValueError("MISSING_PARENT")
        p = parent.binding
        source = self.registry.resolve(p.direction_identity.family, p.direction_identity.title, p.direction_id)
        if source is None:
            raise ValueError("MISSING_ROLE_SOURCE")
        self.source = source
        self.binding = Binding(owner=w.owner_scope_id, thread=w.thread.thread_id,
            request_id="landscape_" + uuid4().hex, direction_id=p.direction_id,
            parent_request_id=p.request_id, parent_generation=parent.generation,
            parent_fingerprint=fingerprint(p.model_dump()), source_id=source.source_id,
            source_version=source.version, source_fingerprint=fingerprint(source.model_dump(mode="json")),
            displayed_role_ids=tuple(r.role_id for r in source.roles))
        if not self._current():
            raise ValueError("INVALID_PARENT")
        self.status = Status.ACTIVE

    def _reference_hint(self, text):
        import re
        s = normalized(text)
        return (bool(re.search(r"第[一二三四五六七八九十1-9](?:种|个)", s)) or
            any(v in s for v in ("角色", "岗位", "这两种", "偏系统那个", "偏系统的那个")) or
            (self.source is not None and any(normalized(a) in s for r in self.source.roles
                                            for a in (r.display_name, *r.reference_aliases))))

    def submit(self, text, *, token=None):
        with self._lock:
            if token is not None and token != self.token():
                return True  # Reject stale/replayed chip without any QA fallback.
            intent = classify(text, active=True)
            if intent is None or (intent.kind == "followup" and not self._reference_hint(text)):
                return False
            if intent.kind in ("personal", "all", "more", "unsupported", "interest") and not (
                    self.binding is not None or self.status != Status.IDLE or self.messages):
                return False
            try:
                _no_credentials(text)
            except ValueError:
                return True
            if self.busy or self.workspace.agent_session.busy:
                return True
            was_bound = self.binding is not None
            if not self.current():
                if was_bound or self.status == Status.STALE:
                    self._message(UNSUPPORTED)
                    return True
                if intent.kind != "overview":
                    self._message(UNSUPPORTED)
                    return True
                try:
                    self._bind()
                except Exception:
                    self.invalidate()
                    self.status = Status.UNSUPPORTED
                    self._message(UNSUPPORTED)
                    self._event("unsupported")
                    return True
            if self.turns >= 16:
                self.status = Status.LIMIT_REACHED
                self._message("本次角色探索达到有限问答边界，没有扩展资料或调用模型。")
                self._event("limit")
                return True
            generation, source, self.busy = self.generation, self.source, True
        try:
            started = perf_counter()
            note, reply = "", None
            named_directions = ("businessanalysis", "knowledgeoperations", "processimprovement")
            s = normalized(text)
            if any(v in s and v != normalized(source.direction_identity.title) for v in named_directions):
                note = UNSUPPORTED
            elif intent.kind == "unsupported_direction":
                note = UNSUPPORTED
            elif intent.kind == "personal":
                note = PERSONAL
            elif intent.kind == "more":
                note = "这份合成资料已展示全部已批准的代表性分工，没有更多已批准类型；不代表真实世界只有这些角色。"
            elif intent.kind == "unsupported":
                note = "资料未说明具体招聘职位、薪资或投递要求，这些仍未知。本次没有进入具体职位筛选。"
            elif intent.kind == "interest":
                try:
                    references(text, source, self.binding.displayed_role_ids, self.last_role_ids)
                    note = "可以继续了解这类工作。这里的兴趣只留在本次聊天，不写入长期理解、Memory 或职业目标。"
                except ValueError:
                    note = AMBIGUOUS
            else:
                try:
                    ids = self.binding.displayed_role_ids if intent.kind in ("overview", "all") else references(
                        text, source, self.binding.displayed_role_ids, self.last_role_ids)
                    if intent.dimension == Dimension.COMPARISON and len(ids) < 2:
                        raise ValueError("AMBIGUOUS_COMPARISON")
                except ValueError:
                    note = AMBIGUOUS
                else:
                    reply = self.service.reply(source, intent.dimension, ids)
                    self.service.validate(reply, source)
                    if intent.kind == "overview":
                        note = "如果先不急着看具体公司职位，可以先把这份资料中的几种不同角色看清楚。你想先看看哪一种平时具体在做什么？"
                    elif intent.kind == "all":
                        note = "先并列看各类分工的来源说明；没有按沟通频率或技术高低排序，资料也不提供定量比较。"
            with self._lock:
                if generation != self.generation or not self._current():
                    return True
                self.turns += 1
                self._message(text.strip(), role="user")
                self._message(note, reply=reply)
                if reply:
                    self.last_role_ids = () if reply.dimension == Dimension.OVERVIEW else reply.role_ids
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
