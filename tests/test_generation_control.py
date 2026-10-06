"""Public synthetic, event-controlled cancellation tests. ZERO live requests."""

import json
from dataclasses import FrozenInstanceError
from threading import Event, Thread, current_thread
from time import perf_counter
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest

from career_runtime.cancellation import CancellationRequested, TurnControl
from career_runtime.context import recent_turns
from career_runtime.continuity import validate_runtime_history
from career_runtime.engine import AnswerDelta, TurnComplete, TurnFailed, OrangeRuntime
from career_runtime.models import PreviousTurn, TurnStatus, Proposal, Relevance, Activity, SafeFailure, StreamMetrics
from career_runtime.session import CANCELLED_TEXT
from tests.agent_doubles import ScriptedProvider, answer, plan, request
from tests.test_agent_runtime import seed
from tests.test_agent_streaming import chunk, provider as real_adapter
from tests.test_chat_theme import _contrast
from tests.test_long_response import LongTransport, prose, wire
from ui.chat_components import DARK_TOKENS, LIGHT_TOKENS, THEME_MODES, shell_stylesheet
from ui.chat_runtime import Workspace


class PausedProvider(ScriptedProvider):
    """Pause actual consumption, not UI animation; close releases blocked IO."""

    def __init__(self, *, partial="公开合成的部分正文。🍊\n", before="stream", plans=None):
        super().__init__(plans, answer(partial + "未显示的尾部。", suggestions=["不应出现的建议"]))
        self.partial, self.before = partial, before
        self.entered, self.release, self.closed, self.close_called = Event(), Event(), Event(), Event()

    def close_io(self):
        self.close_called.set()
        self.release.set()

    def pause(self):
        detach = self._turn_control.attach_close(self.close_io)
        self.entered.set()
        try:
            assert self.release.wait(5), "test IO was not released"
        finally:
            detach()

    def generate_structured(self, *args, **kwargs):
        if self.before == "plan":
            self.pause()
        return super().generate_structured(*args, **kwargs)

    def stream_structured(self, *args, **kwargs):
        self.stream_calls += 1
        self.requests.append(json.loads(args[0][1].content))
        try:
            if self.before != "first_chunk":
                yield from (self._delta('{"visible_response":"' + json.dumps(self.partial, ensure_ascii=False)[1:-1]),)
            self.pause()
            # Deliberately ignores cancellation. The runtime must discard this.
            yield self._delta("不允许继续投影的内容")
        finally:
            self.closed.set()

    @staticmethod
    def _delta(text):
        from career_runtime.streaming import StreamDelta
        return StreamDelta(text)


@pytest.fixture
def workspace(tmp_path):
    w = Workspace(str(uuid4()), tmp_path)
    try:
        yield w
    finally:
        session = w.agent_session
        if session.busy:
            session.request_cancel()
            assert session._worker_done.wait(5)
        session.finish_background()
        w.close()


def configure(w, p):
    s = w.agent_session
    s.provider_factory = lambda: p
    s.set_consent(granted=True)
    return s


def background(w, p, text="公开合成停止练习", *, allow_proposal=False):
    s = configure(w, p)
    s.queue(text, "typed", allow_proposal=allow_proposal)
    pending = s.pending
    s.start_pending()
    assert p.entered.wait(5) and s.busy
    s.progress()  # The renderer's last displayed snapshot is authoritative.
    return s, pending


def finish(s):
    assert s._worker_done.wait(5)
    assert s.finish_background()
    assert not s.busy


def stored(w, pending):
    return w.store.get_turn(w.owner_scope_id, pending.thread_id, pending.turn_id)


def assert_cancelled(w, s, pending, text):
    from observability.context import current_binding
    assert current_binding() is None  # No expired worker/generator scope survives.
    pair = stored(w, pending)
    assert len(pair) == 2 and pair[0].content == pending.text
    assert pair[-1].content == (text or CANCELLED_TEXT)
    meta = pair[-1].metadata
    assert meta["agent_turn_status"] == "CANCELLED" and not meta["suggestions"]
    assert meta["agent_stream"]["cancellation_requested"]
    assert meta["agent_stream"]["partial_response"] == bool(text)
    assert not meta["agent_stream"]["core_valid"]
    assert not meta.get("evidence_refs") and "agent_profile_stamp" not in meta
    assert "agent_failure" not in meta and s.last_error is s.last_failure is s.last_result is None
    assert s.previous_turn().status == TurnStatus.CANCELLED


@pytest.mark.parametrize("before", ["plan", "first_chunk"])
def test_before_first_chunk_persists_concise_cancel_not_fake_answer(workspace, before):
    p = PausedProvider(before=before)
    s, pending = background(workspace, p)
    assert s.request_cancel() and not s.request_cancel()
    finish(s)
    assert_cancelled(workspace, s, pending, "")
    assert p.close_called.is_set()
    assert p.stream_calls == (0 if before == "plan" else 1)
    assert not any(t.role == "assistant" for t in recent_turns(stored(workspace, pending)))


@pytest.mark.parametrize("size", [25, 2000, 6500])
def test_stop_mid_stream_keeps_exact_displayed_unicode_and_refresh_never_resumes(workspace, size):
    p = PausedProvider(partial=prose(size))
    s, pending = background(workspace, p)
    visible = s.progress()[1]
    assert visible == p.partial
    assert s.request_cancel()
    assert s.progress()[1] == visible
    finish(s)
    assert_cancelled(workspace, s, pending, visible)
    assert p.closed.is_set() and p.close_called.is_set()
    assert list(s.stream_turn(pending)) == []
    assert len(workspace.store.list_messages(workspace.owner_scope_id, pending.thread_id)) == 2
    with Workspace(workspace.owner_scope_id, workspace.root) as restored:
        assert restored.chat.messages[-1].content == visible
        assert restored.agent_session.previous_turn().status == TurnStatus.CANCELLED
        assert restored.agent_session.provider is None and restored.agent_session.pending is None
    assert p.structured_calls == p.stream_calls == 1


def test_pending_stop_before_worker_makes_zero_calls(workspace):
    p = ScriptedProvider()
    s = configure(workspace, p)
    s.queue("公开合成", "typed")
    pending = s.pending
    assert s.request_cancel()
    s.start_pending()
    assert p.structured_calls == p.stream_calls == 0
    assert_cancelled(workspace, s, pending, "")


@pytest.mark.parametrize("chunks_to_show", [1, 20, 70])
def test_stop_after_many_actual_transport_chunks_never_consumes_rest(workspace, chunks_to_show):
    t = LongTransport(wire(prose(9500)), shape="uneven")
    p = real_adapter(t)
    s = configure(workspace, p)
    s.queue("公开合成长回复取消", "typed")
    pending, s.pending = s.pending, None
    it = s.stream_turn(pending)
    visible = ""
    for event in it:
        if isinstance(event, AnswerDelta):
            visible += event.text
            if len(visible) >= chunks_to_show * 5:
                break
    delivered = t.stream.delivered
    assert visible and s.request_cancel()
    assert not any(isinstance(e, (AnswerDelta, TurnComplete)) for e in it)
    assert t.stream.closed and t.stream.delivered <= delivered + 1
    assert_cancelled(workspace, s, pending, visible)
    assert len(p.attempts) == 2 and p.attempts[-1].status == "cancelled"
    assert p.attempts[-1].provider_retry_count == 0
    assert stored(workspace, pending)[-1].metadata["agent_stream"]["local_close_attempted"]


def test_freeze_is_last_rendered_snapshot_not_buffered_unseen_text():
    control = TurnControl(background=True)
    control.project("已显示🍊")
    assert control.snapshot()[0] == "已显示🍊"
    control.project("后台尚未显示")
    assert control.request() and control.snapshot()[0] == "已显示🍊"
    with pytest.raises(CancellationRequested):
        control.project("不许追加")
    assert not control.request()


@pytest.mark.parametrize("kind", ["profile_draft", "memory_candidate"])
def test_stop_clears_transient_candidates_and_never_changes_canonical_authority(workspace, monkeypatch, kind):
    from career_runtime.tools import ToolRegistry
    original = seed(workspace)
    text = "公开合成：我现在更想探索 AI 产品方向"
    tool = request(kind, dimension="career_direction_priority", value="ai_product", user_quote=text)
    registries = []
    init = ToolRegistry.__init__
    def capture(self, *args, **kwargs):
        init(self, *args, **kwargs)
        registries.append(self)
    monkeypatch.setattr(ToolRegistry, "__init__", capture)
    p = PausedProvider(plans=[plan(relevance="PROFILE_OR_MEMORY", tools=[tool])])
    s, pending = background(workspace, p, text, allow_proposal=True)
    assert registries[0].proposals
    assert s.request_cancel()
    finish(s)
    assert not registries[0].proposals and not registries[0].profile_drafts and not registries[0].memory_changes
    assert s.last_result is None and not stored(workspace, pending)[-1].metadata["suggestions"]
    assert workspace.memory_service.get_current_confirmed_profile(workspace.subject_id) == original
    assert not workspace.controller.active_memories()


