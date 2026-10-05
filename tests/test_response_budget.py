"""Public synthetic budget/continuation checks; conftest blocks ALL sockets."""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from career_runtime.context import recent_turns, MAX_HISTORY_CHARACTERS
from career_runtime.engine import OrangeRuntime, ResponseGenerationOptions, AnswerDelta, TurnComplete
from career_runtime.finalization import finalize_wire, validate_core_text
from career_runtime.models import ResponseCore, StreamMetrics, TurnStatus
from career_runtime.response_budget import (
    HARD_VISIBLE_CHARACTERS, PERSISTENCE_MESSAGE_CHARACTERS, NORMAL_TARGET_CHARACTERS,
    CONTINUATION_TARGET_CHARACTERS, RESPONSE_TOKEN_CEILING, CONTINUATION_TOKEN_CEILING,
    PLANNER_TOKEN_CEILING, MAX_WIRE_CHARACTERS, MAX_STREAM_CHUNKS, MAX_JSON_HEADER_CHARACTERS,
    response_budget, validate_continuation_repetition,
)
from career_runtime.session import VALIDATION_TEXT
from career_runtime.streaming import VisibleJSONStream
from tests.agent_doubles import ScriptedProvider, answer, plan
from tests.test_generation_control import PausedProvider, background, finish
from tests.test_long_response import LongTransport, wire, turn, split
from ui.chat_runtime import Workspace
from ui.conversation_store import ConversationStore, _content


@pytest.fixture
def workspace(tmp_path):
    with Workspace(str(uuid4()), tmp_path) as value:
        yield value


def body(kind, size):
    """Complete public prose/Markdown/code; never fixture-cut an open fence."""
    head, unit, tail = {
        "chinese": ("## 公开示例\n", "这是一般技术解释。", "\n解释结束。"),
        "english": ("## Public example\n", "Explain one bounded step. ", "\nEnd of explanation."),
        "markdown": ("# Public example\n\n", "- **Evidence**: `bounded` step.\n", "\n## Conclusion\nComplete."),
        "code": ("## Public code\n```python\n", 'message = "公开🍊"\n', "# Complete example\n```\nDone."),
        "unicode": ("## Unicode\n", '🍊😀e\u0301汉字\\"\n', "\n结束。"),
    }[kind]
    padding = size - len(head) - len(tail)
    # Remainder is harmless whitespace/comment padding, not sliced output.
    repeats, remainder = divmod(padding, len(unit))
    return head + unit * repeats + " " * remainder + tail


@pytest.mark.parametrize("size", [50, 2000, NORMAL_TARGET_CHARACTERS, 9500, HARD_VISIBLE_CHARACTERS])
@pytest.mark.parametrize("shape,escaped", [("tiny", True), ("medium", False), ("uneven", True)])
def test_normal_size_boundary_stream_persist_refresh_identity(workspace, size, shape, escaped):
    text = body("chinese", size)
    t = LongTransport(wire(text, escaped=escaped), shape=shape)
    session, _, pending, events, stored = turn(workspace, t)
    final = next(e for e in events if isinstance(e, TurnComplete))
    projected = "".join(e.text for e in events if isinstance(e, AnswerDelta))
    assert len(text) == size and projected == text == final.answer.visible_response == stored[-1].content
    assert stored[-1].metadata["agent_turn_status"] == "COMPLETED"
    policy = json.loads(t.calls[0]["messages"][1]["content"])["response_budget"]
    assert policy == response_budget(dialogue_act="new_topic", previous_status="UNKNOWN", has_cancelled_partial=False).payload()
    assert t.calls[0]["max_tokens"] == RESPONSE_TOKEN_CEILING and len(t.calls) == len(t.plan_calls) == 1
    assert list(session.stream_turn(pending)) == []
    workspace.activate(pending.thread_id)
    assert workspace.chat.messages[-1].content == text and len(workspace.chat.messages) == 2


