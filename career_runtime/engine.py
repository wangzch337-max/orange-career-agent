"""Bounded Observe → structured Plan → tools → observation → real stream."""

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Iterator
from pydantic import Field

from career_runtime.context import bounded_items, messages_for, recent_turns, semantic_message
from career_runtime.models import Activity, ResponseCore, ResponseEnvelope, SafeFailure, ToolResult, StreamMetrics, length_bucket
from career_runtime.finalization import degrade_suggestions, validate_core_text
from career_runtime.continuity import previous_from_messages, validate_runtime_history
from career_runtime.diagnostics import CallAccounting, PlanFailure, RuntimeDiagnostic
from career_runtime.planning import generate_plan
from career_runtime.cancellation import CancellationRequested
from career_runtime.response_budget import response_budget, validate_continuation_repetition, RESPONSE_TOKEN_CEILING, PLANNER_TOKEN_CEILING
from career_runtime.streaming import StreamingLLMProvider, StreamComplete, StreamDelta, VisibleJSONStream, ResponseStreamError
from career_runtime.tools import ToolRegistry
from observability.events import diagnostic_span, emit
from observability.models import DiagnosticComponent as DC
from observability.models import DiagnosticStatus as DS
from providers.models import GenerationOptions
from ui.conversation_store import _content

MAX_PLANNING_ROUNDS = 2
MAX_TOOL_STEPS = 4
PROMPTS = Path(__file__).parent / "prompts"


class ResponseGenerationOptions(GenerationOptions):
    """Runtime-only bounded long-form budget; older structured providers unchanged."""
    max_output_tokens: int = Field(default=RESPONSE_TOKEN_CEILING, ge=1, le=RESPONSE_TOKEN_CEILING)


@dataclass(frozen=True)
class AnswerDelta:
    text: str


@dataclass(frozen=True)
class TurnComplete:
    answer: ResponseEnvelope
    usage: tuple[dict, ...]
    latency_ms: int
    activities: tuple[Activity, ...]
    registry: ToolRegistry
    diagnostics: tuple[RuntimeDiagnostic, ...] = ()
    accounting: CallAccounting | None = None
    provider_attempts: tuple = ()
    stream_metrics: StreamMetrics | None = None


@dataclass(frozen=True)
class TurnFailed:
    category: str
    diagnostic: SafeFailure
    usage: tuple[dict, ...]
    diagnostics: tuple[RuntimeDiagnostic, ...] = ()
    accounting: CallAccounting | None = None
    provider_attempts: tuple = ()
    stream_metrics: StreamMetrics | None = None


@dataclass(frozen=True)
class TurnCancelled:
    usage: tuple[dict, ...]
    latency_ms: int
    diagnostics: tuple[RuntimeDiagnostic, ...]
    accounting: CallAccounting
    provider_attempts: tuple
    stream_metrics: StreamMetrics


