"""Public, deterministic multi-turn context/status/authority regressions."""

import json
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest

from career_runtime.context import recent_turns, excerpt, MAX_HISTORY_CHARACTERS
from career_runtime.continuity import message_status, validate_runtime_history
from career_runtime.engine import TurnComplete, TurnFailed, AnswerDelta
from career_runtime.models import PreviousTurn, TurnStatus
from career_runtime.session import AgentSession, FAILURE_TEXT
from career_runtime.streaming import ResponseStreamError
from tests.agent_doubles import ScriptedProvider, answer, plan, request
from tests.test_agent_runtime import seed
from ui.chat_runtime import Workspace


@pytest.fixture
def workspace(tmp_path):
    with Workspace(str(uuid4()), tmp_path) as value:
        yield value


def turn(workspace, text, response=None, *, act="normal_followup", mode="GENERAL_QA", tools=(), failure=None):
    provider = ScriptedProvider([plan(relevance=mode, tools=tools).model_copy(update={"dialogue_act": act})], response or answer(), failure=failure)
    session = workspace.agent_session
    session.provider = provider
    session.set_consent(granted=True)
    session.queue(text, "typed")
    pending, session.pending = session.pending, None
    events = list(session.stream_turn(pending))
    return provider, events


THREE = "## 一、产品思维\n识别问题与用户需求。\n## 二、协作沟通\n澄清需求、协调利益与解释取舍。\n## 三、效果验证\n用反馈与证据验证改进。"


@pytest.mark.parametrize("text,act", [("继续", "continue_previous"), ("继续详细说", "expand_previous"),
    ("详细一点", "expand_previous"), ("把刚才三个维度分别展开", "expand_previous"),
    ("第二点具体是什么意思？", "clarify_previous"), ("展开第二点", "refer_to_previous_item"),
    ("再给我五个例子", "expand_previous"), ("为什么你刚才这么判断？", "clarify_previous"),
    ("其中产品思维这一项", "refer_to_previous_item"), ("把刚才那份建议改得更简洁", "normal_followup"),
    ("这个", "refer_to_previous_item"), ("第二个", "refer_to_previous_item"),
    ("刚才那个", "refer_to_previous_item"), ("前面提到的岗位", "refer_to_previous_item"),
    ("你前面说的 EXPERIENCE_DEPTH_GAP 是什么意思？", "clarify_previous")])
def test_completed_followups_receive_truth_and_previous_structure(workspace, text, act):
    turn(workspace, "公开合成：产品岗位面试重点", answer(THREE), mode="DIRECT_CAREER")
    provider, events = turn(workspace, text, answer("沿用前面的三个维度，第二项是协作沟通。"), act=act, mode="DIRECT_CAREER")
    assert any(isinstance(event, TurnComplete) for event in events)
    for payload in provider.requests:
        assert payload["previous_turn"]["status"] == "COMPLETED"
        assert THREE in [item["text"] for item in payload["recent_turns"]]
        assert any(item["provenance"] == "completed_assistant" for item in payload["recent_turns"])
    assert provider.requests[-1]["plan"]["dialogue_act"] == act
    assert provider.stream_calls == provider.structured_calls == 1


@pytest.mark.parametrize("claim", ["抱歉，刚才的回答被截断了。", "上一条没有生成完整。", "刚才连接中断了。",
    "我重新继续刚才失败的内容。", "上一轮回答未完成。", "The previous response was truncated.",
    "The last connection was disconnected.", "上一条回答没有保存，所以被截断了。", "刚才没有被截断，但是上一条回复不完整。"])
def test_explicit_false_runtime_claim_blocked_before_display_and_commit(workspace, claim):
    turn(workspace, "公开问题", answer(THREE))
    _, events = turn(workspace, "继续", answer(claim))
    assert not any(isinstance(event, TurnComplete) for event in events)
    assert not any(claim in event.text for event in events if isinstance(event, AnswerDelta))
    stored = workspace.store.list_messages(workspace.owner_scope_id, workspace.thread.thread_id)
    assert claim not in [item.content for item in stored]
    assert stored[-1].metadata["agent_failure"]["reason"] == "runtime_history_claim"
    assert message_status(stored[-1]) == TurnStatus.FAILED_VALIDATION


