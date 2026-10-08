"""Owner/profile/D.4-bound ephemeral comparison. No durable write APIs."""

from dataclasses import dataclass, field
import re
from threading import RLock
from time import perf_counter
from uuid import uuid4
from career_discovery.context import fingerprint
from role_landscape.service import normalized
from agents.match_insight import MatchInsightAgent
from providers.fake import FakeLLMProvider
from evidence_match.models import Binding, Token, Event, Relation, Context
from evidence_match.projection import project_user, project_work
from evidence_match.service import proposed
from ui.conversation_store import _no_credentials

UNAVAILABLE = "需要当前合法的代表性角色和已确认画像，才能说明证据关系。补充经历请继续走既有画像审核确认；本轮没有写入画像或记忆，也没有换用旧岗位。"
NOTICE = "这是当前已确认材料与公开合成工作项的证据关系，不是职业适配裁决；最终决定属于你。"
LABELS = {Relation.DIRECT:"已有较直接证据", Relation.PARTIAL:"相关但有限", Relation.UNKNOWN:"当前未知",
          Relation.TENSION:"有证据的当前张力", Relation.NA:"明确不在本次比较范围"}


def intent(text, active=False):
    if not isinstance(text, str) or not 0 < len(text.strip()) <= 2000:
        return None
    s = normalized(text)
    if re.fullmatch(r"(?:那)?(?:你觉得)?(?:这个角色|这种角色|这项工作|这个工作)(?:与我有什么关系|适合我(?:吗)?)|我(?:有什么|目前有哪些)(?:经历|证据)和(?:这个工作|这个角色|这项工作)相关|我和(?:这个角色|这种工作)有什么匹配的地方|我(?:目前)?还缺什么", s):
        return "start"
    if active and re.fullmatch(r"为什么(?:你说)?(?:这个|这里)(?:算相关|还是unknown|是unknown|仍未知|是未知)|这里具体用了我的哪段经历|(?:展开|解释)(?:第[1-9一二三四五六七八九]条)(?:关系)?", s, re.I):
        return "detail"
    if active and re.fullmatch(r"我(?:做过|完成过|参与过|还做过).+", s):
        return "new_evidence"
    return None


@dataclass(frozen=True)
class Message:
    anchor: int
    reality_offset: int
    landscape_offset: int
    specific_offset: int
    role: str
    text: str = field(repr=False)
    context: object = field(default=None, repr=False)
    relationships: tuple = field(default=(), repr=False)
    detailed: bool = False