def test_cancelled_planner_result_never_executes_tools_or_replans(workspace, monkeypatch):
    from career_runtime.tools import ToolRegistry
    calls = []
    monkeypatch.setattr(ToolRegistry, "execute", lambda *args: calls.append(args))
    p = PausedProvider(before="plan", plans=[plan(relevance="DIRECT_CAREER", tools=[request("current_profile", sections=["skills"])], continuing=True)])
    s, pending = background(workspace, p)
    assert s.request_cancel()
    finish(s)
    assert not calls and p.structured_calls == 1 and p.stream_calls == 0
    assert_cancelled(workspace, s, pending, "")


def test_cancel_during_invalid_plan_does_not_trigger_structural_repair(workspace):
    p = PausedProvider(before="plan", plans=[{"invalid": "public synthetic"}])
    s, pending = background(workspace, p)
    assert s.request_cancel()
    finish(s)
    assert p.structured_calls == 1 and p.stream_calls == 0
    assert_cancelled(workspace, s, pending, "")


@pytest.mark.parametrize("close_fails", [False, True])
def test_real_adapter_supported_close_unblocks_io_and_does_not_turn_into_transport_failure(workspace, close_fails):
    class Stream:
        def __init__(self):
            self.entered, self.release, self.closed = Event(), Event(), Event()
        def __iter__(self):
            yield chunk('{"visible_response":"公开合成 HTTP 部分正文')
            self.entered.set()
            assert self.release.wait(5)
            raise RuntimeError("UNTRUSTED_HTTP_CLOSE_EXCEPTION")
        def close(self):
            self.closed.set()
            self.release.set()
            if close_fails:
                raise RuntimeError("UNTRUSTED_CLOSE_EXCEPTION")
    class Transport:
        def __init__(self):
            self.stream = Stream()
            self.entered = self.stream.entered
            self.chat = NS(completions=self)
        def parse(self, **kwargs):
            return NS(choices=[NS(message=NS(parsed=plan()))], usage=None)
        def create(self, **kwargs):
            return self.stream
    t = Transport()
    p = real_adapter(t)
    s = configure(workspace, p)
    s.queue("公开合成 HTTP 关闭", "typed")
    pending = s.pending
    s.start_pending()
    assert t.entered.wait(5)
    visible = s.progress()[1]
    assert visible and s.request_cancel()
    finish(s)
    assert t.stream.closed.is_set()
    assert_cancelled(workspace, s, pending, visible)
    meta = stored(workspace, pending)[-1].metadata
    assert meta["agent_stream"]["close_failed"] == close_fails
    assert len(p.attempts) == 2 and p.attempts[-1].status == "cancelled"
    assert "UNTRUSTED_" not in json.dumps(meta)


def test_cancel_before_completed_commit_wins_deterministically(workspace, monkeypatch):
    import career_runtime.session as module
    ready, release = Event(), Event()
    original = module.completed_metadata
    def hold(event):
        value = original(event)
        ready.set()
        assert release.wait(5)
        return value
    monkeypatch.setattr(module, "completed_metadata", hold)
    s = configure(workspace, ScriptedProvider())
    s.queue("公开合成取消先赢", "typed")
    pending = s.pending
    s.start_pending()
    assert ready.wait(5)
    visible = s.progress()[1]
    assert s.request_cancel()
    release.set()
    finish(s)
    assert_cancelled(workspace, s, pending, visible)


def test_completed_atomic_commit_before_cancel_wins_deterministically(workspace, monkeypatch):
    committed, release, stop_called = Event(), Event(), Event()
    original = workspace.store.append_turn
    def hold(*args, **kwargs):
        pair = original(*args, **kwargs)
        if kwargs.get("assistant_metadata", {}).get("agent_turn_status") == "COMPLETED":
            committed.set()
            assert release.wait(5)
        return pair
    monkeypatch.setattr(workspace.store, "append_turn", hold)
    s = configure(workspace, ScriptedProvider())
    s.queue("公开合成完成先赢", "typed")
    pending = s.pending
    s.start_pending()
    assert committed.wait(5)
    result = []
    def stop():
        stop_called.set()
        result.append(s.request_cancel())
    thread = Thread(target=stop)
    thread.start()
    assert stop_called.wait(5)
    release.set()
    thread.join(5)
    finish(s)
    assert result == [False]
    assert stored(workspace, pending)[-1].metadata["agent_turn_status"] == "COMPLETED"
    assert len(stored(workspace, pending)) == 2 and s.last_result is not None


def test_execution_view_borrows_pinned_chat_without_owning_state_or_authority(workspace):
    s = configure(workspace, ScriptedProvider())
    canonical_chat = workspace.chat
    s.queue("公开合成状态访问", "typed")
    first = s._generation
    assert s.workspace is workspace and first.view is not workspace
    assert first.view.chat is canonical_chat
    assert first.view.chat.messages is canonical_chat.messages
    assert first.identity is first.control.identity
    assert (first.identity.owner_scope_id, first.identity.thread_id, first.identity.turn_id) == (
        workspace.owner_scope_id, workspace.thread.thread_id, s.pending.turn_id)
    with pytest.raises(AttributeError):
        first.view.chat = object()
    with pytest.raises(FrozenInstanceError):
        first.identity.generation_id = "replacement"
    assert not hasattr(first.view, "activate") and not hasattr(first.view, "submit")
    assert s.request_cancel()
    # Cancellation reloads canonical state but cannot hide or rebind old reads.
    assert first.view.chat is canonical_chat and workspace.chat is not canonical_chat
    with pytest.raises(CancellationRequested):
        first.control.checkpoint()
    s.queue("公开合成下一轮", "typed")
    second = s._generation
    assert second.identity.generation_id != first.identity.generation_id
    assert second.identity.turn_id != first.identity.turn_id
    assert second.view.chat is workspace.chat and first.view.chat is canonical_chat
    with pytest.raises(CancellationRequested):
        first.control.project("禁止的旧轮追加")
    s.cancel_pending()


def test_execution_view_uses_canonical_suggestion_history_and_completes_once(workspace):
    previous_suggestion = "公开合成：进一步核对证据"
    workspace.store.append_turn(workspace.owner_scope_id, workspace.thread.thread_id,
        "公开合成前轮", "公开合成已完成正文", assistant_metadata={
            "agent_turn_status": "COMPLETED", "suggestions": [previous_suggestion]})
    workspace.activate(workspace.thread.thread_id)
    canonical_chat = workspace.chat
    p = ScriptedProvider(plans=[plan(suggestions="optional_relevant")],
        response=answer("公开合成短答复。🍊", suggestions=[previous_suggestion]))
    s = configure(workspace, p)
    s.queue("公开合成后续问题", "typed")
    pending, s.pending = s.pending, None
    generation = s._generation
    events = list(s.stream_turn(pending))
    finals = [event for event in events if isinstance(event, TurnComplete)]
    assert len(finals) == 1 and finals[0] is s.last_result
    assert finals[0].registry.workspace is generation.view
    assert not finals[0].answer.suggestions  # Reads prior canonical suggestions.
    assert finals[0].stream_metrics.degraded_optional_metadata
    assert generation.view.chat is canonical_chat and len(canonical_chat.messages) == 2
    pair = stored(workspace, pending)
    assert "".join(e.text for e in events if isinstance(e, AnswerDelta)) == pair[-1].content
    assert pair[-1].metadata["agent_turn_status"] == "COMPLETED"
    assert not pair[-1].metadata["suggestions"]
    assert workspace.chat.messages[-1].content == finals[0].answer.visible_response
    assert list(s.stream_turn(pending)) == []
    assert p.structured_calls == p.stream_calls == 1
    messages = workspace.store.list_messages(workspace.owner_scope_id, pending.thread_id)
    assert len(messages) == 4
    with Workspace(workspace.owner_scope_id, workspace.root) as restored:
        assert [m.content for m in restored.chat.messages] == [m.content for m in messages]
        assert restored.agent_session.previous_turn().status == TurnStatus.COMPLETED
        assert restored.agent_session.provider is None


