"""Real public UI entry/default injection; never test-only proposal injection."""

from dataclasses import asdict
import json
import socket
from uuid import uuid4

import pytest

from career_background_evaluation.harness import CareerHarness
from career_background_evaluation.scenarios import SCENARIOS
from career_discovery import demo
from career_discovery.context import CareerDiscoveryContextBuilder, workspace_inputs
from career_discovery.models import DiscoveryProposal, Status
from career_discovery.service import validate
from career_reality.models import Status as RealityStatus
from providers.fake import FakeLLMProvider
from tests.test_chat_product import app, WORKSPACE_KEY
from ui.chat_runtime import Workspace, WorkspaceMode


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def blocked(*a, **k):
        pytest.fail("Public demo cannot access network or local configuration")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr("providers.models.load_llm_settings", blocked)


def confirmed(w, root):
    h = CareerHarness(root, SCENARIOS[12], workspace=w)
    h.prepare(); h.resolve_all(); h.confirm(memory=True)
    w.agent_session.set_consent(granted=False)
    return h


def enter(value, w):
    value.button(key="orange_new_chat").click().run()
    value.button(key="orange_opening_discover").click().run()
    assert w.career_discovery.status == Status.CONSENT_REQUIRED
    value.checkbox(key="orange_discovery_consent_" + w.thread.thread_id).check().run()
    value.button(key="orange_discovery_start").click().run()
    assert w.career_discovery.pending_token().need_id == "exploration_scope"


@pytest.mark.parametrize("selected", ["Business Analysis", "Process Improvement", "Knowledge Operations"])
def test_actual_public_entry_new_chat_clarification_default_proposals_and_d2(tmp_path, monkeypatch, selected):
    value = app(tmp_path, str(uuid4()))
    w = value.session_state[WORKSPACE_KEY]
    try:
        assert w.runtime_mode == WorkspaceMode.PUBLIC_SYNTHETIC_DEMO
        assert type(w.career_discovery.provider_factory()) is demo.PublicSyntheticDiscoveryProvider
        h = confirmed(w, tmp_path)
        before = h.current(), h.memories(), h.history()
        # Count the installed provider; do not replace its proposal or factory.
        calls = []
        original = demo.PublicSyntheticDiscoveryProvider.generate_structured
        def counted(self, messages, model, options, **kwargs):
            calls.append(options)
            return original(self, messages, model, options, **kwargs)
        monkeypatch.setattr(demo.PublicSyntheticDiscoveryProvider, "generate_structured", counted)
        enter(value, w)
        assert not calls
        question = w.career_discovery.result.clarification_need.question
        assert question in [m.value for m in value.markdown]
        monkeypatch.setattr(w.memory_service, "retrieve_context", lambda **k: pytest.fail("Added retrieval"))
        value.chat_input[0].set_value("都可以看看").run()
        assert not value.exception and w.career_discovery.status == Status.CREATED
        assert len(calls) == 1 and calls[0].max_retries == 0 and not calls[0].thinking_enabled
        result = w.career_discovery.result
        assert [d.title for d in result.directions] == ["Business Analysis", "Knowledge Operations", "Process Improvement"]
        assert all(d.status == "candidate" and d.uncertainties and d.evidence_gaps for d in result.directions)
        assert all(c.interpretation_status == "derived_candidate" for d in result.directions for c in d.transferable_capabilities)
        assert sum(c.value == demo.PUBLIC_DEMO_NOTICE for c in value.caption) == 1
        assert not value.warning and not w.chat.messages and w.agent_session.pending is None
        target = next(d for d in result.directions if d.title == selected)
        value.button(key="orange_direction_" + result.request_id + "_" + target.direction_id).click().run()
        assert not value.exception and w.career_reality.status == RealityStatus.ACTIVE
        assert w.career_reality.binding.direction_id == target.direction_id and len(calls) == 1
        assert before == (h.current(), h.memories(), h.history())
        assert not w.store.list_messages(w.owner_scope_id, w.thread.thread_id)
        assert "career_discovery" not in w._snapshot() and "runtime_mode" not in w._snapshot()
        assert "都可以看看" not in json.dumps([asdict(e) for e in w.career_discovery.events], ensure_ascii=False)
        assert w.career_discovery.usage["provider"] == "fake"
        value.run()
        assert len(calls) == 1
    finally:
        w.close()


def test_normal_default_has_no_proposal_and_still_fails_safely(tmp_path, monkeypatch):
    with Workspace(str(uuid4()), tmp_path) as w:
        assert w.runtime_mode == WorkspaceMode.NORMAL
        h = confirmed(w, tmp_path)
        before = h.current(), h.memories(), h.history()
        monkeypatch.setattr(demo, "public_template", lambda: pytest.fail("Normal runtime loaded synthetic fixture"))
        fake = w.career_discovery.provider_factory()
        assert type(fake) is FakeLLMProvider and fake.predefined_response is None
        w.career_discovery.provider_factory = lambda: fake
        assert w.career_discovery.start(explicitly_requested=True, consent=True, current_statement="探索相邻方向") is None
        assert w.career_discovery.status == Status.INVALID_OUTPUT and fake.call_count == 1
        assert w.career_discovery.result is None and w.career_discovery.selected_direction_id is None
        assert before == (h.current(), h.memories(), h.history())
        assert w.career_reality.status == RealityStatus.IDLE and not w.chat.messages


