"""Single-request, ephemeral scope; never writes canonical Profile or Memory."""

from dataclasses import dataclass
from threading import RLock
from uuid import uuid4

from providers.errors import LLMStructuredOutputError
from providers.fake import FakeLLMProvider
from career_discovery.context import CareerDiscoveryContextBuilder, bind, fingerprint, readiness
from career_discovery.models import (CareerDiscoveryResult, DiscoveryError, Readiness, SelectionToken, Status)
from career_discovery.service import CareerDiscoveryService
from career_discovery.dialogue import DialogueAct, PendingClarificationToken, scope_dialogue_act


@dataclass(frozen=True)
class DiscoveryEvent:
    event: str
    status: Status
    request_id: str | None = None
    profile_version: int | None = None
    source_count: int = 0
    memory_count: int = 0
    direction_count: int = 0
    uncertainty_count: int = 0
    evidence_gap_count: int = 0
    latency_ms: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    selected_direction_id: str | None = None


class CareerDiscoverySession:
    """D.1 is offline by default; injection uses the existing LLMProvider interface."""

    def __init__(self, owner_scope_id, input_factory, memory_service, *, provider_factory=None):
        self.owner_scope_id, self.input_factory, self.memory_service = owner_scope_id, input_factory, memory_service
        self.provider_factory = provider_factory or (lambda: FakeLLMProvider(None))
        self.builder, self.service = CareerDiscoveryContextBuilder(), CareerDiscoveryService()
        self._lock, self._generation, self._busy = RLock(), 0, False
        self.events = []
        self.result = self.context = self.binding = self.usage = self.selected_direction_id = None
        self.status, self._statement = Status.IDLE, ""
        self._request_id = None
        self._used_request_ids = set()
        self._qa_bridge = None

    @property
    def busy(self):
        return self._busy

    def _event(self, name, **values):
        self.events.append(DiscoveryEvent(name, self.status,
            request_id=self._request_id,
            profile_version=self.binding.profile_version if self.binding else None, **values))
        del self.events[:-40]

    def invalidate(self):
        with self._lock:
            self._generation += 1
            self.result = self.context = self.binding = self.usage = self.selected_direction_id = None
            self.status, self._statement = Status.IDLE, ""
            self._request_id = None
            self.events.clear()
            self._qa_bridge = None

    def pending_token(self):
        """A question owns replies only while its original authority is valid."""
        with self._lock:
            if self._busy or self.status != Status.NEEDS_CLARIFICATION:
                return None  # Ordinary QA never loads a completed discovery context.
            result = self.current_result()
            if (self._busy or not result or self.binding is None or
                    self.status != Status.NEEDS_CLARIFICATION or
                    result.readiness != Readiness.NEEDS_CLARIFICATION or result.clarification_need is None or
                    result.clarification_need.need_id != "exploration_scope"):
                return None
            return PendingClarificationToken(self.owner_scope_id, self.binding.conversation_id,
                result.request_id, self._generation, fingerprint(self.binding.model_dump()),
                result.clarification_need.need_id)

    def on_general_qa(self):
        """Pause only a valid pending scope turn; completed reviews still clear."""
        with self._lock:
            token = self.pending_token()
            if token is None:
                self.invalidate()
                return False
            self._qa_bridge = token
            return True

    def qa_pending_is_current(self):
        with self._lock:
            return self._qa_bridge is not None and self._qa_bridge == self.pending_token()

    def finish_general_qa(self):
        """Same-thread QA may change recent text, never Profile/Memory authority."""
        with self._lock:
            old, token = self.binding, self._qa_bridge
            self._qa_bridge = None
            if old is None or token is None or token.generation != self._generation:
                self.invalidate()
                return False
            try:
                inputs = self._inputs()
                updated = old.model_copy(update={"recent_fingerprint": fingerprint(inputs.recent)})
                if (fingerprint(old.model_dump()) != token.binding_fingerprint or
                        not self._current(updated)):
                    raise DiscoveryError(Status.STALE)
                self.binding = updated
                return True
            except Exception:
                self.invalidate()
                self.status = Status.STALE
                return False

    def answer_pending(self, text, *, token=None):
        """Consume an answer ephemerally and resume this one request, no retrieval."""
        with self._lock:
            current = self.pending_token()
            if token is not None and token != current:
                return True  # Stale answers must never become durable QA messages.
            if current is None or scope_dialogue_act(text) != DialogueAct.ANSWER:
                return False
            try:
                from career_discovery.context import clean, MAX_JSON_CHARS
                from career_discovery.models import Source
                from clarification.context import explicitly_uncertain
                import json
                clean_text, changed = clean(text)
                if changed or clean_text != text.strip():
                    raise DiscoveryError(Status.INVALID_CONTEXT)
                inputs = self._inputs()
                statement = "\n".join(filter(None, (self._statement, clean_text)))
                if len(statement) > 1200:
                    raise DiscoveryError(Status.INVALID_CONTEXT)
                prefix = fingerprint((current.owner, current.thread, current.request_id))[:16]
                answer = Source(ref=f"src_{prefix}_{len(self.context.sources):03d}",
                    origin="current_explicit", category="reply_to_adjacent_or_cross_industry_scope_question",
                    text=clean_text, uncertainty="explicit_uncertainty" if explicitly_uncertain(clean_text) else "none")
                context = type(self.context).model_validate({**self.context.model_dump(),
                    "sources": [*self.context.sources, answer]})
                if len(json.dumps(context.provider_payload(), ensure_ascii=False, separators=(",", ":"))) > MAX_JSON_CHARS:
                    raise DiscoveryError(Status.INVALID_CONTEXT)
                from dataclasses import replace
                binding = bind(replace(inputs, current_statement=statement), current.request_id,
                               self.binding.memory_fingerprints)
                self._statement, self.context, self.binding = statement, context, binding
                self.result = CareerDiscoveryResult.model_validate({**self.result.model_dump(),
                    "readiness": Readiness.READY, "clarification_need": None, "status": Status.READY,
                    "source_summary": [(origin, sum(s.origin == origin for s in context.sources)) for origin in
                        ("confirmed_profile", "confirmed_memory", "current_explicit", "recent_user_context")]})
                self.status, self._busy = Status.READY, True
                self._qa_bridge = None
                generation = self._generation
                self._event("career_discovery_clarification_answered")
            except Exception:
                self.status = Status.INVALID_CONTEXT
                self.result = None
                self._event("career_discovery_answer_rejected")
                return True
        self._discover(context, binding, generation)
        return True

    def _inputs(self, include_memory=False):
        value = self.input_factory(current_statement=self._statement, include_memory=include_memory)
        if value.owner_scope_id != self.owner_scope_id:
            raise DiscoveryError(Status.INVALID_REFERENCE)
        return value

    def _memory_fingerprints(self, context, inputs):
        entries = []
        for source in context.sources:
            if source.origin != "confirmed_memory":
                continue
            if len(source.origin_refs) != 1:
                raise DiscoveryError(Status.INVALID_REFERENCE)
            record = self.memory_service.memory_store.get(inputs.subject_id, source.origin_refs[0])
            if (record is None or record.subject_id != inputs.subject_id or record.status.value != "confirmed" or
                record.memory_type.value not in {"career_preference", "goal", "user_feedback"}):
                raise DiscoveryError(Status.INVALID_REFERENCE)
            from career_discovery.context import clean
            if clean(record.content)[0] != source.text:
                raise DiscoveryError(Status.INVALID_REFERENCE)
            entries.append((record.memory_id, fingerprint(record.model_dump(mode="json"))))
        return tuple(sorted(entries))

    def _current(self, binding):
        try:
            inputs = self._inputs()
            if bind(inputs, binding.request_id, binding.memory_fingerprints) != binding:
                return False
            for memory_id, expected in binding.memory_fingerprints:
                record = self.memory_service.memory_store.get(inputs.subject_id, memory_id)
                if (record is None or record.status.value != "confirmed" or
                    fingerprint(record.model_dump(mode="json")) != expected):
                    return False
            return True
        except Exception:
            return False

    def start(self, *, explicitly_requested=False, consent=False, current_statement="", request_id=None,
              expected_owner_scope_id=None, expected_conversation_id=None):
        with self._lock:
            if not explicitly_requested:
                self.invalidate()
                self.status = Status.NOT_REQUESTED
                self.result = CareerDiscoveryResult(request_id="not_requested", readiness=Readiness.NOT_REQUESTED, status=self.status)
                self._event("career_discovery_not_requested")
                return self.result
            if self._busy:
                return None
            request_id = request_id or "discovery_" + uuid4().hex
            # Caller idempotency keys never become logged request IDs/prose.
            request_id = "discovery_" + fingerprint((self.owner_scope_id, request_id))[:32]
            if request_id in self._used_request_ids:
                result = self.current_result()
                return result if result and result.request_id == request_id else None
            if not consent:
                self.status = Status.CONSENT_REQUIRED
                return None
            if len(self._used_request_ids) >= 64:
                self.status = Status.INVALID_CONTEXT
                return None  # Bounded tombstones; never evict and replay old requests.
            self._used_request_ids.add(request_id)
            self.invalidate()
            self._request_id = request_id
            self._statement = current_statement
            self._event("career_discovery_requested")
            try:
                inputs = self._inputs(include_memory=True)
                if ((expected_owner_scope_id is not None and inputs.owner_scope_id != expected_owner_scope_id) or
                    (expected_conversation_id is not None and inputs.conversation_id != expected_conversation_id)):
                    raise DiscoveryError(Status.STALE)
                if inputs.profile is None:
                    self.status = Status.NEEDS_CLARIFICATION
                    from career_discovery.models import ClarificationNeed
                    self.result = CareerDiscoveryResult(request_id=request_id, readiness=Readiness.NEEDS_CLARIFICATION,
                        clarification_need=ClarificationNeed(need_id="background", question="这次探索可以从哪段已确认的工作、学习或实践经历开始？",
                            reason="insufficient_relevant_background"), status=self.status)
                    self._event("career_discovery_needs_clarification")
                    return self.result
                context = self.builder.build(inputs, request_id)
                binding = bind(inputs, request_id, self._memory_fingerprints(context, inputs))
                self.context, self.binding = context, binding
                source_summary = tuple((origin, sum(s.origin == origin for s in context.sources)) for origin in
                    ("confirmed_profile", "confirmed_memory", "current_explicit", "recent_user_context"))
                self._event("career_discovery_context_built", source_count=len(context.sources), memory_count=dict(source_summary)["confirmed_memory"])
                state, need = readiness(context)
                self.status = Status(state.value)
                self.result = CareerDiscoveryResult(request_id=request_id, readiness=state, clarification_need=need,
                    partial=context.partial, source_summary=source_summary, status=self.status)
                if state != Readiness.READY:
                    self._event("career_discovery_needs_clarification")
                    return self.result
                self._event("career_discovery_ready")
                generation, self._busy = self._generation, True
            except Exception as error:
                self.status = error.code if isinstance(error, DiscoveryError) else Status.INVALID_CONTEXT
                self._event("career_discovery_failed")
                return None
        return self._discover(context, binding, generation)

    def _discover(self, context, binding, generation):
        """Existing single bounded discovery call, shared by start and resume."""
        try:
            if not self._current(binding):
                raise DiscoveryError(Status.STALE)
            provider = self.provider_factory()
            if not self._current(binding):
                raise DiscoveryError(Status.STALE)
            directions, usage = self.service.discover(provider, context)
            with self._lock:
                if generation != self._generation:
                    return None
                if not self._current(binding):
                    raise DiscoveryError(Status.STALE)
                self.status, self.usage = Status.CREATED, usage
                self.result = self.result.model_copy(update={"directions": directions, "status": self.status})
                self._event("career_discovery_directions_created", direction_count=len(directions),
                    uncertainty_count=sum(len(d.uncertainties) for d in directions), evidence_gap_count=sum(len(d.evidence_gaps) for d in directions),
                    latency_ms=usage["latency_ms"], input_tokens=usage["input_tokens"], output_tokens=usage["output_tokens"], total_tokens=usage["total_tokens"])
                return self.result
        except Exception as error:
            with self._lock:
                if generation != self._generation:
                    return None
                self.status = error.code if isinstance(error, DiscoveryError) else (
                    Status.INVALID_OUTPUT if isinstance(error, LLMStructuredOutputError) else Status.PROVIDER_FAILED)
                self.result = None
                self._event("career_discovery_failed")
                return None
        finally:
            with self._lock:
                self._busy = False

    def current_result(self):
        with self._lock:
            if self.result and self.binding and not self._current(self.binding):
                self.result = None
                self.selected_direction_id = None
                self.status = Status.STALE
            return self.result

    def token(self):
        result = self.current_result()
        if not result or self.status not in {Status.CREATED, Status.SELECTED}:
            return None
        return SelectionToken(owner_scope_id=self.owner_scope_id, conversation_id=self.binding.conversation_id,
            request_id=result.request_id, result_fingerprint=fingerprint(result.model_dump(mode="json")))

    def select(self, token, direction_id):
        with self._lock:
            if token is None or token != self.token() or not any(d.direction_id == direction_id for d in self.result.directions):
                self.status = Status.STALE
                self.selected_direction_id = None
                return False
            self.selected_direction_id, self.status = direction_id, Status.SELECTED
            self._event("career_discovery_direction_selected", selected_direction_id=direction_id)
            return True