@pytest.mark.parametrize("kind", ["profile_draft", "memory_candidate"])
def test_stale_execution_chat_access_cannot_overwrite_new_turn_or_confirm_candidates(workspace, monkeypatch, kind):
    import career_runtime.session as module
    original_profile = seed(workspace)
    text = "公开合成：我现在更想探索 AI 产品方向"
    tool = request(kind, dimension="career_direction_priority", value="ai_product", user_quote=text)
    proposal = Proposal(kind="profile" if kind == "profile_draft" else "memory",
        dimension="career_direction_priority", value="ai_product", user_quote=text)
    p = ScriptedProvider(plans=[plan(relevance="PROFILE_OR_MEMORY", tools=[tool], suggestions="optional_relevant")],
        response=answer("公开合成待复核说明。", suggestions=["旧轮建议不应保存"], proposals=[proposal]))
    s = configure(workspace, p)
    s.queue(text, "typed", allow_proposal=True)
    first, first_pending = s._generation, s.pending
    canonical_chat = workspace.chat
    ready, release = Event(), Event()
    original = module.completed_metadata
    captured = []
    def hold_old_metadata(event):
        value = original(event)
        if event.registry.cancellation.identity == first.identity:
            captured.append(event.registry)
            ready.set()
            assert release.wait(5)
        return value
    monkeypatch.setattr(module, "completed_metadata", hold_old_metadata)
    try:
        s.start_pending()
        assert ready.wait(5)
        registry = captured[0]
        assert registry.proposals == [proposal] and registry.workspace.chat is canonical_chat
        visible = s.progress()[1]
        assert visible and s.request_cancel()
        assert not registry.proposals and not registry.profile_drafts and not registry.memory_changes
        # Canonical state remains readable; neither a tool nor confirmation gets a lease.
        assert registry.workspace.chat is canonical_chat
        with pytest.raises(CancellationRequested):
            registry.execute(tool, Relevance.PROFILE_OR_MEMORY)
        with pytest.raises(CancellationRequested):
            registry.confirm_proposal(proposal, confirmed_by_user=True)
        with pytest.raises(CancellationRequested):
            first.control.project("禁止的旧轮追加")
        first_pair = stored(workspace, first_pending)
        assert first_pair[-1].metadata["agent_turn_status"] == "CANCELLED"
        assert first_pair[-1].content == visible and not first_pair[-1].metadata["suggestions"]
        newer = ScriptedProvider(response=answer("公开合成下一轮有效回答。"))
        s.provider = newer
        s.queue("公开合成新的问题", "typed")
        second, second_pending = s._generation, s.pending
        s.pending = None
        assert first.identity.generation_id != second.identity.generation_id
        assert second.view.chat is workspace.chat and first.view.chat is canonical_chat
        events = list(s.stream_turn(second_pending))
        assert sum(isinstance(e, TurnComplete) for e in events) == 1
        second_result = s.last_result
        second_pair = stored(workspace, second_pending)
        assert second_pair[-1].metadata["agent_turn_status"] == "COMPLETED"
        release.set()
        assert first.done.wait(5)
        first.worker.join(5)
        assert not first.worker.is_alive()
        assert s.last_result is second_result and s.last_error is s.last_failure is None
        assert s.previous_turn().status == TurnStatus.COMPLETED and not s.busy
        assert stored(workspace, first_pending) == first_pair
        assert stored(workspace, second_pending) == second_pair
        assert workspace.chat.messages[-1].content == second_pair[-1].content
        assert list(s.stream_turn(first_pending, _generation=first)) == []
        assert list(s.stream_turn(second_pending)) == []
        assert len(workspace.store.list_messages(workspace.owner_scope_id, first_pending.thread_id)) == 4
        assert workspace.memory_service.get_current_confirmed_profile(workspace.subject_id) == original_profile
        assert not workspace.controller.active_memories()
        assert p.structured_calls == p.stream_calls == newer.structured_calls == newer.stream_calls == 1
    finally:
        release.set()
        if first.worker is not None:
            assert first.done.wait(5)
            first.worker.join(5)


@pytest.mark.parametrize("operation", ["switch", "new", "delete", "submit"])
def test_busy_navigation_and_second_turn_block_before_any_mutation(workspace, operation):
    old = workspace.thread.thread_id
    other = workspace.create_new_thread().thread_id
    workspace.activate(old)
    p = PausedProvider()
    s, pending = background(workspace, p)
    actions = {"switch": lambda: workspace.activate(other), "new": workspace.create_new_thread,
        "delete": lambda: workspace.delete_thread(old), "submit": lambda: workspace.submit("不可并发")}
    with pytest.raises(ValueError, match="Stop generation"):
        actions[operation]()
    with pytest.raises(ValueError, match="One bounded turn"):
        s.queue("不可并发", "typed")
    assert workspace.thread.thread_id == old and len(workspace.threads) == 2
    assert s.request_cancel()
    finish(s)
    assert_cancelled(workspace, s, pending, p.partial)
    if operation != "submit":
        actions[operation]()
    assert p.stream_calls == 1


@pytest.mark.parametrize("claim", ["刚才连接失败了。", "刚才网络出错了。", "The previous connection failed."])
def test_cancelled_continuation_cannot_invent_transport_failure(claim):
    with pytest.raises(ValueError, match="Unsupported runtime history"):
        validate_runtime_history(claim, PreviousTurn(status=TurnStatus.CANCELLED))


def test_next_continue_receives_cancelled_partial_as_nonauthoritative_context(workspace):
    s, pending = background(workspace, PausedProvider())
    visible = s.progress()[1]
    assert s.request_cancel()
    finish(s)
    p = ScriptedProvider(response=answer("沿着已经显示的部分继续补充。"))
    s.provider = p
    s.queue("继续", "typed")
    next_pending, s.pending = s.pending, None
    events = list(s.stream_turn(next_pending))
    assert any(isinstance(e, TurnComplete) for e in events)
    for payload in p.requests:
        assert payload["previous_turn"]["status"] == "CANCELLED"
        assert any(t["text"] == visible and t["provenance"] == "cancelled_assistant" for t in payload["recent_turns"])
    assert not p.requests[-1]["conversation_citations"]
    assert s.previous_turn().status == TurnStatus.COMPLETED
    assert len(workspace.store.list_messages(workspace.owner_scope_id, pending.thread_id)) == 4


@pytest.mark.parametrize("damage", ["text", "owner", "status", "suggestions", "evidence", "stamp"])
def test_cancelled_annotation_never_changes_text_ownership_or_authority(workspace, damage):
    s, pending = background(workspace, PausedProvider())
    assert s.request_cancel()
    finish(s)
    pair = stored(workspace, pending)
    meta = dict(pair[-1].metadata)
    owner, text = workspace.owner_scope_id, pair[-1].content
    if damage == "text": text += "替换正文"
    elif damage == "owner": owner = str(uuid4())
    elif damage == "status": meta["agent_turn_status"] = "COMPLETED"
    elif damage == "suggestions": meta["suggestions"] = ["不能增加建议"]
    elif damage == "evidence": meta["evidence_refs"] = ["evidence_public_001"]
    elif damage == "stamp": meta["agent_profile_stamp"] = {"profile_id": "profile_public", "version": 1}
    with pytest.raises(ValueError):
        workspace.store.annotate_cancelled_turn(owner, pending.thread_id, pending.turn_id, text, meta)
    assert stored(workspace, pending) == pair


def test_completed_turn_cannot_be_annotated_as_cancelled(workspace):
    s = configure(workspace, ScriptedProvider())
    s.queue("公开完成", "typed")
    pending, s.pending = s.pending, None
    list(s.stream_turn(pending))
    with pytest.raises(ValueError):
        workspace.store.annotate_cancelled_turn(workspace.owner_scope_id, pending.thread_id, pending.turn_id,
            stored(workspace, pending)[-1].content, {"agent_turn_status": "CANCELLED"})