@pytest.mark.parametrize("kind", ["chinese", "english", "markdown", "code", "unicode"])
@pytest.mark.parametrize("shape,escaped", [("medium", False), ("uneven", True)])
def test_language_format_long_complete_identity(workspace, kind, shape, escaped):
    text = body(kind, 5000)
    _, _, _, events, stored = turn(workspace, LongTransport(wire(text, escaped=escaped), shape=shape))
    assert "".join(e.text for e in events if isinstance(e, AnswerDelta)) == text == stored[-1].content
    assert any(isinstance(e, TurnComplete) for e in events)
    if kind == "code":
        assert text.count("```") == 2 and stored[-1].content.endswith("Done.")


@pytest.mark.parametrize("kind", ["chinese", "english", "markdown", "code", "unicode"])
def test_one_over_limit_never_clipped_or_committed_as_completed(workspace, kind):
    text = body(kind, HARD_VISIBLE_CHARACTERS + 1)
    session, _, _, events, stored = turn(workspace, LongTransport(wire(text), shape="uneven"))
    assert not any(isinstance(e, TurnComplete) for e in events)
    assert session.last_failure.reason == "invalid_core"
    assert stored[-1].metadata["agent_turn_status"] == "FAILED_VALIDATION"
    assert stored[-1].content == VALIDATION_TEXT
    assert stored[-1].content not in (text, text[:HARD_VISIBLE_CHARACTERS])
    assert not stored[-1].metadata.get("suggestions")
    with pytest.raises(ValueError):
        ResponseCore(visible_response=text, citations=[], candidate_proposals=[])
    with pytest.raises(ValueError):
        validate_core_text(text)
    with pytest.raises(ValueError):
        finalize_wire(wire(text))


def cancelled(workspace, partial):
    session, pending = background(workspace, PausedProvider(partial=partial),
        "公开合成：逐步解释迭代器、生成器与测试。")
    assert session.progress()[1] == partial and session.request_cancel()
    finish(session)
    pair = workspace.store.get_turn(workspace.owner_scope_id, pending.thread_id, pending.turn_id)
    assert pair[-1].content == partial and pair[-1].metadata["agent_turn_status"] == "CANCELLED"
    return session, pair


def continue_turn(workspace, partial, response, *, act="continue_previous", user="继续", shape="uneven"):
    session, pair = cancelled(workspace, partial)
    p = plan(relevance="LEARNING_OR_TECHNICAL").model_copy(update={"dialogue_act": act})
    t = LongTransport(wire(response), plans=[p], shape=shape)
    from tests.test_agent_streaming import provider
    session.provider = provider(t)
    session.queue(user, "typed")
    pending, session.pending = session.pending, None
    events = list(session.stream_turn(pending))
    return session, pair, t, pending, events


@pytest.mark.parametrize("size", [2000, 4324, 9500])
@pytest.mark.parametrize("user", ["继续", "Please finish the remaining explanation."])
def test_cancelled_semantic_continuation_bounded_no_repeat_completed_refresh(workspace, size, user):
    partial = body("chinese", size)
    continuation = "## 四、验证结果\n" + "接下来用独立测试验证惰性求值。\n" * 80 + "\n剩余解释结束。"
    s, pair, t, pending, events = continue_turn(workspace, partial, continuation, user=user)
    assert any(isinstance(e, TurnComplete) for e in events)
    payload = json.loads(t.calls[0]["messages"][1]["content"])
    assert payload["previous_turn"]["status"] == "CANCELLED"
    assert payload["plan"]["dialogue_act"] == "continue_previous"
    assert payload["response_budget"]["mode"] == "cancelled_continuation"
    assert payload["response_budget"]["target_visible_characters"] == CONTINUATION_TARGET_CHARACTERS
    assert t.calls[0]["max_tokens"] == CONTINUATION_TOKEN_CEILING
    assert t.plan_calls[0]["max_tokens"] == PLANNER_TOKEN_CEILING
    assert len(continuation) <= CONTINUATION_TARGET_CHARACTERS < HARD_VISIBLE_CHARACTERS
    assert partial not in continuation and not payload["conversation_citations"]
    assert not payload["selected_context"] and not payload["tool_proposals"]
    assert "".join(e.text for e in events if isinstance(e, AnswerDelta)) == continuation
    stored = workspace.store.list_messages(workspace.owner_scope_id, pending.thread_id)
    assert len(stored) == 4 and stored[-1].content == continuation
    assert stored[-1].metadata["agent_turn_status"] == "COMPLETED" and stored[:2] == pair
    assert list(s.stream_turn(pending)) == [] and len(t.calls) == len(t.plan_calls) == 1
    with Workspace(workspace.owner_scope_id, workspace.root) as restored:
        assert [m.content for m in restored.chat.messages] == [m.content for m in stored]
        assert restored.agent_session.provider is None and restored.agent_session.previous_turn().status == TurnStatus.COMPLETED
    assert not workspace.controller.active_memories()
    assert workspace.memory_service.get_current_confirmed_profile(workspace.subject_id) is None