@pytest.mark.parametrize("status", [TurnStatus.COMPLETED, TurnStatus.UNKNOWN])
def test_unknown_or_completed_never_guesses_failure(status):
    with pytest.raises(ValueError, match="Unsupported runtime history"):
        validate_runtime_history("刚才的回复被截断了。", PreviousTurn(status=status))
    for text in ("刚才的回答没有被截断，我可以继续补充。", "你担心刚才的回答被截断了吗？", "第二点再详细解释。"):
        validate_runtime_history(text, PreviousTurn(status=status))


@pytest.mark.parametrize("text", ["刚才项目失败后，需要补充回复内容。", "上一轮面试失败的内容需要复盘。", "刚才工程项目网络中断，导致实验失败。", "之前订单失败，需要分析原因。"])
def test_normal_domain_failure_discussion_is_not_runtime_history(text):
    validate_runtime_history(text, PreviousTurn(status=TurnStatus.COMPLETED))


def test_user_reported_incomplete_is_feedback_not_transport_diagnosis(workspace):
    turn(workspace, "公开问题", answer(THREE))
    provider, events = turn(workspace, "你刚才好像没说完", answer("可以，我继续补充第二点。"), act="expand_previous")
    assert any(isinstance(event, TurnComplete) for event in events)
    assert provider.requests[-1]["previous_turn"]["status"] == "COMPLETED"
    _, events = turn(workspace, "你刚才好像没说完", answer("刚才系统连接中断了。"))
    assert not any(isinstance(event, TurnComplete) for event in events)


@pytest.mark.parametrize("failure,status", [(ResponseStreamError("output_limit"), "FAILED_TRANSPORT"),
    (ResponseStreamError("transport_incomplete"), "FAILED_TRANSPORT"),
    (ValueError("public synthetic invalid shape"), "FAILED_VALIDATION")])
def test_true_failure_notice_not_semantic_content_and_recovery_truthful(workspace, failure, status):
    turn(workspace, "公开失败练习", failure=failure)
    assert workspace.agent_session.previous_turn().status.value == status
    provider, events = turn(workspace, "可以继续吗", answer("上一条回答未完成，我现在补充说明。"), act="continue_previous")
    assert any(isinstance(event, TurnComplete) for event in events)
    assert provider.requests[0]["previous_turn"]["status"] == status
    assert not any(item["role"] == "assistant" for item in provider.requests[0]["recent_turns"])
    assert "agent_failure" not in json.dumps(provider.requests)
    assert workspace.agent_session.previous_turn().status == TurnStatus.COMPLETED


def test_old_failure_then_success_then_continuation_clears_stale_failure(workspace):
    turn(workspace, "失败练习", failure=ResponseStreamError("output_limit"))
    turn(workspace, "重新说明", answer(THREE))
    provider, events = turn(workspace, "继续", answer("继续协作沟通的例子。"), act="continue_previous")
    assert any(isinstance(event, TurnComplete) for event in events)
    assert provider.requests[-1]["previous_turn"]["status"] == "COMPLETED"
    assert workspace.agent_session.last_error is workspace.agent_session.last_failure is None
    assert FAILURE_TEXT not in json.dumps(provider.requests, ensure_ascii=False)


def test_cancelled_generator_and_pending_switch_have_durable_status(workspace):
    session = workspace.agent_session
    session.provider = ScriptedProvider(response=answer(THREE))
    session.set_consent(granted=True)
    session.queue("公开问题", "typed")
    pending, session.pending = session.pending, None
    iterator = session.stream_turn(pending)
    next(event for event in iterator if isinstance(event, AnswerDelta))
    iterator.close()
    assert session.previous_turn().status == TurnStatus.CANCELLED
    session.queue("未发出的公开问题", "typed")
    old = workspace.thread.thread_id
    fresh = workspace.create_new_thread()
    assert session.previous_turn(old).status == TurnStatus.CANCELLED
    assert session.previous_turn(fresh.thread_id).status == TurnStatus.UNKNOWN
    assert session.pending is session.last_error is session.last_failure is None