@pytest.mark.parametrize("theme", THEME_MODES)
def test_ui_stop_send_navigation_and_ready_controls(tmp_path, theme):
    from tests.test_chat_product import app, WORKSPACE_KEY, suggestions
    value = app(tmp_path, str(uuid4()))
    w = value.session_state[WORKSPACE_KEY]
    p = PausedProvider()
    try:
        assert not [b for b in value.button if b.key == "orange_stop_generation"]
        w.agent_session.provider_factory = lambda: p
        value.button(key="orange_agent_consent").click().run()
        value.radio(key="orange_appearance").set_value(theme).run()
        value.chat_input[0].set_value("公开合成界面停止").run()
        assert not value.exception and p.entered.wait(5)
        assert not value.button(key="orange_stop_generation").disabled
        assert value.chat_input[0].disabled and value.button(key="orange_new_chat").disabled
        assert all(b.disabled for b in value.button if b.key.startswith(("orange_thread_", "orange_delete_request_")))
        assert not suggestions(value)
        visible = w.agent_session.progress()[1]
        value.button(key="orange_stop_generation").click().run()
        assert w.agent_session._worker_done.wait(5)
        value.run()
        assert not value.exception and not value.chat_input[0].disabled
        assert not value.button(key="orange_new_chat").disabled
        assert not [b for b in value.button if b.key == "orange_stop_generation"]
        assert not suggestions(value) and w.chat.messages[-1].content == visible
        assert len(value.chat_message) == 2
        assert "已停止生成" in [c.value for c in value.caption]
        value.run()
        assert p.stream_calls == 1 and w.chat.messages[-1].content == visible
    finally:
        p.release.set()
        if w.agent_session.busy:
            w.agent_session.request_cancel()
            assert w.agent_session._worker_done.wait(5)
        w.agent_session.finish_background()
        w.close()


@pytest.mark.parametrize("mode", THEME_MODES)
def test_shared_desktop_axis_mobile_bounds_and_semantic_composer_contrast(mode):
    css = shell_stylesheet(mode)
    assert "--oc-chat-max-width:1040px; --oc-chat-gutter:1rem" in css
    assert css.count("max-width:var(--oc-chat-max-width)") == 2
    assert "max-width:68%" in css and "max-width:88%" in css
    assert "margin-left:248px" not in css and "calc(100% - 248px)" not in css
    assert '@media (max-width:700px)' in css and 'max-width:calc(100% - 3rem)' in css
    assert '[data-testid="stChatInputTextArea"]:not(:disabled) {color:var(--oc-text-primary); -webkit-text-fill-color:var(--oc-text-primary); caret-color:var(--oc-accent);}' in css
    assert '[data-testid="stChatInputTextArea"]::placeholder {color:var(--oc-muted); -webkit-text-fill-color:var(--oc-muted); opacity:1;}' in css
    assert '[data-testid="stChatInputTextArea"]::selection {background:var(--oc-accent-soft); color:var(--oc-text-primary); -webkit-text-fill-color:var(--oc-text-primary);}' in css
    assert "st-emotion-cache" not in css


@pytest.mark.parametrize("tokens", [LIGHT_TOKENS, DARK_TOKENS])
def test_typed_caret_selected_text_and_placeholder_are_readable(tokens):
    assert _contrast(tokens["text-primary"], tokens["composer-bg"]) >= 4.5
    assert _contrast(tokens["muted"], tokens["composer-bg"]) >= 4.5
    assert _contrast(tokens["accent"], tokens["composer-bg"]) >= 3
    assert _contrast(tokens["text-primary"], tokens["accent-soft"]) >= 4.5


class CleanupGate:
    """Separate IO wakeup from deliberately unfinished physical cleanup."""

    def __init__(self):
        self.io_release = Event()
        self.cleanup_release = Event()
        self.close_entered = Event()
        self.worker_close_entered = Event()

    def close(self):
        self.close_entered.set()
        if current_thread().name == "orange-agent-turn":
            self.worker_close_entered.set()
        self.io_release.set()
        assert self.cleanup_release.wait(10), "fake cleanup was not released"

    def release(self):
        self.io_release.set()
        self.cleanup_release.set()


class BlockedCleanupStream:
    """Fake SDK stream: close wakes IO, but both close paths stay blocked."""

    def __init__(self, *, before_first=False, ending="normal_stop", partial="公开合成已显示部分🍊。"):
        self.gate = CleanupGate()
        self.entered, self.late_attempted = Event(), Event()
        self.before_first, self.ending, self.partial = before_first, ending, partial

    def __iter__(self):
        if not self.before_first:
            yield chunk('{"visible_response":"' + json.dumps(self.partial, ensure_ascii=False)[1:-1])
        self.entered.set()
        assert self.gate.io_release.wait(10), "fake IO was not released"
        self.late_attempted.set()
        if self.ending == "finish_only":
            yield chunk(finish="stop")
            return
        if self.ending != "eof":
            yield chunk('禁止的旧轮尾部","citations":[],"candidate_proposals":[],"suggestions":["旧轮建议"]}')
            yield chunk(finish="stop")

    def close(self):
        self.gate.close()


class NormalCleanupStream:
    """Independent Turn B stream, optionally held while stale events attack."""

    def __init__(self, text="公开合成下一轮完整回答。🍊", *, held=False):
        self.text, self.entered, self.release = text, Event(), Event()
        self.closed = False
        if not held:
            self.release.set()

    def __iter__(self):
        payload = answer(self.text).model_dump_json()
        yield chunk(payload[:35])
        self.entered.set()
        assert self.release.wait(10), "fake next turn was not released"
        yield chunk(payload[35:])
        yield chunk(finish="stop", usage=NS(prompt_tokens=11, completion_tokens=17, total_tokens=28))

    def close(self):
        self.closed = True
        self.release.set()


class CleanupTransport:
    """Injected shared SDK client; single-turn cleanup MUST NOT close it."""

    def __init__(self, streams):
        self.streams = list(streams)
        self.chat = NS(completions=self)
        self.parse_calls, self.create_calls, self.close_calls = [], [], 0

    def parse(self, **kwargs):
        self.parse_calls.append(kwargs)
        return NS(choices=[NS(message=NS(parsed=plan()))], usage=None)

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return self.streams.pop(0)

    def close(self):
        self.close_calls += 1
        raise AssertionError("request tried to close an injected shared client")


def join_execution(generation):
    assert generation.done.wait(5)
    if generation.worker is not None:
        generation.worker.join(5)
        assert not generation.worker.is_alive()
    for worker in generation.control._close_workers:
        worker.join(5)
        assert not worker.is_alive()


def cancel_with_blocked_cleanup(w, stream, *, text="公开合成清理隔离练习"):
    s = w.agent_session
    s.queue(text, "typed")
    generation = s._generation
    s.start_pending()
    assert stream.entered.wait(5)
    visible = s.progress()[1]
    assert visible == ("" if stream.before_first else stream.partial)
    started = perf_counter()
    assert s.request_cancel()
    assert perf_counter() - started < 1
    assert stream.gate.close_entered.wait(5)
    assert stream.gate.worker_close_entered.wait(5)
    assert not stream.gate.cleanup_release.is_set()
    assert generation.worker.is_alive() and not generation.done.is_set()
    assert not generation.control.cleanup_idle and not s.busy
    assert generation.cancel_committed and generation.released
    assert "ui_released" in generation.control.lifecycle
    assert "cleanup_finished" not in generation.control.lifecycle
    pair = stored(w, generation.pending)
    assert pair[-1].content == (visible or CANCELLED_TEXT)
    assert pair[-1].metadata["agent_turn_status"] == "CANCELLED"
    assert not pair[-1].metadata["suggestions"] and not pair[-1].metadata["agent_activity"]
    return generation, pair


@pytest.mark.parametrize("before_first", [False, True])
def test_blocked_sdk_cleanup_releases_semantic_ui_and_next_turn_completes(workspace, before_first):
    old_stream = BlockedCleanupStream(before_first=before_first)
    new_stream = NormalCleanupStream()
    transport = CleanupTransport([old_stream, new_stream])
    p = real_adapter(transport)
    s = configure(workspace, p)
    generations = []
    try:
        first, first_pair = cancel_with_blocked_cleanup(workspace, old_stream)
        generations.append(first)
        assert old_stream.late_attempted.is_set()
        frozen = first.control.snapshot()[0]
        with pytest.raises(CancellationRequested):
            first.control.project("禁止追加")
        assert first.control.snapshot()[0] == frozen
        assert s.cleanup_status() == {"tracked": 1, "limit": 3, "pending_cleanup": 1}
        assert not s.finish_background()
        s.queue("公开合成下一轮问题", "typed")
        second = s._generation
        generations.append(second)
        assert second.identity.generation_id != first.identity.generation_id
        assert second.control is not first.control and not second.control.requested
        assert s._generation is second and not s._owns(first) and s._owns(second)
        s.start_pending()
        join_execution(second)
        assert s.finish_background()
        assert s.last_result is not None and s.last_result.answer.visible_response == new_stream.text
        second_pair = stored(workspace, second.pending)
        assert second_pair[-1].content == new_stream.text
        assert second_pair[-1].metadata["agent_turn_status"] == "COMPLETED"
        assert second_pair[-1].metadata["agent_usage"][-1]["total_tokens"] == 28
        assert old_stream.gate.worker_close_entered.is_set()
        assert first.worker.is_alive() and not first.done.is_set()
        assert not old_stream.gate.cleanup_release.is_set()
        assert "cleanup_finished" not in first.control.lifecycle
        newest_result, newest_metrics = s.last_result, p.last_stream_metrics
        old_stream.gate.release()
        join_execution(first)
        assert stored(workspace, first.pending) == first_pair
        assert stored(workspace, second.pending) == second_pair
        assert s.last_result is newest_result and p.last_stream_metrics == newest_metrics
        assert s.previous_turn().status == TurnStatus.COMPLETED
        assert p.attempts is second.control.provider_attempts
        assert len(first.control.provider_attempts) == len(second.control.provider_attempts) == 2
        assert first.control.provider_attempts[-1].status == "cancelled"
        assert second.control.provider_attempts[-1].status == "succeeded"
        assert len(workspace.chat.messages) == 4 and not s.busy
        assert s.cleanup_status() == {"tracked": 0, "limit": 3, "pending_cleanup": 0}
        assert "cleanup_finished" in first.control.lifecycle
        assert transport.close_calls == 0
        assert len(transport.parse_calls) == len(transport.create_calls) == 2
        assert all(call["max_tokens"] == 8192 for call in transport.create_calls)
    finally:
        old_stream.gate.release()
        new_stream.release.set()
        for generation in generations:
            join_execution(generation)