@pytest.mark.parametrize("shape", ["tiny", "medium", "uneven"])
def test_full_cancelled_partial_copy_rejected_without_repair(workspace, shape):
    partial = body("english", 2000)
    s, pair, t, pending, events = continue_turn(workspace, partial, "Brief intro.\n" + partial + "\nNew end.", shape=shape)
    assert not any(isinstance(e, TurnComplete) for e in events)
    assert s.last_failure.reason == "invalid_core"
    stored = workspace.store.list_messages(workspace.owner_scope_id, pending.thread_id)
    assert stored[:2] == pair and stored[-1].content == VALIDATION_TEXT
    assert len(t.calls) == len(t.plan_calls) == 1
    assert not any(partial in e.text for e in events if isinstance(e, AnswerDelta))


def test_over_limit_continuation_keeps_cancelled_body_and_safe_failure(workspace):
    partial = body("english", 4324)
    s, pair, t, pending, events = continue_turn(workspace, partial, body("code", 10001))
    assert not any(isinstance(e, TurnComplete) for e in events)
    assert s.last_failure.reason == "invalid_core"
    stored = workspace.store.list_messages(workspace.owner_scope_id, pending.thread_id)
    assert stored[:2] == pair and stored[-1].content == VALIDATION_TEXT
    assert len(t.calls) == len(t.plan_calls) == 1


@pytest.mark.parametrize("act", ["new_topic", "expand_previous", "clarify_previous", "normal_followup"])
def test_cancelled_status_alone_does_not_route_or_reduce_other_modes(workspace, act):
    _, _, t, _, events = continue_turn(workspace, body("chinese", 2000), body("english", 5000), act=act)
    assert any(isinstance(e, TurnComplete) for e in events)
    assert t.calls[0]["max_tokens"] == RESPONSE_TOKEN_CEILING
    assert json.loads(t.calls[0]["messages"][1]["content"])["response_budget"]["mode"] == "normal"


@pytest.mark.parametrize("status,has_partial", [("COMPLETED", True), ("UNKNOWN", True), ("FAILED_TRANSPORT", True), ("CANCELLED", False)])
def test_budget_selection_requires_all_three_authoritative_conditions(status, has_partial):
    budget = response_budget(dialogue_act="continue_previous", previous_status=status, has_cancelled_partial=has_partial)
    assert budget.mode == "normal" and budget.provider_max_output_tokens == RESPONSE_TOKEN_CEILING


def test_long_cancelled_context_keeps_framing_headings_and_larger_exact_tail(workspace):
    partial = "开场解释迭代器\n## 一、协议\n" + "甲"*2900 + "\n## 二、生成器\n" + "乙"*2900 + "\n## 三、测试\n" + "丙"*2900 + "\n停在这个具体步骤🍊"
    _, pair = cancelled(workspace, partial)
    history = recent_turns(pair)
    selected = next(h for h in history if h.provenance == "cancelled_assistant")
    assert selected.excerpted and len(selected.text) <= 2800 and partial not in selected.text
    assert selected.text.endswith(partial[-1000:])
    for fragment in ("开场解释迭代器", "一、协议", "二、生成器", "三、测试", "停在这个具体步骤🍊"):
        assert fragment in selected.text
    assert len(json.dumps([h.model_dump() for h in history], ensure_ascii=False, separators=(",", ":"))) <= MAX_HISTORY_CHARACTERS