@pytest.mark.parametrize("invalid", [True, False, None, "PUBLIC_SYNTHETIC_DEMO", "NORMAL", "demo"])
def test_runtime_mode_is_code_owned_enum_not_truthy_user_or_session_text(tmp_path, invalid):
    with pytest.raises(ValueError):
        Workspace(str(uuid4()), tmp_path, mode=invalid)
    assert not (tmp_path / "conversations.sqlite3").exists()


def test_demo_and_normal_workspaces_do_not_share_mode_or_provider(tmp_path):
    scope = str(uuid4())
    with Workspace(scope, tmp_path, mode=WorkspaceMode.PUBLIC_SYNTHETIC_DEMO) as w:
        confirmed(w, tmp_path)
        w.career_discovery.start(explicitly_requested=True, consent=True, current_statement="探索相邻方向")
        assert len(w.career_discovery.result.directions) == 3
        with pytest.raises(AttributeError):
            w.runtime_mode = WorkspaceMode.NORMAL
    with Workspace(scope, tmp_path) as normal:
        assert normal.runtime_mode == WorkspaceMode.NORMAL
        assert normal.career_discovery.result is None and normal.career_reality.status == RealityStatus.IDLE
        assert type(normal.career_discovery.provider_factory()) is FakeLLMProvider
        assert normal.career_discovery.start(explicitly_requested=True, consent=True, current_statement="探索相邻方向") is None


def test_bad_demo_result_fails_without_fallback_retry_or_d2(tmp_path, monkeypatch):
    value = app(tmp_path, str(uuid4()))
    w = value.session_state[WORKSPACE_KEY]
    try:
        h = confirmed(w, tmp_path)
        before = h.current(), h.memories(), h.history()
        enter(value, w)
        calls = []
        def broken():
            calls.append(True)
            raise ValueError("PUBLIC_DEMO_INVALID")
        monkeypatch.setattr(demo, "public_template", broken)
        value.chat_input[0].set_value("都可以看看").run()
        assert not value.exception and w.career_discovery.result is None and len(calls) == 1
        assert any("未自动重试或补造方向" in warning.value for warning in value.warning)
        assert not [b for b in value.button if b.label == "继续探索这个方向"]
        assert w.career_reality.status == RealityStatus.IDLE
        assert before == (h.current(), h.memories(), h.history())
        value.run()
        assert len(calls) == 1
    finally:
        w.close()


@pytest.mark.parametrize("count", range(6))
def test_shared_public_fixture_zero_to_five_stays_in_existing_validator(tmp_path, count):
    with Workspace(str(uuid4()), tmp_path) as w:
        confirmed(w, tmp_path)
        context = CareerDiscoveryContextBuilder().build(workspace_inputs(w, current_statement="探索相邻方向"), "demo_schema")
        proposal = DiscoveryProposal.model_validate(demo.proposal_from_payload(context.provider_payload(),
            titles=tuple(f"Exploration Family {i}" for i in range(count))))
        result = validate(proposal, context)
        assert len(result) == count
        assert all(d.confidence.value == "TENTATIVE" and d.goal_relation.value == "EXPLORATORY" for d in result)


def test_demo_fixture_is_strict_and_contains_no_specific_jobs_or_rankings():
    template = demo.public_template()
    assert len(template.directions) == 3
    for item in template.directions:
        assert item.uncertainties and item.evidence_gaps
        assert item.confidence.value == "TENTATIVE" and item.goal_relation.value == "EXPLORATORY"
        assert all(c.uncertainty == "requires_validation" for c in item.transferable_capabilities)
    bad = template.model_dump()
    bad["directions"][0]["ranking"] = 1
    with pytest.raises(ValueError):
        DiscoveryProposal.model_validate(bad)


def test_public_demo_does_not_skip_confirmed_profile_or_consent(tmp_path):
    with Workspace(str(uuid4()), tmp_path, mode=WorkspaceMode.PUBLIC_SYNTHETIC_DEMO) as w:
        assert w.career_discovery.start(explicitly_requested=True) is None
        assert w.career_discovery.status == Status.CONSENT_REQUIRED
        result = w.career_discovery.start(explicitly_requested=True, consent=True)
        assert result.clarification_need.need_id == "background" and not result.directions


def test_entry_replaces_old_normal_session_but_never_replays_or_seeds_profile(tmp_path):
    value = app(tmp_path, str(uuid4()))
    initial = value.session_state[WORKSPACE_KEY]
    scope = initial.owner_scope_id
    initial.close()
    old = Workspace(scope, tmp_path)
    value.session_state[WORKSPACE_KEY] = old
    value.run()
    current = value.session_state[WORKSPACE_KEY]
    try:
        assert not value.exception and old._closed
        assert current is not old and current.runtime_mode == WorkspaceMode.PUBLIC_SYNTHETIC_DEMO
        assert current.owner_scope_id == scope and not current.chat.messages
        assert current.career_discovery.result is None
        assert current.memory_service.get_current_confirmed_profile(current.subject_id) is None
    finally:
        current.close()