def test_failed_persistence_receipt_survives_restart_and_next_success(workspace, monkeypatch):
    turn(workspace, "已完成问题", answer(THREE))
    original = workspace.store.append_turn
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("public synthetic save failure")
    monkeypatch.setattr(workspace.store, "append_turn", fail)
    for _ in range(2):
        turn(workspace, "新问题", answer("这次无法保存。"))
        assert AgentSession(workspace).previous_turn().status == TurnStatus.FAILED_PERSISTENCE
    monkeypatch.setattr(workspace.store, "append_turn", original)
    turn(workspace, "继续", answer("上一条回答未完成，现在继续补充。"))
    assert AgentSession(workspace).previous_turn().status == TurnStatus.COMPLETED
    assert len(workspace.store.list_messages(workspace.owner_scope_id, workspace.thread.thread_id)) == 4


def test_thread_switch_refresh_and_service_restart_preserve_truth(tmp_path):
    owner = str(uuid4())
    with Workspace(owner, tmp_path) as workspace:
        turn(workspace, "公开主题", answer(THREE))
        old = workspace.thread.thread_id
        workspace.create_new_thread()
        assert workspace.agent_session.previous_turn().status == TurnStatus.UNKNOWN
        workspace.activate(old)
        assert workspace.agent_session.previous_turn().status == TurnStatus.COMPLETED
        assert workspace.chat.messages[-1].content == THREE
    with Workspace(owner, tmp_path) as restored:
        restored.activate(old)
        assert restored.agent_session.previous_turn().status == TurnStatus.COMPLETED
        assert restored.chat.messages[-1].content == THREE
        provider, _ = turn(restored, "第二点是什么意思", answer("第二点是协作沟通。"))
        assert provider.requests[0]["previous_turn"]["status"] == "COMPLETED"


def test_lost_receipt_acknowledgement_cannot_erase_committed_answer(workspace, monkeypatch):
    session = workspace.agent_session
    original = session._record_turn
    def fail_completed(pending, status, anchor):
        if status == TurnStatus.COMPLETED:
            raise sqlite3.OperationalError("public synthetic receipt failure")
        original(pending, status, anchor)
    monkeypatch.setattr(session, "_record_turn", fail_completed)
    _, events = turn(workspace, "公开问题", answer(THREE))
    assert any(isinstance(event, TurnComplete) for event in events)
    assert session.last_error is None
    assert AgentSession(workspace).previous_turn().status == TurnStatus.COMPLETED
    assert workspace.chat.messages[-1].content == THREE


def test_initial_status_write_failure_blocks_provider_and_records_storage_failure(workspace, monkeypatch):
    session = workspace.agent_session
    def fail(*args):
        raise sqlite3.OperationalError("public synthetic receipt write failure")
    monkeypatch.setattr(session, "_record_turn", fail)
    provider, events = turn(workspace, "公开问题")
    assert provider.structured_calls == provider.stream_calls == 0
    assert not any(isinstance(event, TurnComplete) for event in events)
    assert AgentSession(workspace).previous_turn().status == TurnStatus.FAILED_PERSISTENCE


