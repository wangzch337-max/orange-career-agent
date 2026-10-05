"""Conversation-bound ephemeral clarification, no durable authority write APIs."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from threading import RLock
from time import perf_counter
from uuid import uuid4

from clarification.context import ClarificationContextBuilder, binding_for, direction_value, explicit_intent, explicitly_uncertain
from clarification.models import ClarificationAnswerCandidate, OpenClarification
from clarification.needs import generate_needs
from clarification.policy import MAX_ANSWERS, MAX_EVENTS, MAX_QUESTIONS, ClarificationStatus as Status, TurnIntent
from clarification.service import ClarificationError, ClarificationSelector, no_question
from providers.errors import LLMStructuredOutputError


@dataclass
class ClarificationState:
    version: int = 0
    asked_need_ids: set[str] = field(default_factory=set)
    answered_need_ids: set[str] = field(default_factory=set)
    dismissed_need_ids: set[str] = field(default_factory=set)
    closed_topics: set[str] = field(default_factory=set)
    current_open_need: OpenClarification | None = field(default=None, repr=False)
    answer_candidates: list[ClarificationAnswerCandidate] = field(default_factory=list, repr=False)


@dataclass(frozen=True)
class ClarificationEvent:
    event: str
    status: Status
    state_version: int
    source_count: int = 0
    need_count: int = 0
    reason_code: str | None = None
    question_count: int = 0
    latency_ms: int = 0


class ClarificationSession:
    """Every selection needs an explicit action; rerenders cannot call provider."""

    def __init__(self, owner_scope_id, input_factory, *, provider_factory=None):
        self.owner_scope_id = owner_scope_id
        self.input_factory = input_factory
        # Reuse C.2's lazy existing Qwen factory, not a new transport. No factory
        # is called before explicit, disclosed clarification action.
        if provider_factory is None:
            from resume_evidence.session import _qwen_provider
            provider_factory = _qwen_provider
        self.provider_factory = provider_factory
        self.builder = ClarificationContextBuilder()
        self.selector = ClarificationSelector()
        self.state = ClarificationState()
        self.status = Status.IDLE
        self.events: list[ClarificationEvent] = []
        self.usage = None
        self.last_decision = None
        self.parse_failure = None  # Safe structural metadata only; not the error object.
        self._generation = 0
        self._attempted_version = None
        self._statement_key = None
        self._lock = RLock()

    def _event(self, name, **metadata):
        self.events.append(ClarificationEvent(name, self.status, self.state.version, **metadata))
        del self.events[:-MAX_EVENTS]

    def invalidate(self):
        with self._lock:
            version = self.state.version + 1
            self._generation += 1
            self.state = ClarificationState(version=version)
            self._attempted_version = None
            self._statement_key = None
            self.usage, self.last_decision = None, None
            self.parse_failure = None
            self.status = Status.IDLE
            self.events.clear()
            self._event("clarification_invalidated")

    def _inputs(self, current_statement=""):
        inputs = self.input_factory(current_statement=current_statement)
        if inputs.owner_scope_id != self.owner_scope_id:
            raise ValueError("CLARIFICATION_CONTEXT_FAILED")
        return inputs

    def _still_current(self, generation, binding):
        if generation != self._generation:
            return False
        try:
            return binding == binding_for(self._inputs(), self.state.version)
        except Exception:
            return False

    def current_question(self):
        with self._lock:
            question = self.state.current_open_need
            if question and not self._still_current(self._generation, question.binding):
                self.invalidate()
                self.status = Status.STALE_CLARIFICATION_STATE
                return None
            return question

    def can_run(self, *, current_statement=""):
        """UI affordance only; run() repeats every authority/identity check."""
        key = (hashlib.sha256(direction_value(current_statement).encode()).hexdigest()
               if explicit_intent(current_statement) else None)
        return (self.state.current_open_need is None and len(self.state.asked_need_ids) < MAX_QUESTIONS and
            len(self.state.answer_candidates) < MAX_ANSWERS and
            (self._attempted_version != self.state.version or (key is not None and key != self._statement_key)))

    def run(self, intent: TurnIntent, *, current_statement="", expected_binding=None):
        with self._lock:
            # Resume readiness and explicit workflow intent, not keyword routing
            # or unrelated General QA, authorize context/retrieval/model work.
            if intent != TurnIntent.RESUME_REVIEW:
                return no_question()
            if expected_binding is not None and not self._still_current(self._generation, expected_binding):
                self.status = Status.STALE_CLARIFICATION_STATE
                return no_question()
            if self.current_question() is not None:
                return no_question()  # One open question; no stacked call.
            # A genuinely new explicit current intent is a new user-driven
            # clarification turn, not an automatic retry of the old selection.
            key = (hashlib.sha256(direction_value(current_statement).encode()).hexdigest()
                   if explicit_intent(current_statement) else None)
            if key is not None and key != self._statement_key:
                self.state.version += 1
                self._statement_key = key
            if (len(self.state.asked_need_ids) >= MAX_QUESTIONS or len(self.state.answer_candidates) >= MAX_ANSWERS or
                    self._attempted_version == self.state.version):
                return no_question()
            self._attempted_version = self.state.version
            self.parse_failure = None
            generation, version = self._generation, self.state.version
            try:
                inputs = self._inputs(current_statement)
                binding = binding_for(inputs, version)
                context = self.builder.build(inputs, answers=tuple(self.state.answer_candidates))
                needs = generate_needs(context, closed_need_ids=self.state.asked_need_ids,
                                       closed_topics=self.state.closed_topics)
                context = context.model_copy(update={"needs": needs})
            except Exception:
                if generation == self._generation:
                    self.status = Status.CLARIFICATION_CONTEXT_FAILED
                    self._event("clarification_failed")
                return no_question()
            if generation != self._generation:
                return no_question()
            self._event("clarification_context_built", source_count=len(context.sources))
            self._event("clarification_need_generated", need_count=len(needs))
            if not needs:
                self.status = Status.NO_CLARIFICATION_NEEDED
                self.last_decision = no_question()
                self._event("clarification_skipped")
                return self.last_decision
        # Do not hold the session lock during provider I/O. Invalidations can
        # happen meanwhile; only pinned owner/thread/evidence/version can publish.
        started = perf_counter()
        try:
            if not self._still_current(generation, binding):
                raise ClarificationError("STALE_CLARIFICATION_STATE")
            provider = self.provider_factory()
            if not self._still_current(generation, binding):
                raise ClarificationError("STALE_CLARIFICATION_STATE")
            decision, usage = self.selector.select(provider, context)
            with self._lock:
                if not self._still_current(generation, binding):
                    raise ClarificationError("STALE_CLARIFICATION_STATE")
                self.usage, self.last_decision = usage, decision
                if decision.should_ask:
                    selected = next(n for n in needs if n.need_id == decision.selected_need_id)
                    self.state.version += 1
                    bound = binding.model_copy(update={"state_version": self.state.version})
                    self.state.current_open_need = OpenClarification(question_id="question_" + uuid4().hex,
                        binding=bound, need=selected, decision=decision,
                        resolved_sources=tuple((s.ref, s.kind, s.origin_refs) for s in context.sources
                                               if s.ref in selected.source_refs))
                    self.state.asked_need_ids.add(selected.need_id)
                    self.status = Status.QUESTION_OPEN
                    self._event("clarification_selected", reason_code=selected.reason_code.value, question_count=1)
                    self._event("clarification_asked", question_count=1,
                        latency_ms=min(120_000, round((perf_counter() - started) * 1000)))
                else:
                    self.status = Status.NO_CLARIFICATION_NEEDED
                    self._event("clarification_skipped")
                return decision
        except Exception as error:
            with self._lock:
                if generation != self._generation:
                    return no_question()  # Deleted/replaced states never resurrect.
                if isinstance(error, ClarificationError):
                    self.status = Status(error.code)
                    self.parse_failure = error.parse_diagnostic
                elif isinstance(error, LLMStructuredOutputError):
                    self.status = Status.INVALID_CLARIFICATION_PLAN
                else:
                    self.status = Status.PROVIDER_FAILED
                self.usage, self.last_decision = None, None
                self._event("clarification_failed")
                return no_question()

    def answer(self, question: OpenClarification, text: str, *, intent=TurnIntent.ANSWER):
        with self._lock:
            current = self.current_question()
            if current is None or current != question or intent != TurnIntent.ANSWER:
                self.status = Status.ANSWER_NOT_APPLICABLE
                return None
            try:
                from ui.conversation_store import _no_credentials
                if not isinstance(text, str) or not 0 < len(text.strip()) <= 2000:
                    raise ValueError("ANSWER_NOT_APPLICABLE")
                _no_credentials(text)
                candidate = ClarificationAnswerCandidate(candidate_id="clarification_answer_" + uuid4().hex,
                    question_id=question.question_id, need_id=question.need.need_id, topic=question.need.topic,
                    user_answer=text.strip(), uncertainty="explicit_uncertainty" if explicitly_uncertain(text) else "none",
                    created_at=datetime.now(timezone.utc), binding=question.binding,
                    resolved_sources=question.resolved_sources)
            except Exception:
                self.status = Status.ANSWER_NOT_APPLICABLE
                return None
            self.state.answer_candidates.append(candidate)
            self.state.answered_need_ids.add(question.need.need_id)
            self.state.closed_topics.add(question.need.topic)
            self.state.current_open_need = None
            self.state.version += 1
            self.status = Status.ANSWER_RECORDED
            self._event("clarification_answer_recorded")
            return candidate  # No next question, provider, Profile or Memory call.

    def dismiss(self, question: OpenClarification):
        with self._lock:
            if self.current_question() != question:
                self.status = Status.ANSWER_NOT_APPLICABLE
                return False
            self.state.dismissed_need_ids.add(question.need.need_id)
            self.state.closed_topics.add(question.need.topic)
            self.state.current_open_need = None
            self.state.version += 1
            self.status = Status.NO_CLARIFICATION_NEEDED
            self._event("clarification_dismissed")
            return True
