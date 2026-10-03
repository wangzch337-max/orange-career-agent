"""Consent ownership, once-only final turns, failures and historical read-only loads."""

from uuid import uuid4

import pytest

from career_runtime.engine import TurnComplete, AnswerDelta
from career_runtime.session import AgentSession, PendingTurn, FAILURE_TEXT, VALIDATION_TEXT
from tests.agent_doubles import ScriptedProvider, answer, plan, request
from tests.test_agent_runtime import seed
from ui.chat_runtime import Workspace


@pytest.fixture
def workspace(tmp_path):
    with Workspace(str(uuid4()), tmp_path) as value:
        yield value


def test_consent_required_before_configuration_or_provider_access(workspace):
    calls = []
    session = AgentSession(workspace, provider_factory=lambda: calls.append("called"))
    assert not session.consent
    with pytest.raises(PermissionError):
        session.queue("公开问题", "typed")
    assert not calls
    session.set_consent(granted=True)
    assert session.consent
    restored = AgentSession(workspace)
    assert restored.consent
    restored.set_consent(granted=False)
    assert not session.consent
    assert not calls


def test_owner_isolation_and_new_chat_exact_profile_reuse(workspace):
    original = seed(workspace)
    session = workspace.agent_session
    session.set_consent(granted=True)
    previous = workspace.thread.thread_id
    fresh = workspace.create_new_thread()
    assert fresh.thread_id != previous
    assert (fresh.profile_id_ref, fresh.profile_version_ref) == (original.profile_id, original.version)
    assert session.consent and not workspace.chat.messages
    with Workspace(str(uuid4()), workspace.root) as other:
        assert not other.agent_session.consent
        assert other.memory_service.get_current_confirmed_profile(other.subject_id) is None


def test_validated_final_once_and_reload_never_calls_provider(workspace):
    provider = ScriptedProvider()
    session = AgentSession(workspace, provider_factory=lambda: provider)
    session.set_consent(granted=True)
    session.queue("公开问题", "typed")
    pending = session.pending
    session.pending = None
    events = list(session.stream_turn(pending))
    assert any(isinstance(e, TurnComplete) for e in events)
    assert len(workspace.chat.messages) == 2
    assert list(session.stream_turn(pending)) == []
    assert provider.structured_calls == provider.stream_calls == 1
    stored = workspace.store.list_messages(workspace.owner_scope_id, pending.thread_id)
    assert len(stored) == 2 and stored[-1].metadata["agent_activity"]
    assert len(stored[-1].metadata["agent_usage"]) == 2
    serialized = repr(stored)
    for banned in ("reasoning", "scratchpad", "selected_context", "tool_catalog"):
        assert banned not in serialized
    operations = {event.operation for event in workspace.controller.diagnostic_collector.timeline(workspace.controller.diagnostic_context.run_id)}
    assert {"agent_turn", "agent_plan", "agent_response"} <= operations
    workspace.activate(pending.thread_id)
    assert len(workspace.chat.messages) == 2 and provider.stream_calls == 1


@pytest.mark.parametrize("failure", [RuntimeError("PRIVATE_EXCEPTION_TEXT"), ValueError("PRIVATE_EXCEPTION_TEXT")])
def test_stream_failure_persists_only_safe_failure_pair(workspace, failure):
    provider = ScriptedProvider(failure=failure)
    session = AgentSession(workspace, provider_factory=lambda: provider)
    session.set_consent(granted=True)
    session.queue("公开问题", "suggestion")
    list(session.stream_turn(session.pending))
    stored = workspace.store.list_messages(workspace.owner_scope_id, workspace.thread.thread_id)
    assert len(stored) == 2 and stored[-1].content == FAILURE_TEXT
    assert "PRIVATE_EXCEPTION_TEXT" not in repr(stored)
    assert provider.stream_calls == 1 and session.last_result is None
    list(session.stream_turn(session.pending))
    assert len(workspace.store.list_messages(workspace.owner_scope_id, workspace.thread.thread_id)) == 2
    assert provider.stream_calls == 1


def test_interruption_closes_generator_without_partial_content(workspace):
    provider = ScriptedProvider(response=answer("可中断的公开合成流。"))
    session = AgentSession(workspace, provider_factory=lambda: provider)
    session.set_consent(granted=True)
    session.queue("公开问题", "typed")
    iterator = session.stream_turn(session.pending)
    next(e for e in iterator if isinstance(e, AnswerDelta))
    iterator.close()
    assert len(workspace.chat.messages) == 2
    assert workspace.chat.messages[-1].content == FAILURE_TEXT


def test_malformed_metadata_never_commits_temporary_response(workspace):
    provider = ScriptedProvider(response=answer("临时内容不会保存", citations=["not_owned"]))
    session = AgentSession(workspace, provider_factory=lambda: provider)
    session.set_consent(granted=True)
    session.queue("公开问题", "typed")
    list(session.stream_turn(session.pending))
    assert workspace.chat.messages[-1].content == VALIDATION_TEXT
    assert session.last_error == "validation_failure"
    final = workspace.store.list_messages(workspace.owner_scope_id, workspace.thread.thread_id)[-1]
    assert final.metadata["agent_failure"]["stage"] == "response_validation"
    assert final.metadata["agent_failure"]["reason"] == "unknown_reference"
    assert len(final.metadata["agent_usage"]) == 2


def test_request_identity_collision_is_rejected_transactionally(workspace):
    store, owner, thread = workspace.store, workspace.owner_scope_id, workspace.thread.thread_id
    pair = store.append_turn(owner, thread, "问题", "回答", turn_id="test_once")
    assert store.append_turn(owner, thread, "问题", "回答", turn_id="test_once") == pair
    with pytest.raises(ValueError):
        store.append_turn(owner, thread, "不同问题", "不同回答", turn_id="test_once")
    assert len(store.list_messages(owner, thread)) == 2


def test_activity_allowlist_cannot_persist_free_text_or_fake_web_stage(workspace):
    for item in [{"stage": "web_search", "status": "succeeded"},
                 {"stage": "plan", "status": "succeeded", "reasoning": "private"}]:
        with pytest.raises(ValueError):
            workspace.store.append_turn(workspace.owner_scope_id, workspace.thread.thread_id, "问题", "回答",
                assistant_metadata={"agent_activity": [item]})
    assert not workspace.chat.messages