class EvidenceMatchSession:
    def __init__(self, workspace):
        self.workspace, self._lock, self.generation = workspace, RLock(), 0
        self.agent_factory = lambda context: MatchInsightAgent(FakeLLMProvider(proposed(context)))
        self.invalidate()

    def invalidate(self):
        with self._lock:
            self.generation += 1
            self.binding = self.result = self.context = None
            self.messages, self.events, self.displayed = [], [], ()
            self.turns, self.busy, self.status = 0, False, "unavailable"

    def _inputs(self):
        w = self.workspace
        if w._closed or not w.specific_role.current():
            raise ValueError("D5_PARENT_UNAVAILABLE")
        w.store.get_thread(w.owner_scope_id, w.thread.thread_id)
        profile = w.memory_service.get_current_confirmed_profile(w.subject_id)
        if profile is None:
            raise ValueError("D5_PROFILE_UNAVAILABLE")
        return profile, w.specific_role.source

    def _current(self):
        b, w = self.binding, self.workspace
        if b is None or w._closed:
            return False
        try:
            if (b.owner, b.subject, b.thread, b.generation) != (w.owner_scope_id, w.subject_id, w.thread.thread_id, self.generation):
                return False
            profile, source = self._inputs()
            return ((profile.profile_id, profile.version, fingerprint(profile.model_dump(mode="json")),
                     source.representative_role_id, source.source_id, source.version,
                     fingerprint(source.model_dump(mode="json")), "d5.work@v1",
                     w.specific_role.generation, fingerprint(w.specific_role.binding.model_dump())) ==
                    (b.profile_id, b.profile_version, b.profile_fingerprint, b.role_id, b.source_id, b.source_version,
                     b.source_fingerprint, b.projection_version, b.parent_generation, b.parent_fingerprint))
        except Exception:
            return False

    def current(self):
        with self._lock:
            if self.binding and not self._current():
                self.invalidate()
                self.status = "stale"
            return self.status == "active" and self.binding is not None

    def token(self):
        if not self.current(): return None
        b = self.binding
        return Token(owner=b.owner, subject=b.subject, thread=b.thread, request_id=b.request_id,
                     generation=self.generation, turn=self.turns)

    def _message(self, text, *, role="assistant", relationships=(), detailed=False):
        w = self.workspace
        self.messages.append(Message(len(w.chat.messages), len(w.career_reality.messages),
            len(w.role_landscape.messages), len(w.specific_role.messages), role, text,
            self.context if relationships else None, relationships, detailed))
        del self.messages[:-40]

    def _event(self, duration=0):
        b = self.binding
        counts = {r: sum(i.relation_type == r for i in self.result.relationships) for r in Relation} if self.result else {}
        self.events.append(Event(request_id=b.request_id if b else None, profile_version=b.profile_version if b else 0,
            role_id=b.role_id if b else None, projection_version="d5.work@v1", relation_counts=counts,
            status=self.status, duration_ms=duration))
        del self.events[:-40]

    def submit(self, text, *, token=None):
        with self._lock:
            if token is not None and token != self.token(): return True
            kind = intent(text, active=self.binding is not None)
            if kind is None: return False
            try: _no_credentials(text)
            except ValueError: return True
            w = self.workspace
            if self.busy or w.agent_session.busy: return True
            active = self.current()
            if self.turns >= 24:
                self.status = "limited"; self._message("本轮证据关系问答已达到有限边界，请重新明确开始。")
                self._event(); return True
            if kind == "new_evidence":
                self.turns += 1
                self._message(text.strip(), role="user")
                self._message("补充经历需要继续走既有画像审核确认。这条会话表述没有成为能力事实，本轮证据关系没有改变。")
                return True
            if kind == "detail":
                if not active:
                    self._message(UNAVAILABLE); return True
                s = normalized(text)
                index = re.search(r"第([1-9一二三四五六七八九])条", s)
                if index:
                    char = index[1]; number = int(char) if char.isdigit() else "一二三四五六七八九".index(char)+1
                    selected = self.displayed[number-1:number]
                elif "unknown" in s.lower() or "未知" in s:
                    selected = tuple(r for r in self.displayed if r.relation_type == Relation.UNKNOWN)[:1]
                else:
                    selected = tuple(r for r in self.displayed if r.relation_type in (Relation.DIRECT, Relation.PARTIAL))[:1]
                self.turns += 1
                self._message(text.strip(), role="user")
                self._message("展开本轮已验证关系的双侧来源与限制。" if selected else "这里没有可唯一展开的对应关系，请明确当前关系序号。",
                              relationships=selected, detailed=True)
                return True
            try:
                profile, source = self._inputs()
                context = Context(user=project_user(profile), work=project_work(source))
                if not context.user.signals: raise ValueError("D5_NO_ADMITTED_SIGNALS")
            except Exception:
                self.invalidate(); self.status = "unavailable"
                self._message(UNAVAILABLE); self._event(); return True
            self.generation += 1
            self.binding = Binding(owner=w.owner_scope_id, subject=w.subject_id, thread=w.thread.thread_id,
                request_id="relationship_" + uuid4().hex, generation=self.generation,
                profile_id=context.user.profile_id, profile_version=context.user.profile_version,
                profile_fingerprint=context.user.profile_fingerprint, role_id=context.work.role_id,
                source_id=context.work.source_id, source_version=context.work.source_version,
                source_fingerprint=context.work.source_fingerprint, projection_version=context.work.projection_version,
                parent_generation=w.specific_role.generation, parent_fingerprint=fingerprint(w.specific_role.binding.model_dump()))
            generation, self.busy = self.generation, True
        try:
            started = perf_counter()
            result, checked_context = self.agent_factory(context).analyze_role_relationships(profile, source)
            with self._lock:
                if generation != self.generation or not self._current(): return True
                self.context, self.result, self.status = checked_context, result, "active"
                chosen = []
                for r in (Relation.DIRECT, Relation.PARTIAL, Relation.UNKNOWN, Relation.TENSION, Relation.NA):
                    item = next((i for i in result.relationships if i.relation_type == r), None)
                    if item: chosen.append(item)
                self.displayed = tuple(chosen)
                self.turns += 1
                self._message(text.strip(), role="user")
                self._message(NOTICE, relationships=self.displayed)
                self._event(round((perf_counter()-started)*1000))
        except Exception:
            with self._lock:
                if generation == self.generation:
                    self.invalidate(); self.status = "invalid"
                    self._message(UNAVAILABLE); self._event()
        finally:
            with self._lock:
                if generation == self.generation: self.busy = False
        return True
