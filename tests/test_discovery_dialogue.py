"""Owned pending scope turns use public synthetic authority only."""

from dataclasses import asdict
import json
import pytest

from career_discovery.dialogue import DialogueAct, scope_dialogue_act
from career_discovery.models import Status
from career_background_evaluation.harness import CapturingFake
from tests.career_discovery_doubles import prepared, proposal_from_payload


@pytest.fixture
def h(tmp_path, monkeypatch):
    monkeypatch.setattr("providers.models.load_llm_settings", lambda *a: pytest.fail("No configuration"))
    value = prepared(tmp_path)
    yield value
    value.close()


def pending(h):
    session = h.workspace.career_discovery
    fake = CapturingFake(proposal_from_payload)
    session.provider_factory = lambda: fake
    result = session.start(explicitly_requested=True, consent=True, current_statement="我还没想好职业方向")
    assert result.clarification_need.need_id == "exploration_scope" and fake.attempts == 0
    return session, fake


@pytest.mark.parametrize("text", ["都可以", "两个都看看", "我还没想好", "跨行业也可以", "先看看相邻的", "跨度大一点也没关系", "both are okay", "邻近经验优先"])
def test_pending_answers_resume_once_without_authority_or_new_retrieval(h, monkeypatch, text):
    session, fake = pending(h)
    before = h.current(), h.memories(), h.history()
    token = session.pending_token()
    monkeypatch.setattr(h.workspace.memory_service, "retrieve_context", lambda **k: pytest.fail("No added retrieval"))
    assert session.answer_pending(text, token=token)
    assert session.status == Status.CREATED and session.result.directions and fake.attempts == 1
    assert any(s.text == text and s.category.startswith("reply_to_") for s in session.context.sources)
    assert (h.current(), h.memories(), h.history()) == before
    assert not h.workspace.chat.messages and "career_discovery" not in h.workspace._snapshot()
    assert text not in json.dumps([asdict(e) for e in session.events], ensure_ascii=False)
    assert session.answer_pending(text, token=token) and fake.attempts == 1


@pytest.mark.parametrize("text", ["Transformer 的 attention 是什么？", "请解释 attention", "可以介绍一下 Python", "两个都看看。另外 Python 如何使用？", "what is a generator?", "今天天气晴朗"])
def test_unrelated_or_mixed_text_does_not_implicitly_answer(h, text):
    session, fake = pending(h)
    token = session.pending_token()
    assert not session.answer_pending(text)
    assert session.pending_token() == token and fake.attempts == 0


@pytest.mark.parametrize("change", ["new", "delete", "switch", "profile", "owner", "context", "close"])
def test_stale_pending_token_cannot_resume_or_fall_through(h, change):
    session, fake = pending(h)
    token, w = session.pending_token(), h.workspace
    if change == "new": w.create_new_thread()
    elif change == "delete": w.delete_thread(w.thread.thread_id)
    elif change == "switch": w.activate(w.thread.thread_id)
    elif change == "profile":
        get = w.memory_service.get_current_confirmed_profile
        w.memory_service.get_current_confirmed_profile = lambda subject: get(subject).model_copy(update={"version": 999})
    elif change == "owner": w.owner_scope_id = "other"
    elif change == "context": session.invalidate()
    elif change == "close": w.close()
    assert session.answer_pending("都可以", token=token)
    assert fake.attempts == 0 and not session.result


def test_declarative_answer_is_not_a_phrase_to_preference_rule():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "career_discovery/dialogue.py").read_text()
    assert '"都可以"' not in source and '"两个都看看"' not in source
    assert scope_dialogue_act("要跨行业也行") == DialogueAct.ANSWER
    assert scope_dialogue_act("跨行业是什么意思？") == DialogueAct.QUESTION


def test_rejected_secret_shaped_scope_answer_never_echoed(h):
    session, fake = pending(h)
    assert session.answer_pending("跨行业 sk-" + "A1b2C3d4" * 4)
    assert fake.attempts == 0 and session.status == Status.INVALID_CONTEXT
    assert "sk-" not in json.dumps([asdict(e) for e in session.events])


def test_qa_bridge_cannot_skip_profile_version_change(h):
    session, fake = pending(h)
    assert session.on_general_qa()
    get = h.workspace.memory_service.get_current_confirmed_profile
    h.workspace.memory_service.get_current_confirmed_profile = lambda subject: get(subject).model_copy(update={"version": 999})
    assert not session.finish_general_qa() and not session.result and fake.attempts == 0


def test_ordinary_qa_clears_created_review_without_loading_discovery_inputs(h, monkeypatch):
    session = h.workspace.career_discovery
    session.provider_factory = lambda: CapturingFake(proposal_from_payload)
    assert session.start(explicitly_requested=True, consent=True, current_statement="探索相邻方向").directions
    monkeypatch.setattr(session, "input_factory", lambda **k: pytest.fail("No ordinary QA discovery reads"))
    assert not session.on_general_qa() and session.result is None