def semantic_state(w):
    """Synthetic canonical state and current UI authority, excluding cleanup metadata."""
    s = w.agent_session
    return (w.thread, w.chat, tuple(w.chat.messages), tuple(w.threads),
        tuple((t.thread_id, w.store.list_messages(w.owner_scope_id, t.thread_id),
               w.store.load_snapshot(w.owner_scope_id, t.thread_id)) for t in w.threads),
        w.memory_service.get_current_confirmed_profile(w.subject_id),
        tuple(w.memory_service.memory_store.list_history(w.subject_id)),
        s._generation, s._control, s.pending, s.progress(), s.busy,
        s.last_result, s.last_error, s.last_failure, s.last_cancelled)


@pytest.mark.parametrize("operation", ["switch", "new", "delete"])
def test_blocked_cleanup_navigation_delete_and_late_finish_cannot_resurrect(workspace, operation):
    old_thread = workspace.thread.thread_id
    other_thread = workspace.create_new_thread().thread_id
    workspace.activate(old_thread)
    old_stream = BlockedCleanupStream()
    s = configure(workspace, real_adapter(CleanupTransport([old_stream])))
    first = None
    try:
        first, pair = cancel_with_blocked_cleanup(workspace, old_stream)
        identity, bound_chat = first.identity, first.view.chat
        if operation == "switch":
            workspace.activate(other_thread)
        elif operation == "new":
            workspace.create_new_thread()
        else:
            workspace.delete_thread(old_thread)
        assert workspace.thread.thread_id != old_thread and not s.busy
        assert first.identity is identity and first.view.thread.thread_id == old_thread
        assert first.view.chat is bound_chat and first.view.chat is not workspace.chat
        assert first.worker.is_alive() and not old_stream.gate.cleanup_release.is_set()
        assert not workspace.chat.messages
        before = semantic_state(workspace)
        old_stream.gate.release()
        join_execution(first)
        assert s.finish_background()  # Also safe when the original thread was deleted.
        after = semantic_state(workspace)
        # finish_background clears its old progress pointer, not canonical state.
        assert after[:9] == before[:9]
        assert after[11:] == before[11:]
        assert s.progress() is None and not s.busy
        if operation == "delete":
            assert old_thread not in {thread.thread_id for thread in workspace.threads}
            with pytest.raises(ValueError):
                workspace.store.get_turn(workspace.owner_scope_id, old_thread, first.pending.turn_id)
        else:
            assert stored(workspace, first.pending) == pair
        assert not first.control.registry and s.last_result is None
        assert s.cleanup_status()["tracked"] == 0
    finally:
        old_stream.gate.release()
        if first is not None:
            join_execution(first)


def test_cancel_before_worker_has_no_phantom_cleanup_entry(workspace):
    s = configure(workspace, ScriptedProvider())
    for _ in range(5):
        s.queue("公开合成未启动取消", "typed")
        generation = s._generation
        assert generation.worker is None and not generation.running
        assert s.request_cancel()
        assert stored(workspace, generation.pending)[-1].metadata["agent_turn_status"] == "CANCELLED"
        assert not s.busy and s.pending is None
        assert generation.done.is_set()
        assert s.cleanup_status() == {"tracked": 0, "limit": 3, "pending_cleanup": 0}
    assert s.provider is None


@pytest.mark.parametrize("phase", ["active", "completed"])
@pytest.mark.parametrize("late_kind", ["chunk", "activity", "eof", "normal_stop", "completion",
    "suggestion", "profile_candidate", "memory_candidate", "evidence", "overwrite", "failure"])
def test_late_attack_cannot_cross_session_persistence_or_candidate_authority(workspace, monkeypatch, phase, late_kind):
    """Bypass the engine deliberately: the outer write boundary must reject too."""
    import career_runtime.session as module
    from career_runtime.tools import ToolRegistry
    original_profile = seed(workspace)
    old_text = "公开合成：我现在更想探索 AI 产品方向"
    partial = "公开合成待复核的部分正文。"
    tool_requests = {kind: request(kind, dimension="career_direction_priority", value="ai_product", user_quote=old_text)
        for kind in ("profile_draft", "memory_candidate")}
    proposals = [Proposal(kind=kind, dimension="career_direction_priority", value="ai_product", user_quote=old_text)
        for kind in ("profile", "memory")]
    new_stream = NormalCleanupStream(held=phase == "active")
    s = configure(workspace, real_adapter(CleanupTransport([new_stream])))
    s.queue(old_text, "typed", allow_proposal=True)
    first = s._generation
    cleanup = CleanupGate()
    ready, late_release, attempted = Event(), Event(), Event()
    registries, metadata_calls, writes, generations = [], [], [], [first]
    original_run, original_metadata = OrangeRuntime.run, module.completed_metadata
    original_append = workspace.store.append_turn

    def hostile_old_execution(view, user_text, *, cancellation, **kwargs):
        detach = cancellation.attach_close(cleanup.close)
        registry = ToolRegistry(view, user_text, proposal_permission=True, cancellation=cancellation)
        registries.append(registry)
        registry.authority_summary()
        for tool in tool_requests.values():
            assert registry.execute(tool, Relevance.PROFILE_OR_MEMORY).status == "succeeded"
        try:
            yield Activity(stage="respond", status="started")
            yield AnswerDelta(partial)
            ready.set()
            assert late_release.wait(10)
            attempted.set()
            if late_kind == "eof":
                return
            if late_kind in {"profile_candidate", "memory_candidate"}:
                kind = "profile_draft" if late_kind == "profile_candidate" else "memory_candidate"
                with pytest.raises(CancellationRequested):
                    registry.execute(tool_requests[kind], Relevance.PROFILE_OR_MEMORY)
                with pytest.raises(CancellationRequested):
                    registry.confirm_proposal(proposals[0 if kind == "profile_draft" else 1], confirmed_by_user=True)
            if late_kind == "chunk":
                yield AnswerDelta("禁止的旧轮追加")
            elif late_kind == "activity":
                yield Activity(stage="plan", status="started")
            elif late_kind == "failure":
                yield TurnFailed("runtime_failure", SafeFailure(category="runtime_failure",
                    stage="response_stream", reason="execution_error", latency_ms=0), ())
            else:
                response = answer("禁止的旧轮完成正文", suggestions=["旧轮建议"] if late_kind == "suggestion" else [],
                    citations=[original_profile.evidence[0].id] if late_kind == "evidence" else [],
                    proposals=proposals if late_kind in {"profile_candidate", "memory_candidate"} else [])
                yield TurnComplete(response, (), 0, (), registry,
                    stream_metrics=StreamMetrics(transport_completed=True, provider_finish_category="normal_stop", core_valid=True))
        finally:
            detach()
            cleanup.close()

    def observe_metadata(event):
        metadata_calls.append(event.registry.cancellation.identity)
        return original_metadata(event)

    def observe_write(*args, **kwargs):
        writes.append((kwargs.get("turn_id"), kwargs.get("assistant_metadata", {}).get("agent_turn_status")))
        return original_append(*args, **kwargs)

    # The real runtime is still used for Turn B, with its own provider scope.
    def dispatch(runtime, view, user_text, **kwargs):
        if kwargs["cancellation"].identity == first.identity:
            return hostile_old_execution(view, user_text, **kwargs)
        return original_run(runtime, view, user_text, **kwargs)

    monkeypatch.setattr(OrangeRuntime, "run", dispatch)
    monkeypatch.setattr(module, "completed_metadata", observe_metadata)
    monkeypatch.setattr(workspace.store, "append_turn", observe_write)
    try:
        s.start_pending()
        assert ready.wait(5) and s.progress()[1] == partial
        assert registries[0].proposals == proposals
        assert s.request_cancel() and cleanup.close_entered.wait(5)
        assert not cleanup.cleanup_release.is_set() and first.worker.is_alive()
        assert not s.busy and first.cancel_committed and first.released
        first_pair = stored(workspace, first.pending)
        assert first_pair[-1].metadata["agent_turn_status"] == "CANCELLED"
        assert not first_pair[-1].metadata.get("evidence_refs")
        assert not first_pair[-1].metadata["suggestions"]
        assert not registries[0].proposals and not registries[0].profile_drafts and not registries[0].memory_changes
        s.queue("公开合成下一轮问题", "typed")
        second = s._generation
        generations.append(second)
        s.start_pending()
        assert new_stream.entered.wait(5)
        assert second.control is not first.control and s._generation is second
        if phase == "completed":
            join_execution(second)
            assert s.finish_background()
        else:
            assert s.busy and s.progress()[0].turn_id == second.pending.turn_id
        before = semantic_state(workspace)
        late_release.set()
        assert attempted.wait(5) and cleanup.worker_close_entered.wait(5)
        assert not cleanup.cleanup_release.is_set() and first.worker.is_alive()
        assert semantic_state(workspace) == before
        assert metadata_calls == ([second.identity] if phase == "completed" else [])
        assert not any(turn == first.pending.turn_id and status == "COMPLETED" for turn, status in writes)
        if phase == "active":
            new_stream.release.set()
            join_execution(second)
            assert s.finish_background()
        second_pair = stored(workspace, second.pending)
        assert second_pair[-1].metadata["agent_turn_status"] == "COMPLETED"
        assert second_pair[-1].content == new_stream.text
        assert metadata_calls == [second.identity]
        before_cleanup_return = semantic_state(workspace)
        cleanup.release()
        join_execution(first)
        assert semantic_state(workspace) == before_cleanup_return
        assert stored(workspace, first.pending) == first_pair
        assert stored(workspace, second.pending) == second_pair
        assert len(workspace.chat.messages) == 4 and not s.busy
        assert s.cleanup_status()["tracked"] == 0
    finally:
        late_release.set()
        cleanup.release()
        new_stream.release.set()
        for generation in generations:
            if generation.worker is not None:
                join_execution(generation)