def test_legacy_threads_and_existing_consent_are_backward_compatible(workspace):
    store, owner, thread = workspace.store, workspace.owner_scope_id, workspace.thread.thread_id
    store.append_turn(owner, thread, "旧问题", "旧答案没有新状态")
    session = AgentSession(workspace)
    session.set_consent(granted=True)
    assert session.previous_turn().status == TurnStatus.UNKNOWN
    assert AgentSession(workspace).consent
    stored = store.list_messages(owner, thread)
    assert recent_turns(stored)[-1].provenance == "legacy_assistant"
    assert store._connect is not None
    with sqlite3.connect(store.path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
    # Error-looking legacy prose is NOT proof of a transport failure.
    store.append_turn(owner, thread, "旧问题2", FAILURE_TEXT)
    assert session.previous_turn().status == TurnStatus.UNKNOWN


def test_v13b2_completed_metadata_recognized_without_migration(workspace):
    from career_runtime.models import StreamMetrics
    workspace.store.append_turn(workspace.owner_scope_id, workspace.thread.thread_id, "旧问题", THREE,
        assistant_metadata={"agent_stream": StreamMetrics(transport_completed=True, provider_finish_category="normal_stop", core_valid=True, persistence_committed=True).model_dump()})
    assert workspace.agent_session.previous_turn().status == TurnStatus.COMPLETED


@pytest.mark.parametrize("size", [5000, 9500, 10000])
def test_long_previous_answer_keeps_head_all_dimensions_middle_tail_and_budget(workspace, size):
    body = "开场事实\n## 一、产品思维\n用户需求边界\n" + "甲" * (size//3-50) + "\n## 二、协作沟通\n核对需求范围\n" + "乙" * (size//3-50) + "\n## 三、效果验证\n观察实际反馈\n" + "丙" * (size//3-50) + "\n结尾未决问题"
    turn(workspace, "公开长问题", answer(body))
    provider, events = turn(workspace, "展开第二点", answer("核对需求范围属于第二项协作沟通。"), act="refer_to_previous_item")
    assert any(isinstance(event, TurnComplete) for event in events)
    history = provider.requests[-1]["recent_turns"]
    assert len(json.dumps(history, ensure_ascii=False, separators=(",", ":"))) <= MAX_HISTORY_CHARACTERS
    combined = "\n".join(item["text"] for item in history)
    for required in ("开场事实", "产品思维", "协作沟通", "核对需求范围", "效果验证", "结尾未决问题"):
        assert required in combined
    assert any(item["excerpted"] for item in history)
    assert provider.requests[-1]["previous_turn"]["status"] == "COMPLETED"


@pytest.mark.parametrize("text", ["汉字😀\\\"\n"*1800, "无标题段落"*2000])
def test_context_escaping_unicode_and_nonmarkdown_stay_bounded(workspace, text):
    workspace.store.append_turn(workspace.owner_scope_id, workspace.thread.thread_id, "公开问题", text)
    history = recent_turns(workspace.store.list_messages(workspace.owner_scope_id, workspace.thread.thread_id))
    assert len(json.dumps([item.model_dump() for item in history], ensure_ascii=False, separators=(",", ":"))) <= 4500
    assert history[-1].role == "assistant"
    assert history[-1].text
    clipped, flag = excerpt(text, 1600)
    assert flag and len(clipped) <= 1600


def test_old_unrelated_history_falls_out_and_explicit_recent_reference_is_available(workspace):
    for i in range(20):
        workspace.store.append_turn(workspace.owner_scope_id, workspace.thread.thread_id, f"旧问题{i}", f"旧主题{i}")
    turn(workspace, "现在的主题", answer(THREE))
    messages = workspace.store.list_messages(workspace.owner_scope_id, workspace.thread.thread_id, limit=12)
    initial = recent_turns(messages)
    target = initial[0].message_id
    selected = recent_turns(messages, prioritized_ids=[target])
    assert len(selected) <= 6 and target in {item.message_id for item in selected}
    assert all("旧主题0" != item.text for item in selected)
    assert any(item.text == THREE for item in selected)
    with pytest.raises(ValueError):
        workspace.store.list_messages(workspace.owner_scope_id, workspace.thread.thread_id, limit=100)


class DialogueProvider(ScriptedProvider):
    def __init__(self, acts, responses, mode):
        super().__init__([plan(relevance=mode).model_copy(update={"dialogue_act": act}) for act in acts])
        self.responses = list(responses)

    def generate_structured(self, messages, response_model, options, **kwargs):
        payload = json.loads(messages[1].content)
        if self.plans[0].dialogue_act not in {"new_topic", "normal_followup"}:
            ids = [item["message_id"] for item in payload["recent_turns"] if item["role"] == "assistant"]
            self.plans[0] = self.plans[0].model_copy(update={"referenced_message_ids": ids[-1:]})
        return super().generate_structured(messages, response_model, options, **kwargs)

    def stream_structured(self, *args, **kwargs):
        self.response = self.responses.pop(0)
        yield from super().stream_structured(*args, **kwargs)


BACKGROUNDS = ("AI 技术专业学生", "有八年经验的审计从业者", "机械工程师", "市场营销与电商从业者", "设计与 UX 从业者")


def public_dialogue(workspace, background, mode="DIRECT_CAREER"):
    texts = [f"公开合成角色：{background}，帮我拆解产品岗位面试重点。", "把三个维度展开。", "第二个多给几个例子。",
        "那如果我是转行的人呢？", "为什么你认为前面经验能迁移？", "那最大的未知是什么？"]
    responses = [answer(THREE), answer("## 一、产品思维\n需求定位。\n## 二、协作沟通\n澄清、取舍、协调。\n## 三、效果验证\n设计反馈。"),
        answer("第二项协作沟通，例如澄清范围、协调优先级、解释取舍。"), answer(f"依据你当前说明的{background}背景，转行可以先核对可迁移证据。"),
        answer("沿用前面的澄清、取舍与协调经验来讨论迁移，不认定未经证实的能力。"), answer("当前未知是目标岗位所需的直接实践证据，未知不等于已确认缺陷。")]
    provider = DialogueProvider(["new_topic", "expand_previous", "refer_to_previous_item", "normal_followup", "clarify_previous", "normal_followup"], responses, mode)
    session = workspace.agent_session
    session.provider = provider
    session.set_consent(granted=True)
    for i, text in enumerate(texts):
        session.queue(text, "typed")
        pending, session.pending = session.pending, None
        events = list(session.stream_turn(pending))
        assert any(isinstance(event, TurnComplete) for event in events)
        payload = provider.requests[-1]
        assert payload["previous_turn"]["status"] == ("UNKNOWN" if i == 0 else "COMPLETED")
        assert len(payload["recent_turns"]) <= 6
        assert not payload["selected_context"] and not payload["tool_statuses"]
        if i == 2:
            assert "协作沟通" in json.dumps(payload["recent_turns"], ensure_ascii=False)
            assert payload["plan"]["referenced_message_ids"]
        assert len(workspace.chat.messages) == (i+1)*2
        assert not workspace.controller.active_memories()
    assert provider.structured_calls == provider.stream_calls == 6
    return provider


@pytest.mark.parametrize("background", BACKGROUNDS)
def test_six_turn_cross_background_dialogues(workspace, background):
    public_dialogue(workspace, background)


@pytest.mark.parametrize("mode,topic,second", [("GENERAL_QA", "怎么安慰情绪低落的朋友？", "先倾听，不抢着给建议"),
    ("LEARNING_OR_TECHNICAL", "generator 和 iterator 有什么区别？", "生成器通过 yield 保留执行位置")])
def test_four_turn_general_and_technical_reference_chains(workspace, mode, topic, second):
    responses = [answer(f"## 一、概念\n基础说明\n## 二、具体做法\n{second}\n## 三、边界\n按实际需要使用"),
        answer(f"第二点具体做法是：{second}。"), answer("沿用第二点再给一个具体例子。"), answer("把前面的例子整理得更简洁。")]
    provider = DialogueProvider(["new_topic", "clarify_previous", "expand_previous", "normal_followup"], responses, mode)
    session = workspace.agent_session
    session.provider = provider
    session.set_consent(granted=True)
    for text in (topic, "第二点再详细解释一下", "给我一个第二点的代码例子" if mode == "LEARNING_OR_TECHNICAL" else "再给一个例子", "改得简洁一点"):
        session.queue(text, "typed")
        pending, session.pending = session.pending, None
        assert any(isinstance(event, TurnComplete) for event in session.stream_turn(pending))
        assert provider.requests[-1]["plan"]["relevance"] == mode
        assert not provider.requests[-1]["selected_context"]
        assert not provider.requests[-1]["tool_statuses"]
    assert provider.stream_calls == provider.structured_calls == 4


def test_profile_assisted_followup_reuses_owned_same_version_evidence_without_reasking(workspace):
    original = seed(workspace)
    evidence = original.skills[0].evidence_ids[0]
    turn(workspace, "按已有技能讨论发展", answer("已确认技能包括"+original.skills[0].label, citations=[evidence]), mode="DIRECT_CAREER", tools=[request("current_profile", sections=["skills"])])
    provider, events = turn(workspace, "为什么你刚才这么判断？", answer("沿用上轮已核对的技能证据继续解释。", citations=[evidence]), mode="DIRECT_CAREER", act="clarify_previous")
    assert any(isinstance(event, TurnComplete) for event in events)
    assert provider.requests[-1]["conversation_citations"] == [evidence]
    assert not provider.requests[-1]["tool_statuses"]
    assert original.skills[0].label in json.dumps(provider.requests[-1]["recent_turns"], ensure_ascii=False)
    assert workspace.memory_service.get_current_confirmed_profile(workspace.subject_id) == original
    assert not workspace.controller.active_memories()
    assert "agent_profile_stamp" in workspace.store.list_messages(workspace.owner_scope_id, workspace.thread.thread_id)[-1].metadata


def test_changed_profile_and_new_topic_cannot_reuse_stale_evidence(workspace):
    original = seed(workspace)
    ref = original.skills[0].evidence_ids[0]
    turn(workspace, "核对技能", answer("已核对技能。", citations=[ref]), mode="DIRECT_CAREER", tools=[request("current_profile", sections=["skills"])])
    provider, _ = turn(workspace, "新问题", answer(), mode="GENERAL_QA", act="new_topic")
    assert not provider.requests[-1]["conversation_citations"]
    workspace.memory_service.save_confirmed_profile(workspace.subject_id, original.model_copy(update={"version": original.version+1}))
    provider, events = turn(workspace, "继续技能", answer("旧版本不能冒充当前证据。", citations=[ref]), mode="DIRECT_CAREER", act="continue_previous")
    assert not provider.requests[-1]["conversation_citations"]
    assert not any(isinstance(event, TurnComplete) for event in events)


def test_unknown_message_reference_fails_before_tools_or_response(workspace):
    provider = ScriptedProvider([plan().model_copy(update={"dialogue_act": "refer_to_previous_item", "referenced_message_ids": ["foreign_message"]})])
    session = workspace.agent_session
    session.provider = provider
    session.set_consent(granted=True)
    session.queue("这个", "typed")
    pending, session.pending = session.pending, None
    assert not any(isinstance(event, TurnComplete) for event in session.stream_turn(pending))
    assert provider.structured_calls == 1 and provider.stream_calls == 0


def test_profile_change_during_stream_cannot_stamp_old_evidence_as_new_version(workspace):
    original = seed(workspace)
    ref = original.skills[0].evidence_ids[0]
    class Changed(ScriptedProvider):
        def stream_structured(self, *args, **kwargs):
            workspace.memory_service.save_confirmed_profile(workspace.subject_id, original.model_copy(update={"version": original.version+1}))
            yield from super().stream_structured(*args, **kwargs)
    provider = Changed([plan(relevance="DIRECT_CAREER", tools=[request("current_profile", sections=["skills"])])], answer("本轮读取时的技能证据。", citations=[ref]))
    session = workspace.agent_session
    session.provider = provider
    session.set_consent(granted=True)
    session.queue("核对技能", "typed")
    pending, session.pending = session.pending, None
    list(session.stream_turn(pending))
    stored = workspace.store.list_messages(workspace.owner_scope_id, workspace.thread.thread_id)
    assert "agent_profile_stamp" not in stored[-1].metadata


def test_owner_isolation_and_closed_receipt_no_content_or_reasoning(workspace):
    turn(workspace, "公开标记OWNER_ONLY", answer(THREE))
    with Workspace(str(uuid4()), workspace.root) as other:
        assert other.agent_session.previous_turn().status == TurnStatus.UNKNOWN
        provider, _ = turn(other, "继续", answer("请说明希望继续哪个话题。"))
        assert "OWNER_ONLY" not in json.dumps(provider.requests)
        assert not provider.requests[0]["recent_turns"]
    with sqlite3.connect(workspace.agent_session.path) as db:
        names = [row[1] for row in db.execute("PRAGMA table_info(turn_receipts)")]
        assert set(names) == {"owner", "thread_id", "turn_id", "status", "previous_assistant_id"}
        assert "OWNER_ONLY" not in repr(db.execute("SELECT * FROM turn_receipts").fetchall())


def test_universal_prompts_and_contract_not_biography_or_keyword_router():
    root = Path(__file__).resolve().parents[1]
    prompts = "\n".join((root/"career_runtime/prompts"/name).read_text() for name in ("planner_v1.md", "planner_repair_v1.md", "response_v1.md"))
    for assumption in ("用户是 AI 学生", "用户就读 CityU", "用户正在寻找实习", "用户只有项目没有工作经验", "用户会 Python"):
        assert assumption not in prompts
    assert "任意专业、行业、教育程度和职业阶段" in prompts
    assert "previous_turn" in prompts and "COMPLETED" in prompts
    code = (root/"career_runtime/context.py").read_text() + (root/"career_runtime/engine.py").read_text()
    assert 'if "继续" in' not in code and '== "继续"' not in code
    from career_runtime.planning import public_contract
    assert {"dialogue_act", "referenced_message_ids"} <= set(public_contract()["required_plan_fields"])


def test_audit_to_business_analysis_chain_retains_current_user_facts(workspace):
    texts = ("公开合成：我有八年审计经验，考虑转商业分析。", "为什么你认为我的经验能迁移？", "那我最大的缺口是什么？", "第二个例子再说明一下")
    responses = [answer("你提到八年审计经验。可讨论证据核查、流程分析和利益相关方沟通，不直接认定商业分析能力。"),
        answer("沿用审计背景：第一是证据核查，第二是流程分析；是否迁移仍需岗位实践验证。"),
        answer("当前没有商业分析端到端实践的证据，这是未知，不是已确认能力缺陷。"),
        answer("第二项流程分析可以用公开流程图例子说明，不需要重新询问你的背景。")]
    provider = DialogueProvider(["new_topic", "clarify_previous", "normal_followup", "refer_to_previous_item"], responses, "DIRECT_CAREER")
    session = workspace.agent_session
    session.provider = provider
    session.set_consent(granted=True)
    for index, text in enumerate(texts):
        session.queue(text, "typed")
        pending, session.pending = session.pending, None
        assert any(isinstance(event, TurnComplete) for event in session.stream_turn(pending))
        if index:
            assert "审计" in json.dumps(provider.requests[-1]["recent_turns"], ensure_ascii=False)
        assert not provider.requests[-1]["tool_statuses"]
    assert len(workspace.chat.messages) == 8
    assert workspace.memory_service.get_current_confirmed_profile(workspace.subject_id) is None


@pytest.mark.parametrize("theme", ["跟随系统", "浅色模式", "深色模式"])
def test_ui_three_turn_continuity_survives_rerun_without_extra_calls(tmp_path, theme):
    from tests.test_chat_product import app, WORKSPACE_KEY
    value = app(tmp_path, str(uuid4()))
    workspace = value.session_state[WORKSPACE_KEY]
    try:
        provider = DialogueProvider(["new_topic", "expand_previous", "refer_to_previous_item"],
            [answer(THREE), answer(THREE + "\n第二维度需要具体澄清需求。"), answer("第二维度的例子是协调优先级。")], "DIRECT_CAREER")
        workspace.agent_session.provider_factory = lambda: provider
        value.button(key="orange_agent_consent").click().run()
        value.radio(key="orange_appearance").set_value(theme).run()
        for index, text in enumerate(("产品岗位面试重点", "三个维度展开", "第二维度给个例子")):
            value.chat_input[0].set_value(text).run(timeout=30)
            assert not value.exception and len(value.chat_message) == (index+1)*2
            assert workspace.agent_session.previous_turn().status == TurnStatus.COMPLETED
            value.run(timeout=30)
            assert provider.structured_calls == provider.stream_calls == index+1
        assert len(value.chat_input) == 1
        assert value.radio(key="orange_appearance").options == ["跟随系统", "浅色模式", "深色模式"]
    finally:
        workspace.close()


def test_status_metadata_rejects_unknown_fields_contradiction_and_secret_ids(workspace):
    for meta in ({"agent_turn_status": "made_up"}, {"agent_turn_status": "COMPLETED", "agent_failure": {"category":"runtime_failure","stage":"context","reason":"execution_error","latency_ms":0}},
        {"agent_profile_stamp":{"profile_id":"sk-"+"A"*25,"version":1}}, {"agent_profile_stamp":{"profile_id":"public","version":1,"reasoning":"hidden"}}):
        with pytest.raises(ValueError):
            workspace.store.append_turn(workspace.owner_scope_id, workspace.thread.thread_id, "问题", "回答", assistant_metadata=meta)
    assert not workspace.chat.messages