@pytest.mark.parametrize("size", [10000, 10001, 19999, 20000])
def test_historical_generic_store_messages_reload_without_new_runtime_validation(workspace, size):
    text = body("english", size)
    pair = workspace.store.append_turn(workspace.owner_scope_id, workspace.thread.thread_id, "旧引导展示", text)
    assert ConversationStore(workspace.store.path).list_messages(workspace.owner_scope_id, workspace.thread.thread_id) == pair
    workspace.activate(workspace.thread.thread_id)
    assert workspace.chat.messages[-1].content == text
    assert _content(text) == text
    with pytest.raises(ValueError):
        _content(body("english", PERSISTENCE_MESSAGE_CHARACTERS + 1))


@pytest.mark.parametrize("value", [0, -1, RESPONSE_TOKEN_CEILING + 1, None, float("inf")])
def test_no_unlimited_provider_output_options(value):
    with pytest.raises(ValueError):
        ResponseGenerationOptions(max_output_tokens=value)


def test_targets_not_hard_limits_and_units_are_not_interchangeable():
    normal = response_budget(dialogue_act="new_topic", previous_status="UNKNOWN", has_cancelled_partial=False)
    continued = response_budget(dialogue_act="continue_previous", previous_status="CANCELLED", has_cancelled_partial=True)
    assert normal.payload()["safety_margin_characters"] == 2000
    assert continued.payload()["safety_margin_characters"] == 6000
    assert 0 < continued.target_visible_characters < normal.target_visible_characters < HARD_VISIBLE_CHARACTERS < PERSISTENCE_MESSAGE_CHARACTERS
    assert 0 < continued.provider_max_output_tokens < normal.provider_max_output_tokens == RESPONSE_TOKEN_CEILING
    text = "🍊" * HARD_VISIBLE_CHARACTERS
    raw = wire(text, escaped=True)
    assert len(text.encode("utf-8")) == 40000 and len(raw) > 120000 and len(raw) < MAX_WIRE_CHARACTERS
    projection = VisibleJSONStream()
    assert "".join(projection.feed(c) for c in split(raw, "uneven")) == text
    assert finalize_wire(raw)[0].visible_response == text
    assert StreamMetrics.model_fields["stream_chunk_count"].metadata[-1].le == MAX_STREAM_CHUNKS
    schema = ResponseCore.model_json_schema()
    assert schema["properties"]["visible_response"]["maxLength"] == HARD_VISIBLE_CHARACTERS
    assert MAX_JSON_HEADER_CHARACTERS == 80
    with pytest.raises(ValueError):
        finalize_wire(raw + " " * MAX_WIRE_CHARACTERS)


def test_brief_recap_allowed_but_whole_substantial_copy_not_rewritten():
    prior = body("english", 2000)
    validate_continuation_repetition("As noted earlier, " + prior[:100] + "\nNow continue.", prior)
    validate_continuation_repetition("短承接", "短承接")
    with pytest.raises(ValueError, match="Continuation repeats"):
        validate_continuation_repetition(prior + "\nNew explanation.", prior)


@pytest.mark.parametrize("damage", ["length_finish", "incomplete_core", "over_limit_code"])
def test_no_cut_code_or_sentence_marked_completed(workspace, damage):
    text = body("code", 9500)
    raw, finish_reason = wire(text), "stop"
    if damage == "length_finish":
        finish_reason = "length"
    elif damage == "incomplete_core":
        raw = raw[:raw.index("# Complete example")]
    else:
        raw = wire(body("code", 10001))
    _, _, _, events, stored = turn(workspace, LongTransport(raw, finish=finish_reason))
    assert not any(isinstance(e, TurnComplete) for e in events)
    assert stored[-1].metadata["agent_turn_status"] != "COMPLETED" and stored[-1].content != text


def test_no_posthoc_replacement_or_extra_context_call_and_prompts_use_contract():
    root = Path(__file__).resolve().parents[1]
    engine = (root / "career_runtime/engine.py").read_text()
    response = (root / "career_runtime/prompts/response_v1.md").read_text()
    assert "response_budget" in response and "target_visible_characters" in response
    assert "cancelled_continuation" in response and "不从头重建原答复" in response
    assert "body[:10000]" not in engine and "visible_response[:" not in engine
    assert "sleep(" not in engine and "SummarizerAgent" not in engine