@pytest.mark.parametrize("ending", ["eof", "finish_only"])
def test_cancel_commit_ui_release_then_provider_eof_never_changes_winner(workspace, ending):
    stream = BlockedCleanupStream(ending=ending)
    s = configure(workspace, real_adapter(CleanupTransport([stream])))
    first = None
    try:
        first, pair = cancel_with_blocked_cleanup(workspace, stream)
        assert stream.late_attempted.is_set() and not stream.gate.cleanup_release.is_set()
        stream.gate.release()
        join_execution(first)
        assert s.finish_background()
        final = stored(workspace, first.pending)
        assert len(final) == 2 and final[-1].content == pair[-1].content
        assert final[-1].metadata["agent_turn_status"] == "CANCELLED"
        assert not final[-1].metadata["suggestions"] and not final[-1].metadata.get("evidence_refs")
        assert not final[-1].metadata["agent_stream"]["core_valid"]
        assert s.last_result is None and s.previous_turn().status == TurnStatus.CANCELLED
        assert len(workspace.chat.messages) == 2
    finally:
        stream.gate.release()
        if first is not None:
            join_execution(first)


def test_cleanup_registry_tracks_three_without_eviction_and_collects_only_finished(workspace):
    streams = [BlockedCleanupStream() for _ in range(3)]
    newest = NormalCleanupStream(held=True)
    transport = CleanupTransport([*streams, newest])
    s = configure(workspace, real_adapter(transport))
    generations = []
    try:
        for stream in streams:
            generation, _ = cancel_with_blocked_cleanup(workspace, stream)
            generations.append(generation)
            assert not s.request_cancel()
            assert len(generation.control._close_workers) <= 2
            assert generation.worker.daemon and all(t.daemon for t in generation.control._close_workers)
        ids = {g.identity.generation_id for g in generations}
        assert set(s._executions) == ids
        assert s.cleanup_status() == {"tracked": 3, "limit": 3, "pending_cleanup": 3}
        with pytest.raises(ValueError, match="暂时无法开始"):
            s.queue("公开合成超额请求", "typed")
        assert set(s._executions) == ids and s._generation is generations[-1]
        assert s.pending is None and all(g.worker.is_alive() for g in generations)
        streams[0].gate.release()
        join_execution(generations[0])
        assert not s._worker_done.is_set() and not s.finish_background()
        assert s.cleanup_status() == {"tracked": 2, "limit": 3, "pending_cleanup": 2}
        assert generations[0].control.registry is generations[0].control.final_event is None
        assert "cleanup_finished" in generations[0].control.lifecycle
        s.queue("公开合成腾出容量后的有效请求", "typed")
        active = s._generation
        generations.append(active)
        s.start_pending()
        assert newest.entered.wait(5) and s.busy
        assert s.cleanup_status() == {"tracked": 3, "limit": 3, "pending_cleanup": 2}
        assert active.identity.generation_id in s._executions and not active.done.is_set()
        assert all(g.identity.generation_id in s._executions for g in generations[1:3])
        with pytest.raises(ValueError, match="One bounded turn"):
            s.queue("禁止挤走活跃轮", "typed")
        for g in generations[1:3]:
            with pytest.raises(CancellationRequested):
                g.control.checkpoint()
        newest.release.set()
        join_execution(active)
        assert s.finish_background() and s.last_result is not None
        assert s.cleanup_status() == {"tracked": 2, "limit": 3, "pending_cleanup": 2}
        assert all(g.worker.is_alive() for g in generations[1:3])
        assert sum(g.worker.is_alive() + sum(t.is_alive() for t in g.control._close_workers)
                   for g in s._executions.values()) <= 3 * 3
        for stream in streams[1:]:
            stream.gate.release()
        for g in generations[1:3]:
            join_execution(g)
        assert s.cleanup_status() == {"tracked": 0, "limit": 3, "pending_cleanup": 0}
        assert transport.close_calls == 0 and len(workspace.chat.messages) == 8
    finally:
        for stream in streams:
            stream.gate.release()
        newest.release.set()
        for generation in generations:
            join_execution(generation)


def test_request_owned_sdk_clients_do_not_share_cancelled_cleanup(workspace, monkeypatch):
    class OwnedClient(CleanupTransport):
        def close(self):
            self.close_calls += 1
            if getattr(self, "cleanup_stream", None) is not None:
                self.cleanup_stream.gate.close()
    old_stream, new_stream = BlockedCleanupStream(), NormalCleanupStream()
    clients = [OwnedClient([]), OwnedClient([old_stream]), OwnedClient([]), OwnedClient([new_stream])]
    clients[1].cleanup_stream = old_stream
    created = []
    p = real_adapter(CleanupTransport([]))
    p._client = None  # Exercise the actual default ownership branch, without an SDK/network.
    def create_owned(_options):
        client = clients[len(created)]
        created.append(client)
        return client
    monkeypatch.setattr(p, "_create_client", create_owned)
    s = configure(workspace, p)
    generations = []
    try:
        first, pair = cancel_with_blocked_cleanup(workspace, old_stream)
        generations.append(first)
        assert len(created) == 2 and clients[0].close_calls == 1
        assert clients[1].close_calls and not old_stream.gate.cleanup_release.is_set()
        assert len(first.control._close_workers) == 2
        assert clients[2].close_calls == clients[3].close_calls == 0
        s.queue("公开合成独立请求客户端", "typed")
        second = s._generation
        generations.append(second)
        s.start_pending()
        join_execution(second)
        assert s.finish_background() and s.last_result.answer.visible_response == new_stream.text
        assert len(created) == len({id(client) for client in created}) == 4
        assert clients[2].close_calls == clients[3].close_calls == 1
        assert first.worker.is_alive() and all(t.is_alive() for t in first.control._close_workers)
        assert not old_stream.gate.cleanup_release.is_set()
        state = semantic_state(workspace)
        old_stream.gate.release()
        join_execution(first)
        assert semantic_state(workspace) == state and stored(workspace, first.pending) == pair
        assert len(second.control.provider_attempts) == 2
        assert all(a.status == "succeeded" for a in second.control.provider_attempts)
    finally:
        old_stream.gate.release()
        for generation in generations:
            join_execution(generation)


