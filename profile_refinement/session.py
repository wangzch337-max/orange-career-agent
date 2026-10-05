"""Ephemeral owner/thread-bound delta review; explicit actions are the only writes."""

from dataclasses import dataclass
from threading import RLock

from memory.errors import ProfileVersionConflictError
from memory.models import ProfileReference
from profile_refinement.confirmation import ACCEPTED, MEMORY_FIELDS, build_confirmed_profile, write_curated_memory
from profile_refinement.context import ProfileRefinementContextBuilder, binding_for_refinement, digest
from profile_refinement.models import ChangeType, RefinementError, Resolution, ReviewToken, Status, Value
from profile_refinement.service import ProfileDeltaProposer, check_value, fingerprint_draft
from providers.errors import LLMStructuredOutputError


@dataclass(frozen=True)
class RefinementEvent:
    event: str
    status: Status
    draft_id: str | None = None
    profile_version: int | None = None
    change_count: int = 0
    source_count: int = 0
    conflict_count: int = 0
    uncertainty_count: int = 0
    latency_ms: int = 0


class ProfileRefinementSession:
    def __init__(self, owner_scope_id, input_factory, memory_service, *, provider_factory=None, on_confirmed=None):
        self.owner_scope_id = owner_scope_id
        self.input_factory = input_factory
        self.memory_service = memory_service
        self.on_confirmed = on_confirmed
        if provider_factory is None:
            from resume_evidence.session import _qwen_provider
            provider_factory = _qwen_provider
        self.provider_factory = provider_factory  # lazy, explicit disclosed action only
        self.builder, self.proposer = ProfileRefinementContextBuilder(), ProfileDeltaProposer()
        self.status = Status.IDLE
        self.draft = self.context = self.base = self.usage = self.confirmed_profile = None
        self.memory_status = "NOT_REQUESTED"
        self.events = []
        self._statement = ""
        self._generation = 0
        self._busy = False
        self._lock = RLock()
        self._pending_profile = None

    @property
    def busy(self):
        return self._busy

    def _event(self, name, **metadata):
        self.events.append(RefinementEvent(name, self.status,
            draft_id=self.draft.draft_id if self.draft else None, **metadata))
        del self.events[:-40]

    def invalidate(self):
        with self._lock:
            self._generation += 1
            self.draft = self.context = self.base = self.usage = self.confirmed_profile = None
            self._pending_profile = None
            self._statement = ""
            self.memory_status = "NOT_REQUESTED"
            self.status = Status.IDLE
            self.events.clear()

    def _inputs(self, *, include_memory=False):
        inputs = self.input_factory(current_statement=self._statement, include_memory=include_memory)
        if inputs.owner_scope_id != self.owner_scope_id:
            raise RefinementError(Status.OWNER_SCOPE_MISMATCH)
        return inputs

    def _current(self, binding):
        try:
            return binding_for_refinement(self._inputs()) == binding
        except Exception:
            return False

    def _validate_memory_sources(self, context, subject_id, refs=None):
        sources = [s for s in context.sources if s.origin == "confirmed_memory" and (refs is None or s.ref in refs)]
        if not sources:
            return
        active = {m.memory_id: m for m in self.memory_service.memory_store.list_active(subject_id)
                  if m.memory_type.value in {"career_preference", "goal", "user_feedback"}}
        for source in sources:
            if len(source.origin_refs) != 1 or source.origin_refs[0] not in active:
                raise RefinementError(Status.INVALID_REFERENCE)

    def current_draft(self):
        with self._lock:
            if self.draft and self.draft.status in {Status.DRAFT, Status.REVIEWING, Status.PROFILE_CONFIRMATION_FAILED}:
                if not self._current(self.draft.binding):
                    self._stale()
            return self.draft

    def _stale(self):
        self.status = Status.STALE_DRAFT
        if self.draft:
            self.draft = self.draft.model_copy(update={"status": Status.STALE_DRAFT})
        self._pending_profile = None
        self._event("profile_draft_stale")

    def token(self):
        draft = self.current_draft()
        return None if draft is None else ReviewToken(draft_id=draft.draft_id,
            draft_fingerprint=draft.draft_fingerprint, owner_scope_id=draft.binding.owner_scope_id,
            conversation_id=draft.binding.conversation_id)

    def start(self, *, explicit_review=False, current_statement="", expected_binding=None):
        with self._lock:
            if not explicit_review or self._busy:
                return None  # General QA / repeated rerender cannot call provider.
            # One fresh explicit draft; late prior output/actions cannot publish.
            self.invalidate()
            self._statement = current_statement
            try:
                inputs = self._inputs(include_memory=True)
                binding = binding_for_refinement(inputs)
                if expected_binding is not None and expected_binding != binding:
                    raise RefinementError(Status.STALE_DRAFT)
                context = self.builder.build(inputs)
                self._validate_memory_sources(context, inputs.subject_id)
            except Exception as error:
                self.status = error.code if isinstance(error, RefinementError) else Status.INVALID_DRAFT
                self._event("profile_refinement_failed")
                return None
            generation = self._generation
            self._busy = True
            self._event("profile_refinement_context_built", source_count=len(context.sources))
        try:
            if not self._current(binding):
                raise RefinementError(Status.STALE_DRAFT)
            provider = self.provider_factory()
            if not self._current(binding):
                raise RefinementError(Status.STALE_DRAFT)
            draft, usage = self.proposer.propose(provider, context, binding)
            with self._lock:
                if generation != self._generation:
                    return None
                if not self._current(binding):
                    raise RefinementError(Status.STALE_DRAFT)
                self.draft, self.context, self.base, self.usage = draft, context, inputs.profile, usage
                self.status = draft.status
                self._event("profile_refinement_no_change" if not draft.changes else "profile_draft_created",
                    profile_version=draft.proposed_profile_version, change_count=len(draft.changes),
                    conflict_count=sum(c.conflict_state != "none" for c in draft.changes),
                    uncertainty_count=sum(c.uncertainty != "none" for c in draft.changes), latency_ms=usage.latency_ms)
                return draft
        except Exception as error:
            with self._lock:
                if generation != self._generation:
                    return None
                self.status = error.code if isinstance(error, RefinementError) else (
                    Status.INVALID_DRAFT if isinstance(error, LLMStructuredOutputError) else Status.PROVIDER_FAILED)
                self._event("profile_refinement_failed")
                return None
        finally:
            with self._lock:
                self._busy = False

    def _validate_action(self, token):
        if token.owner_scope_id != self.owner_scope_id:
            raise RefinementError(Status.OWNER_SCOPE_MISMATCH)
        draft = self.draft
        if draft is None or token.conversation_id != draft.binding.conversation_id:
            raise RefinementError(Status.CONVERSATION_NOT_FOUND)
        if (token.draft_id != draft.draft_id or token.draft_fingerprint != draft.draft_fingerprint or
            fingerprint_draft(draft) != draft.draft_fingerprint):
            raise RefinementError(Status.STALE_DRAFT)
        if draft.status not in {Status.DRAFT, Status.REVIEWING, Status.PROFILE_CONFIRMATION_FAILED}:
            raise RefinementError(Status.STALE_DRAFT)
        if not self._current(draft.binding):
            self._stale()
            raise RefinementError(Status.STALE_DRAFT)
        return draft

    def resolve(self, token, change_id, resolution, *, edited_value=None):
        with self._lock:
            try:
                draft = self._validate_action(token)
                resolution = Resolution(resolution)
                if resolution == Resolution.PENDING:
                    raise RefinementError(Status.INVALID_DRAFT)
                change = next((c for c in draft.changes if c.change_id == change_id), None)
                if change is None:
                    raise RefinementError(Status.INVALID_REFERENCE)
                if resolution == Resolution.EDIT:
                    value = Value.model_validate(edited_value)
                    check_value(change.category, value)
                    if change.change_type == ChangeType.REMOVE:
                        raise RefinementError(Status.INVALID_DRAFT)
                else:
                    if edited_value is not None:
                        raise RefinementError(Status.INVALID_DRAFT)
                    value = change.edited_value  # Later Confirm/Uncertain cannot restore the model value.
                if resolution == Resolution.UNCERTAIN and change.change_type == ChangeType.REMOVE:
                    raise RefinementError(Status.INVALID_DRAFT)
                changed = change.model_copy(update={"user_resolution": resolution, "edited_value": value})
                draft = draft.model_copy(update={"changes": tuple(changed if c.change_id == change_id else c for c in draft.changes),
                                                  "status": Status.REVIEWING})
                self.draft = draft.model_copy(update={"draft_fingerprint": fingerprint_draft(draft)})
                self._pending_profile = None
                self.status = Status.REVIEWING
                event = {Resolution.EDIT: "profile_change_edited", Resolution.REJECT: "profile_change_rejected",
                         Resolution.KEEP_OLD: "profile_change_rejected", Resolution.UNCERTAIN: "profile_change_uncertain"}.get(resolution, "profile_change_reviewed")
                self._event(event)
                return True
            except Exception as error:
                self.status = error.code if isinstance(error, RefinementError) else Status.INVALID_DRAFT
                self._event("profile_review_failed")
                return False

    def reject(self, token):
        with self._lock:
            try:
                draft = self._validate_action(token)
                self.draft = draft.model_copy(update={"status": Status.REJECTED})
                self.status = Status.REJECTED
                self._pending_profile = None
                self._event("profile_draft_rejected")
                return True
            except Exception as error:
                self.status = error.code if isinstance(error, RefinementError) else Status.INVALID_DRAFT
                return False

    def confirm(self, token, *, confirmed_by_user=False, memory_change_id=None):
        binding = self.draft.binding if self.draft else None
        result = self._confirm(token, confirmed_by_user=confirmed_by_user, memory_change_id=memory_change_id)
        # Cross-component cleanup only after releasing the Profile lock. A
        # scoped callback must not clear a newly created clarification session.
        if result is not None and self.on_confirmed and binding is not None:
            try:
                self.on_confirmed(binding)
            except Exception:
                pass  # Optional cleanup cannot invalidate canonical authority.
        return result

    def _confirm(self, token, *, confirmed_by_user=False, memory_change_id=None):
        with self._lock:
            try:
                if confirmed_by_user is not True:
                    raise RefinementError(Status.INVALID_DRAFT)
                # Explicit duplicate click is read-only, never repeats Memory side effects.
                if self.draft and self.draft.status == Status.CONFIRMED and token == self.token():
                    return self.confirmed_profile
                draft = self._validate_action(token)
                if digest(self.base.model_dump(mode="json") if self.base else None) != draft.binding.base_profile_fingerprint:
                    raise RefinementError(Status.STALE_DRAFT)
                if memory_change_id is not None:
                    eligible = {c.change_id for c in draft.changes if c.category in MEMORY_FIELDS and
                        c.user_resolution in ACCEPTED and c.change_type != ChangeType.REMOVE}
                    if memory_change_id not in eligible:
                        raise RefinementError(Status.INVALID_DRAFT)
                # Revalidate refs even if internal candidate models were replaced/constructed.
                for c in draft.changes:
                    if any(ref not in {s.ref for s in self.context.sources} for ref in c.source_refs):
                        raise RefinementError(Status.INVALID_REFERENCE)
                self._validate_memory_sources(self.context, draft.binding.subject_id,
                    {ref for c in draft.changes if c.user_resolution in ACCEPTED for ref in c.source_refs})
                final = self._pending_profile or build_confirmed_profile(draft, self.base, self.context)
                if final is None:
                    self.status = Status.NO_MATERIAL_CHANGE
                    self.draft = draft.model_copy(update={"status": Status.NO_MATERIAL_CHANGE})
                    self._event("profile_refinement_no_change")
                    return None
                self._pending_profile = final  # Stable identity/content for an explicit local retry.
                expected = None if self.base is None else ProfileReference(subject_id=draft.binding.subject_id,
                    profile_id=self.base.profile_id, version=self.base.version)
                self._event("profile_confirmation_started", profile_version=final.version)
                try:
                    saved = self.memory_service.profile_store.save_confirmed_profile(
                        draft.binding.subject_id, final, expected_current=expected,
                        confirmation_guard=lambda: self._validate_action(token))
                except ProfileVersionConflictError:
                    raise
                except RefinementError:
                    raise
                except Exception:
                    # A lost commit acknowledgement cannot create another version.
                    stored = self.memory_service.profile_store.get_profile_version(draft.binding.subject_id, final.profile_id, final.version)
                    current = self.memory_service.get_current_confirmed_profile(draft.binding.subject_id)
                    if stored is None or stored != final or current != stored:
                        raise RefinementError(Status.PROFILE_CONFIRMATION_FAILED) from None
                    saved = None
                self.confirmed_profile = final if saved is None else saved.profile
                self.draft = draft.model_copy(update={"status": Status.CONFIRMED})
                self.status = Status.CONFIRMED
                self._event("profile_confirmation_completed", profile_version=final.version)
                # Profile + pointer are committed. Memory is opt-in and best-effort.
                if memory_change_id is not None:
                    try:
                        self.memory_status = write_curated_memory(self.memory_service, draft.binding.subject_id,
                            self.confirmed_profile, draft, memory_change_id)
                        self._event("profile_memory_side_effect_completed")
                    except Exception:
                        self.memory_status = Status.MEMORY_SIDE_EFFECT_FAILED.value
                        self._event("profile_memory_side_effect_failed")
                return self.confirmed_profile
            except Exception as error:
                self.status = (Status.PROFILE_VERSION_CONFLICT if isinstance(error, ProfileVersionConflictError) else
                    error.code if isinstance(error, RefinementError) else Status.PROFILE_CONFIRMATION_FAILED)
                self._event("profile_confirmation_failed")
                return None