class OrangeRuntime:
    """The provider reasons; code owns budgets, IO, consent and final validation."""

    def __init__(self, provider: StreamingLLMProvider, *, planning_retries: int = 1):
        if not isinstance(provider, StreamingLLMProvider):
            raise TypeError("A real streaming provider capability is required.")
        if type(planning_retries) is not int or planning_retries not in {0, 1}:
            raise ValueError("Planner transport retry must remain bounded to zero or one.")
        self.provider = provider
        self.planning_options = GenerationOptions(max_output_tokens=PLANNER_TOKEN_CEILING, max_retries=planning_retries,
                                                   timeout_seconds=45)
        self.response_options = ResponseGenerationOptions(max_retries=0, timeout_seconds=90)

    def run(self, workspace, user_text: str, *, consent: bool, proposal_permission: bool = False, previous_turn=None, cancellation=None) -> Iterator:
        if not consent:
            raise PermissionError("Provider-context consent is required.")
        _content(user_text)
        if len(user_text) > 2000:
            raise ValueError("Message exceeds runtime budget.")
        started = perf_counter()
        results, executed, usage, activities = [], set(), [], []
        diagnostics = []
        counts = {"planner_invocation_count": 0, "repair_invocation_count": 0, "response_invocation_count": 0}
        attempt_log = self.provider.attempts if hasattr(self.provider, "attempts") else None
        attempt_start = len(attempt_log) if attempt_log is not None else None
        stream_started = False
        bound_reached = False
        failure_stage = "context"
        diagnostic_stage = "context"
        stream_metrics = None
        registry, provider_stream = None, None

        def checkpoint():
            if cancellation is not None:
                cancellation.checkpoint()

        def activity(stage, status):
            value = Activity(stage=stage, status=status)
            activities.append(value)
            return value

        def record(detail):
            diagnostics.append(detail)
            emit(DC.CONVERSATION, "agent_plan" if detail.plan_attempt else "agent_turn",
                 DS(detail.status.upper()), agent_detail=detail)

        def final_statistics():
            attempts = tuple(attempt_log[attempt_start:]) if attempt_start is not None else ()
            accounting = CallAccounting(**counts, tool_attempt_count=len(executed),
                provider_request_count=len(attempts) if attempt_start is not None else None,
                provider_retry_count=sum(item.provider_retry_count > 0 for item in attempts) if attempt_start is not None else None)
            return accounting, attempts

        def cancelled_event():
            if provider_stream is not None and callable(getattr(provider_stream, "close", None)):
                try:
                    provider_stream.close()
                    cancellation.close_attempted = True
                except Exception:
                    cancellation.close_failed = True
            if registry is not None:
                registry.proposals.clear()
                registry.profile_drafts.clear()
                registry.memory_changes.clear()
            accounting, attempts = final_statistics()
            metrics = ((cancellation.provider_metrics[0] or stream_metrics) if counts["response_invocation_count"] else None) or StreamMetrics()
            return TurnCancelled(tuple(usage), round((perf_counter()-started)*1000), tuple(diagnostics), accounting, attempts, metrics)

        if cancellation is not None:
            cancellation.final_event = cancelled_event

        with diagnostic_span(DC.CONVERSATION, "agent_turn"):
            try:
                checkpoint()
                yield activity("understand", "started")
                checkpoint()
                registry = ToolRegistry(workspace, user_text, proposal_permission=proposal_permission, cancellation=cancellation)
                source_messages = workspace.store.list_messages(workspace.owner_scope_id, workspace.thread.thread_id, limit=12)
                history = recent_turns(source_messages)
                previous_turn = previous_turn or previous_from_messages(source_messages)
                base = {"current_message": user_text, "recent_turns": [item.model_dump() for item in history],
                        "previous_turn": previous_turn.model_dump(mode="json"), "authority": registry.authority_summary()}
                yield activity("understand", "succeeded")
                for round_index in range(MAX_PLANNING_ROUNDS):
                    checkpoint()
                    failure_stage = "planning"
                    if round_index:
                        record(RuntimeDiagnostic(stage="replan", status="succeeded", error_category="none", plan_attempt=2))
                    selected = bounded_items([item for result in results for item in result.items])
                    observations = [{"name": result.name.value, "status": result.status,
                        "items": [item.model_dump() for item in result.items if item in selected]} for result in results]
                    yield activity("plan", "started")
                    with diagnostic_span(DC.CONVERSATION, "agent_plan"):
                        plan = generate_plan(self.provider,
                            {**base, "tool_catalog": registry.catalog(), "observations": observations,
                             "remaining_tools": MAX_TOOL_STEPS - len(executed), "last_planning_round": round_index == 1},
                            registry, self.planning_options, round_index=round_index, record=record, usage=usage, counts=counts, cancellation=cancellation)
                    checkpoint()
                    yield activity("plan", "succeeded")
                    if set(plan.referenced_message_ids) - {item.message_id for item in history}:
                        raise ValueError("Unknown conversation reference.")
                    record(RuntimeDiagnostic(stage="conversation_validation", status="succeeded", error_category="none",
                        previous_turn_status=previous_turn.status, dialogue_act=plan.dialogue_act))
                    for request in plan.tools:
                        checkpoint()
                        fingerprint = request.model_dump_json()
                        if fingerprint in executed:
                            continue
                        if len(executed) >= MAX_TOOL_STEPS:
                            bound_reached = True
                            break
                        executed.add(fingerprint)
                        stage = registry.specs[request.name].stage
                        if not registry.permitted(request, plan.relevance):
                            results.append(registry.execute(request, plan.relevance))
                            record(RuntimeDiagnostic(stage="tool_permission_validation", status="skipped", error_category="none",
                                schema_model="ToolRequest", plan_attempt=round_index+1, tool_step_index=len(executed), tool_name_category="registered_read"))
                            yield activity(stage, "skipped")
                            continue
                        record(RuntimeDiagnostic(stage="tool_permission_validation", status="succeeded", error_category="none",
                            schema_model="ToolRequest", plan_attempt=round_index+1, tool_step_index=len(executed),
                            tool_name_category="registered_candidate" if registry.specs[request.name].permission == "candidate" else "registered_read"))
                        yield activity(stage, "started")
                        checkpoint()
                        diagnostic_stage = "tool_execution"
                        with diagnostic_span(DC.CONVERSATION, "agent_tool") as statistics:
                            result = registry.execute(request, plan.relevance)
                            checkpoint()
                            diagnostic_stage = "tool_result_validation"
                            try:
                                result = ToolResult.model_validate(result.model_dump() if hasattr(result, "model_dump") else result)
                            except ValueError:
                                record(RuntimeDiagnostic(stage="tool_result_validation", status="failed", error_category="validation_failure",
                                    schema_model="ToolResult", tool_step_index=len(executed)))
                                raise ValueError("Tool result failed validation.") from None
                            statistics["counts"] = {"result_count": len(result.items)}
                        record(RuntimeDiagnostic(stage="tool_execution", status="failed" if result.status == "failed" else "succeeded",
                            error_category="tool_failure" if result.status == "failed" else "none", tool_step_index=len(executed)))
                        record(RuntimeDiagnostic(stage="tool_result_validation", status="succeeded", error_category="none",
                            schema_model="ToolResult", tool_step_index=len(executed)))
                        results.append(result)
                        yield activity(stage, "succeeded" if result.status == "succeeded" else "failed")
                    if not plan.continue_after_tools:
                        break
                    if round_index == MAX_PLANNING_ROUNDS - 1:
                        bound_reached = True
                if bound_reached:
                    yield activity("bounded", "succeeded")
                checkpoint()
                items = bounded_items([item for result in results for item in result.items])
                refs = {ref.ref for item in items for ref in item.refs}
                history = recent_turns(source_messages, prioritized_ids=plan.referenced_message_ids)
                base["recent_turns"] = [item.model_dump() for item in history]
                partial = next((item.content for item in source_messages if item.role == "assistant"
                    and item.message_id == previous_turn.assistant_message_id and semantic_message(item)
                    and previous_turn.status.value == "CANCELLED"), "")
                budget = response_budget(dialogue_act=plan.dialogue_act, previous_status=previous_turn.status.value,
                    has_cancelled_partial=bool(partial))
                continuation_partial = partial if budget.mode == "cancelled_continuation" else ""
                response_options = ResponseGenerationOptions(**{**self.response_options.model_dump(),
                    "max_output_tokens": budget.provider_max_output_tokens})
                conversation_refs = registry.conversation_citations(
                    [item for item in source_messages if item.message_id in {turn.message_id for turn in history}], plan)
                refs.update(conversation_refs)
                # No full tool result or unselected Profile/Memory enters final prompt.
                payload = {**base, "plan": plan.model_dump(), "selected_context": [item.model_dump() for item in items],
                           "tool_statuses": [{"name": result.name.value, "status": result.status} for result in results],
                           "available_refs": sorted(refs), "tool_proposals": [p.model_dump() for p in registry.proposals],
                           "conversation_citations": sorted(conversation_refs),
                           "bound_reached": bound_reached, "response_budget": budget.payload()}
                yield activity("respond", "started")
                checkpoint()
                failure_stage = "response_stream"
                projection, completion, complete_count, delta_count = VisibleJSONStream(), None, 0, 0
                counts["response_invocation_count"] += 1
                if cancellation is not None:
                    cancellation.response_started = True
                with diagnostic_span(DC.CONVERSATION, "agent_response"):
                    provider_stream = self.provider.stream_structured(messages_for(
                        (PROMPTS / "response_v1.md").read_text(), payload), ResponseEnvelope,
                        response_options, prompt_name="orange_response", prompt_version="v1")
                    for event in provider_stream:
                        checkpoint()
                        if isinstance(event, StreamDelta):
                            delta_count += 1
                            stream_started = True
                            if completion is not None:
                                raise ValueError("Delta after completion.")
                            if text := projection.feed(event.content):
                                # Reject credential-shaped chunks before UI projection.
                                _content(projection.visible)
                                validate_runtime_history(projection.visible, previous_turn)
                                validate_continuation_repetition(projection.visible, continuation_partial)
                                yield AnswerDelta(text)
                        elif isinstance(event, StreamComplete):
                            if completion is not None:
                                if complete_count != 1 or stream_metrics.duplicate_finalization_count or completion != event.response:
                                    raise ValueError("Conflicting or excessive final completion.")
                                stream_metrics = stream_metrics.model_copy(update={"duplicate_finalization_count": 1})
                                continue  # Identical duplicate acknowledgement is not a second answer.
                            complete_count += 1
                            completion = event.response
                            stream_metrics = StreamMetrics.model_validate(event.metrics.model_dump())
                            usage.append(completion.safe_metadata())
                        else:
                            raise ValueError("Unknown streaming event.")
                    checkpoint()
                    if completion is None or complete_count != 1:
                        raise ValueError("Exactly one final completion is required.")
                    failure_stage = "response_validation"
                    if not stream_metrics.transport_completed or stream_metrics.provider_finish_category != "normal_stop" or stream_metrics.output_limit_reached:
                        raise ResponseStreamError("transport_incomplete")
                    core = ResponseCore.model_validate({key: value for key, value in completion.data.model_dump().items() if key != "suggestions"})
                    validate_core_text(core.visible_response)
                    validate_runtime_history(core.visible_response, previous_turn)
                    validate_continuation_repetition(core.visible_response, continuation_partial)
                    if not projection.text_complete or core.visible_response != projection.visible:
                        raise ValueError("Final and streamed content differ.")
                    if set(core.citations) - refs:
                        raise ValueError("Unowned or unavailable citation.")
                    if any(proposal not in registry.proposals for proposal in core.candidate_proposals):
                        raise ValueError("Invented candidate proposal.")
                    past = {user_text, *(s for message in workspace.chat.messages[-6:] for s in message.suggestions)}
                    answer, degraded = degrade_suggestions(completion.data, policy=plan.suggestion_policy, past=past)
                    degraded |= stream_metrics.degraded_optional_metadata
                    stream_metrics = stream_metrics.model_copy(update={"core_valid": True,
                        "visible_length_bucket": length_bucket(len(core.visible_response)),
                        "stream_chunk_count": stream_metrics.stream_chunk_count or delta_count,
                        "optional_metadata_valid": not degraded, "degraded_optional_metadata": degraded})
                    if degraded:
                        record(RuntimeDiagnostic(stage="response_optional_validation", status="skipped", error_category="validation_failure",
                            schema_model="ResponseEnvelope", stream=stream_metrics))
                yield activity("respond", "succeeded")
                checkpoint()
                yield activity("complete", "succeeded")
                checkpoint()
                record(RuntimeDiagnostic(stage="response_validation", status="succeeded", error_category="none", schema_model="ResponseEnvelope", stream=stream_metrics))
                accounting, attempts = final_statistics()
                yield TurnComplete(answer, tuple(usage), round((perf_counter() - started) * 1000), tuple(activities), registry,
                    tuple(diagnostics), accounting, attempts, stream_metrics)
            except CancellationRequested:
                yield cancelled_event()
            except Exception as exc:
                if cancellation is not None and cancellation.requested:
                    yield cancelled_event()  # Close-induced IO errors are not transport failures.
                    return
                from providers.errors import LLMError, LLMStructuredOutputError
                category = ("provider_failure" if exc.diagnostic.error_category == "provider_failure" else "validation_failure") if isinstance(exc, PlanFailure) else "validation_failure" if isinstance(exc, (ValueError, LLMStructuredOutputError)) else "provider_failure" if isinstance(exc, LLMError) else "runtime_failure"
                reason = {"Unowned or unavailable citation.": "unknown_reference", "Invented candidate proposal.": "invented_candidate",
                          "Repeated suggestion.": "repeated_suggestion", "Suggestions violate the current plan.": "suggestion_policy",
                          "Visible response must be first.": "stream_order", "Final and streamed content differ.": "stream_mismatch",
                          "Unsupported runtime history claim.": "runtime_history_claim", "Unknown conversation reference.": "unknown_reference",
                          "Continuation repeats cancelled body.": "invalid_core"}.get(str(exc),
                          "structured_validation" if isinstance(exc, (PlanFailure, LLMStructuredOutputError)) else "provider_error" if isinstance(exc, LLMError) else "execution_error")
                if isinstance(exc, ResponseStreamError):
                    reason = exc.reason
                if failure_stage in {"response_stream", "response_validation"}:
                    stream_metrics = getattr(self.provider, "last_stream_metrics", None) or stream_metrics
                    if stream_metrics is not None and failure_stage == "response_validation":
                        stream_metrics = stream_metrics.model_copy(update={"core_valid": False})
                if not isinstance(exc, PlanFailure):
                    detail_stage = "response_validation" if failure_stage == "response_validation" else "stream_failure" if stream_started else "response_provider_transport" if failure_stage == "response_stream" else diagnostic_stage
                    record(RuntimeDiagnostic(stage=detail_stage, status="failed",
                        error_category="provider_failure" if isinstance(exc, LLMError) and not isinstance(exc, LLMStructuredOutputError) else "validation_failure", stream=stream_metrics))
                yield activity("failed", "failed")
                accounting, attempts = final_statistics()
                yield TurnFailed(category, SafeFailure(category=category, stage=failure_stage, reason=reason,
                    latency_ms=round((perf_counter() - started) * 1000)), tuple(usage), tuple(diagnostics), accounting, attempts, stream_metrics)
                # Re-raise only a sanitized exception so the outer diagnostic span
                # records failure (not a fake SUCCEEDED turn). UI handles this safely.
                raise RuntimeError(category) from None
            finally:
                if provider_stream is not None and callable(getattr(provider_stream, "close", None)):
                    try:
                        provider_stream.close()
                    except Exception:
                        pass