@pytest.mark.parametrize("shutdown", ["session", "workspace"])
def test_shutdown_returns_while_tracked_cleanup_is_still_blocked(workspace, shutdown):
    stream = BlockedCleanupStream()
    s = configure(workspace, real_adapter(CleanupTransport([stream])))
    first, closer = None, None
    finished, failures = Event(), []
    try:
        first, pair = cancel_with_blocked_cleanup(workspace, stream)
        def close():
            try:
                (s.close if shutdown == "session" else workspace.close)()
            except Exception as exc:
                failures.append(type(exc).__name__)
            finally:
                finished.set()
        closer = Thread(target=close, daemon=True)
        closer.start()
        assert finished.wait(1), "shutdown waited for blocked cleanup"
        closer.join(5)
        assert not closer.is_alive() and not failures
        assert s._closed and first.worker.is_alive() and not first.done.is_set()
        assert not stream.gate.cleanup_release.is_set()
        assert first.identity.generation_id in s._executions
        assert first.worker.daemon and all(t.daemon for t in first.control._close_workers)
        with pytest.raises(CancellationRequested):
            first.control.project("关闭后禁止追加")
        with pytest.raises(ValueError):
            s.queue("关闭后禁止新轮", "typed")
        stream.gate.release()
        join_execution(first)
        assert s.finish_background()
        assert s.cleanup_status()["tracked"] == 0
        final = workspace.store.get_turn(workspace.owner_scope_id, first.pending.thread_id, first.pending.turn_id)
        assert final == pair and s.last_result is None
    finally:
        stream.gate.release()
        if first is not None:
            join_execution(first)
        if closer is not None:
            closer.join(5)


def test_process_exit_does_not_join_blocked_daemon_cleanup(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    script = """
import socket, sys
from pathlib import Path
from uuid import uuid4
from tests.test_generation_control import BlockedCleanupStream, CleanupTransport, configure, cancel_with_blocked_cleanup, real_adapter
from ui.chat_runtime import Workspace
def blocked(*args, **kwargs):
    raise AssertionError('offline child forbids network')
socket.create_connection = socket.socket.connect = blocked
w = Workspace(str(uuid4()), Path(sys.argv[1]))
stream = BlockedCleanupStream()
s = configure(w, real_adapter(CleanupTransport([stream])))
generation, _ = cancel_with_blocked_cleanup(w, stream)
w.close()
assert generation.worker.is_alive() and generation.worker.daemon
assert all(t.daemon for t in generation.control._close_workers)
assert not stream.gate.cleanup_release.is_set()
print('shutdown_without_cleanup_join')
"""
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path / "child")],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert result.stdout.strip() == "shutdown_without_cleanup_join"


def test_shared_provider_across_owners_keeps_state_attempts_and_cleanup_isolated(workspace):
    old_stream, new_stream = BlockedCleanupStream(), NormalCleanupStream()
    transport = CleanupTransport([old_stream, new_stream])
    p = real_adapter(transport)
    configure(workspace, p)
    first = None
    try:
        first, _ = cancel_with_blocked_cleanup(workspace, old_stream)
        with Workspace(str(uuid4()), workspace.root) as other:
            s = configure(other, p)
            s.queue("另一 owner 的公开合成问题", "typed")
            second = s._generation
            s.start_pending()
            join_execution(second)
            assert s.finish_background()
            assert first.identity.owner_scope_id != second.identity.owner_scope_id
            assert first.identity.thread_id != second.identity.thread_id
            payload = json.loads(transport.create_calls[-1]["messages"][1]["content"])
            assert not payload["recent_turns"] and not payload["selected_context"]
            assert not payload["authority"]["confirmed_profile_available"]
            with pytest.raises(ValueError):
                other.store.get_thread(other.owner_scope_id, first.pending.thread_id)
            state, attempts, metrics = semantic_state(other), p.attempts, p.last_stream_metrics
            old_stream.gate.release()
            join_execution(first)
            assert semantic_state(other) == state
            assert p.attempts is attempts is second.control.provider_attempts
            assert p.last_stream_metrics == metrics
            assert other.agent_session.last_result.answer.visible_response == new_stream.text
            assert len(other.chat.messages) == len(workspace.chat.messages) == 2
            assert stored(workspace, first.pending)[-1].metadata["agent_turn_status"] == "CANCELLED"
            assert transport.close_calls == 0
    finally:
        old_stream.gate.release()
        if first is not None:
            join_execution(first)


@pytest.mark.parametrize("theme", THEME_MODES)
def test_ui_composer_and_activity_release_while_old_cleanup_stays_blocked(tmp_path, theme):
    from tests.test_chat_product import app, WORKSPACE_KEY, suggestions
    value = app(tmp_path, str(uuid4()))
    w = value.session_state[WORKSPACE_KEY]
    old_stream, new_stream = BlockedCleanupStream(partial=prose(2000)), NormalCleanupStream()
    transport = CleanupTransport([old_stream, new_stream])
    s, first = w.agent_session, None
    try:
        s.provider_factory = lambda: real_adapter(transport)
        value.button(key="orange_agent_consent").click().run()
        value.radio(key="orange_appearance").set_value(theme).run()
        value.chat_input[0].set_value("公开合成界面慢清理测试").run()
        first = s._generation
        assert old_stream.entered.wait(5) and not value.exception
        assert value.chat_input[0].disabled and value.button(key="orange_new_chat").disabled
        visible = s.progress()[1]
        value.button(key="orange_stop_generation").click().run()
        assert old_stream.gate.worker_close_entered.wait(5)
        assert first.worker.is_alive() and not first.done.is_set()
        assert not old_stream.gate.cleanup_release.is_set()
        assert not value.exception and not value.chat_input[0].disabled
        assert not value.button(key="orange_new_chat").disabled
        assert not [button for button in value.button if button.key == "orange_stop_generation"]
        assert not suggestions(value) and not s.busy
        assert len(value.chat_message) == 2 and w.chat.messages[-1].content == visible
        assert "已停止生成" in [caption.value for caption in value.caption]
        assert not any(caption.value in {"组织回答…", "确定需要的上下文…", "理解这条消息…"} for caption in value.caption)
        assert not [expander for expander in value.expander if expander.label == "Orange 的处理进度"]
        value.chat_input[0].set_value("公开合成下一轮界面问题").run()
        second = s._generation
        join_execution(second)
        value.run()
        assert not value.exception and len(value.chat_message) == 4
        assert not value.chat_input[0].disabled and w.chat.messages[-1].content == new_stream.text
        assert second.identity.generation_id != first.identity.generation_id
        assert first.worker.is_alive() and not old_stream.gate.cleanup_release.is_set()
        value.button(key="orange_new_chat").click().run()
        assert not value.exception and not value.chat_input[0].disabled
        assert len(value.chat_message) == 1 and value.chat_message[0].name == "assistant"
        assert not w.chat.messages and not w.store.list_messages(w.owner_scope_id, w.thread.thread_id)
        value.button(key=f"orange_thread_{first.pending.thread_id}").click().run()
        assert not value.exception and len(value.chat_message) == 4
        old_stream.gate.release()
        join_execution(first)
        value.run()
        assert not value.exception and len(value.chat_message) == 4
        assert w.chat.messages[-1].content == new_stream.text and not value.chat_input[0].disabled
        assert len(transport.create_calls) == len(transport.parse_calls) == 2
        assert transport.close_calls == 0
    finally:
        old_stream.gate.release()
        new_stream.release.set()
        if first is not None:
            join_execution(first)
        w.close()


def test_close_workers_are_deduplicated_bounded_and_lifecycle_is_content_free():
    gates = [CleanupGate(), CleanupGate()]
    control = TurnControl()
    try:
        for _ in range(12):
            for gate in gates:
                control.attach_close(gate.close)
        assert control.request()
        assert all(gate.close_entered.wait(5) for gate in gates)
        assert len(control._close_workers) == len(control._close_keys) == 2
        for _ in range(12):
            assert not control.request()
            for gate in gates:
                control.attach_close(gate.close)
        assert len(control._close_workers) == 2 and not control.cleanup_idle
        assert control.lifecycle == ["cancel_requested", "cleanup_started"]
        for value in ("公开合成正文不应作为事件", "profile", "memory", "reasoning", "cleanup_pending_payload"):
            with pytest.raises(ValueError):
                control.note(value)
        for event in ("cancel_committed", "ui_released"):
            control.note(event)
            control.note(event)
        assert len(control.lifecycle) == 4 and "cleanup_finished" not in control.lifecycle
        for gate in gates:
            gate.release()
        for worker in control._close_workers:
            worker.join(5)
            assert not worker.is_alive()
        assert control.cleanup_idle
        control.note("cleanup_finished")
        assert len(control.lifecycle) == 5
    finally:
        for gate in gates:
            gate.release()
        for worker in control._close_workers:
            worker.join(5)


def test_semantic_cancel_release_requires_essential_persistence(workspace, monkeypatch):
    import sqlite3
    stream = BlockedCleanupStream()
    s = configure(workspace, real_adapter(CleanupTransport([stream])))
    s.queue("公开合成取消保存失败", "typed")
    first = s._generation
    original = workspace.store.append_turn
    try:
        s.start_pending()
        assert stream.entered.wait(5)
        s.progress()
        def unavailable(*args, **kwargs):
            raise sqlite3.OperationalError("synthetic unavailable store")
        monkeypatch.setattr(workspace.store, "append_turn", unavailable)
        assert not s.request_cancel()
        assert stream.gate.worker_close_entered.wait(5)
        assert s.busy and not first.released and not first.cancel_committed
        assert "ui_released" not in first.control.lifecycle
        assert stored(workspace, first.pending) == ()
        with pytest.raises(ValueError, match="One bounded turn"):
            s.queue("不能在必要提交失败后开下一轮", "typed")
        monkeypatch.setattr(workspace.store, "append_turn", original)
        stream.gate.release()
        join_execution(first)
        assert s.finish_background()
        assert stored(workspace, first.pending)[-1].metadata["agent_turn_status"] == "CANCELLED"
        assert not s.busy and s.last_result is None
    finally:
        monkeypatch.setattr(workspace.store, "append_turn", original)
        stream.gate.release()
        join_execution(first)


def test_failure_event_valid_check_cannot_publish_after_cancel_and_new_completion(workspace, monkeypatch):
    s = configure(workspace, ScriptedProvider(response=answer("公开合成新的正常回答。")))
    s.queue("公开合成旧轮错误竞争", "typed")
    first = s._generation
    cleanup = CleanupGate()
    checked, release_check, armed = Event(), Event(), Event()
    original_run, checkpoint = OrangeRuntime.run, first.control.checkpoint
    generations = [first]
    def delayed_checkpoint():
        checkpoint()
        if current_thread() is first.worker and armed.is_set() and not checked.is_set():
            checked.set()
            assert release_check.wait(10)
    def failing_old_run(_runtime, _view, _text, **kwargs):
        detach = first.control.attach_close(cleanup.close)
        try:
            yield AnswerDelta("公开合成旧轮部分正文。")
            armed.set()
            yield TurnFailed("runtime_failure", SafeFailure(category="runtime_failure",
                stage="response_stream", reason="execution_error", latency_ms=0), ())
        finally:
            detach()
            cleanup.close()
    def dispatch(runtime, view, text, **kwargs):
        if kwargs["cancellation"] is first.control:
            return failing_old_run(runtime, view, text, **kwargs)
        return original_run(runtime, view, text, **kwargs)
    monkeypatch.setattr(first.control, "checkpoint", delayed_checkpoint)
    monkeypatch.setattr(OrangeRuntime, "run", dispatch)
    try:
        s.start_pending()
        assert checked.wait(5)
        s.progress()
        assert s.request_cancel()
        s.queue("公开合成下一轮成功", "typed")
        second = s._generation
        generations.append(second)
        s.start_pending()
        join_execution(second)
        assert s.finish_background() and s.last_error is None
        before = semantic_state(workspace)
        release_check.set()
        assert cleanup.worker_close_entered.wait(5)
        assert first.worker.is_alive() and not cleanup.cleanup_release.is_set()
        assert s.last_error is None
        assert semantic_state(workspace) == before
    finally:
        release_check.set()
        cleanup.release()
        for generation in generations:
            join_execution(generation)


def test_setup_error_ownership_check_and_publication_are_atomic_with_cancel(workspace, monkeypatch):
    import career_runtime.session as module
    p = ScriptedProvider(response=answer("公开合成新的正常回答。"))
    s = configure(workspace, p)
    s.queue("公开合成旧轮设置错误竞争", "typed")
    first = s._generation
    cleanup = CleanupGate()
    first.control.attach_close(cleanup.close)
    armed, checked, release_check, published, release_failure = (Event() for _ in range(5))
    owns, failure_model = s._owns, module.SafeFailure
    generations = [first]
    def failed_setup():
        armed.set()
        raise RuntimeError("synthetic setup failure")
    def delayed_ownership(generation):
        valid = owns(generation)
        if generation is first and current_thread() is first.worker and armed.is_set() and not checked.is_set():
            checked.set()
            # Stop can interleave only when the check/write lease is NOT held.
            if not s._lock._is_owned():
                assert release_check.wait(10)
        return valid
    def hold_failure_construction(**kwargs):
        value = failure_model(**kwargs)
        if current_thread() is first.worker:
            published.set()
            assert release_failure.wait(10)
        return value
    s.provider_factory = failed_setup
    monkeypatch.setattr(s, "_owns", delayed_ownership)
    monkeypatch.setattr(module, "SafeFailure", hold_failure_construction)
    try:
        s.start_pending()
        assert checked.wait(5) and s.request_cancel()
        assert cleanup.close_entered.wait(5) and not cleanup.cleanup_release.is_set()
        s.provider = p
        s.queue("公开合成下一轮成功", "typed")
        second = s._generation
        generations.append(second)
        s.start_pending()
        join_execution(second)
        assert s.finish_background() and s.last_error is None
        before = semantic_state(workspace)
        release_check.set()
        assert published.wait(5)
        assert first.worker.is_alive() and not cleanup.cleanup_release.is_set()
        assert s.last_error is None
        assert semantic_state(workspace) == before
    finally:
        release_check.set()
        release_failure.set()
        cleanup.release()
        for generation in generations:
            join_execution(generation)


@pytest.mark.parametrize("kind", ["profile_draft", "memory_candidate"])
def test_candidate_computation_returning_after_cancel_cannot_publish(workspace, monkeypatch, kind):
    original_profile = seed(workspace)
    text = "公开合成：我现在更想探索 AI 产品方向"
    tool = request(kind, dimension="career_direction_priority", value="ai_product", user_quote=text)
    class PlanningTransport(CleanupTransport):
        def parse(self, **kwargs):
            self.parse_calls.append(kwargs)
            value = plan(relevance="PROFILE_OR_MEMORY", tools=[tool]) if len(self.parse_calls) == 1 else plan()
            return NS(choices=[NS(message=NS(parsed=value))], usage=None)
    stream = NormalCleanupStream()
    s = configure(workspace, real_adapter(PlanningTransport([stream])))
    service = (workspace.controller.profile_refinement_service if kind == "profile_draft"
        else workspace.controller.memory_change_detector)
    method = "refine" if kind == "profile_draft" else "detect"
    original = getattr(service, method)
    ready, release = Event(), Event()
    generations = []
    def held_computation(*args, **kwargs):
        result = original(*args, **kwargs)
        ready.set()
        assert release.wait(10)
        return result
    monkeypatch.setattr(service, method, held_computation)
    try:
        s.queue(text, "typed", allow_proposal=True)
        first = s._generation
        generations.append(first)
        s.start_pending()
        assert ready.wait(5)
        registry = first.control.registry
        assert registry is not None and not registry.proposals
        assert s.request_cancel() and not s.busy and first.worker.is_alive()
        s.queue("公开合成下一轮独立问题", "typed")
        second = s._generation
        generations.append(second)
        s.start_pending()
        join_execution(second)
        assert s.finish_background() and s.last_result.answer.visible_response == stream.text
        before = semantic_state(workspace)
        release.set()
        join_execution(first)
        assert semantic_state(workspace) == before
        assert not registry.proposals and not registry.profile_drafts and not registry.memory_changes
        assert workspace.memory_service.get_current_confirmed_profile(workspace.subject_id) == original_profile
        assert not workspace.controller.active_memories()
        assert stored(workspace, first.pending)[-1].metadata["agent_turn_status"] == "CANCELLED"
        assert stored(workspace, second.pending)[-1].metadata["agent_turn_status"] == "COMPLETED"
        assert len(workspace.chat.messages) == 4
    finally:
        release.set()
        stream.release.set()
        for generation in generations:
            join_execution(generation)
