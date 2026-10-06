"""Source/authority/lifecycle coverage using public synthetic owned workspaces."""

from dataclasses import asdict
from pathlib import Path
from threading import Event, Thread
from uuid import uuid4
import json
import pytest

from career_background_evaluation.harness import CapturingFake
from career_reality.models import Authority, Dimension, Status
from career_reality.service import CareerRealityService, followup_dimension
from career_reality.sources import CareerRealitySourceRegistry, SOURCE_PATH, direction_id
from tests.career_discovery_doubles import prepared, proposal_from_payload


@pytest.fixture
def h(tmp_path, monkeypatch):
    monkeypatch.setattr("providers.models.load_llm_settings", lambda *a: pytest.fail("No credentials"))
    monkeypatch.setattr("resume_evidence.session._qwen_provider", lambda: pytest.fail("No Qwen"))
    value = prepared(tmp_path)
    yield value
    value.close()


def select(h, title="Business Analysis", *, family=None):
    def proposal(payload):
        raw = proposal_from_payload(payload, titles=(title,))
        raw["directions"][0]["direction_family"] = family or title
        return raw
    discovery = h.workspace.career_discovery
    discovery.provider_factory = lambda: CapturingFake(proposal)
    result = discovery.start(explicitly_requested=True, consent=True, current_statement="探索相邻方向")
    token, selected = discovery.token(), result.directions[0].direction_id
    assert discovery.select(token, selected)
    return token, selected


def open_reality(h, title="Business Analysis"):
    token, selected = select(h, title)
    assert h.workspace.career_reality.start(token, selected)
    return h.workspace.career_reality


def test_exact_resolution_not_fuzzy_or_job_fallback():
    registry = CareerRealitySourceRegistry()
    for source in registry.inventory().records:
        for item in source.identities:
            assert registry.resolve(item.family, item.title, direction_id(item.family, item.title)) == source
    assert registry.resolve("Business Analyses", "Business Analyses", direction_id("Business Analyses", "Business Analyses")) is None
    assert registry.resolve("Other Family", "Business Analysis", direction_id("Other Family", "Business Analysis")) is None
    with pytest.raises(ValueError):
        registry.resolve("Business Analysis", "Business Analysis", "direction_unknown")


@pytest.mark.parametrize("mutation", ["provenance", "type", "duplicate_source", "duplicate_identity", "unsafe", "extra"])
def test_invalid_source_inventory_rejected(tmp_path, mutation):
    data = json.loads(SOURCE_PATH.read_text())
    record = data["records"][0]
    if mutation == "provenance": record["provenance"] = "real_company_survey"
    if mutation == "type": record["source_type"] = "live_job"
    if mutation == "duplicate_source": data["records"].append(record)
    if mutation == "duplicate_identity": record["identities"].append(record["identities"][0])
    if mutation == "unsafe": record["purpose"] = "你适合这个方向"
    if mutation == "extra": record["fit_score"] = 99
    path = tmp_path / "public_sources.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError): CareerRealitySourceRegistry(path).inventory()


@pytest.mark.parametrize("mutation", ["ref", "text", "authority", "source", "situation", "duplicate"])
def test_reply_strict_source_ownership_and_no_repair(mutation):
    source = CareerRealitySourceRegistry().inventory().records[0]
    service = CareerRealityService()
    reply = service.reply(source, Dimension.WORK)
    block = reply.blocks[0]
    if mutation == "ref": block = block.model_copy(update={"source_ref":"unrelated"})
    if mutation == "text": block = block.model_copy(update={"text":"你缺少高级分析能力"})
    if mutation == "authority": block = block.model_copy(update={"authority":Authority.EXPLANATION})
    reply = reply.model_copy(update={"blocks":(block, *reply.blocks[1:])})
    if mutation == "source": reply = reply.model_copy(update={"source_id":"reality_other"})
    if mutation == "situation": reply = reply.model_copy(update={"situation_id":"other"})
    if mutation == "duplicate": reply = reply.model_copy(update={"blocks":(*reply.blocks, block)})
    with pytest.raises(ValueError): service.validate(reply, source)


@pytest.mark.parametrize("dimension", list(Dimension))
def test_each_dimension_is_bounded_exact_source_projection(dimension):
    service = CareerRealityService()
    for source in CareerRealitySourceRegistry().inventory().records:
        reply = service.reply(source, dimension)
        assert service.validate(reply, source) == reply
        assert len(reply.model_dump_json()) < 9000
        assert {b.authority for b in reply.blocks} <= {Authority.SOURCE_FACT, Authority.EXAMPLE, Authority.UNKNOWN}


def test_d2_has_zero_memory_access_writes_provider_or_match(h, monkeypatch):
    before = h.current(), h.memories(), h.history()
    token, selected = select(h)
    for name in ("retrieve_context", "create_confirmed", "create_candidate", "supersede", "save_confirmed_profile"):
        monkeypatch.setattr(h.workspace.memory_service, name, lambda *a, **k: pytest.fail("No D.2 Memory/write"))
    monkeypatch.setattr(h.workspace.memory_service.memory_store, "get", lambda *a: pytest.fail("No D.2 Memory reads"))
    session = h.workspace.career_reality
    assert session.start(token, selected)
    for question in ("平时主要做什么？", "需要哪些能力？", "这个方向适合我吗？"):
        assert session.submit(question)
    assert session.messages[-1].reply is None and "未知" in session.messages[-1].text
    assert before == (h.current(), h.memories(), h.history())
    assert not h.workspace.store.list_messages(h.workspace.owner_scope_id, h.workspace.thread.thread_id)
    assert not h.workspace.controller.state or not h.workspace.controller.state.get("match_results")


def test_general_qa_interrupts_without_losing_owned_work_context(h):
    session = open_reality(h)
    stamp = session.binding
    assert not session.submit("Transformer 的 attention 是什么？")
    assert not session.submit("这个方向的 Transformer attention 是什么？")
    h.workspace.career_discovery.invalidate()  # Existing QA queue clears D.1.
    h.workspace.reload_completed_turn(h.workspace.thread.thread_id)
    assert session.current() and session.binding == stamp
    assert session.submit("那刚才那个方向平时跟谁合作？")
    assert session.messages[-1].reply.dimension == Dimension.COLLABORATION


@pytest.mark.parametrize("question,dimension", [
    ("主要解决什么问题？",Dimension.PURPOSE), ("一天大概怎么工作？",Dimension.WORK),
    ("通常跟谁合作？",Dimension.COLLABORATION), ("工作成果是什么？",Dimension.IO),
    ("工作方式是什么？",Dimension.STYLE), ("技术含量高吗？",Dimension.CAPABILITIES),
    ("这个方向里面有没有不同路线？",Dimension.VARIATIONS), ("还有什么不确定？",Dimension.UNKNOWN),
    ("还有别的工作情境吗？",Dimension.SITUATION),
])
def test_free_followup_is_not_a_fixed_menu(h, question, dimension):
    session = open_reality(h)
    assert session.submit(question)
    assert session.messages[-1].reply.dimension == dimension


@pytest.mark.parametrize("question", ["Python 是什么？", "解释一下协作算法", "如何分析数据？", "需要哪些能力？另外说说 Transformer。"])
def test_no_simple_keyword_takeover(question):
    assert followup_dimension(question) is None


def test_second_situation_then_unknown_never_invents(h):
    session = open_reality(h)
    assert session.submit("再举一个例子")
    assert session.messages[-1].reply.situation_id == "metric_disagreement"
    assert session.submit("还有别的例子吗？")
    assert session.messages[-1].reply is None and "不补造" in session.messages[-1].text
    assert session.situation_index == 1


def test_unsupported_identity_no_substitution(h):
    token, selected = select(h, "Audit Practice")
    session = h.workspace.career_reality
    assert not session.start(token, selected)
    assert session.status == Status.UNSUPPORTED and session.source is None
    assert "没有换成其他方向" in session.messages[-1].text


@pytest.mark.parametrize("operation", ["new", "switch", "delete", "close", "resume_clear", "profile", "owner", "source"])
def test_lifecycle_invalidates_context_and_old_chips(h, operation, tmp_path):
    session = open_reality(h)
    token = session.token()
    w, thread = h.workspace, h.workspace.thread.thread_id
    if operation == "new": w.create_new_thread()
    elif operation == "switch":
        w.activate(thread)
    elif operation == "delete": w.delete_thread(thread)
    elif operation == "close": w.close()
    elif operation == "resume_clear": w.resume_intake.clear()
    elif operation == "profile":
        current = w.memory_service.get_current_confirmed_profile
        w.memory_service.get_current_confirmed_profile = lambda subject: current(subject).model_copy(update={"version":999})
    elif operation == "owner": w.owner_scope_id = str(uuid4())
    elif operation == "source":
        data = json.loads(SOURCE_PATH.read_text())
        data["records"][0]["version"] = 2
        path = tmp_path / "changed_public_source.json"; path.write_text(json.dumps(data))
        session.registry = CareerRealitySourceRegistry(path)
    assert not session.current()
    assert session.submit("平时主要做什么？", token=token)
    assert not session.messages


@pytest.mark.parametrize("mutation", ["owner", "thread", "request", "id", "stale"])
def test_invalid_selection_never_opens(h, mutation):
    token, selected = select(h)
    if mutation == "owner": token = token.model_copy(update={"owner_scope_id":"other"})
    if mutation == "thread": token = token.model_copy(update={"conversation_id":"other"})
    if mutation == "request": token = token.model_copy(update={"request_id":"other"})
    if mutation == "id": selected = "direction_unknown"
    if mutation == "stale": h.workspace.career_discovery.invalidate()
    session = h.workspace.career_reality
    assert not session.start(token, selected)
    assert session.source is None


def test_duplicate_selection_no_replay_and_old_selection_cannot_resurrect(h):
    token, selected = select(h)
    session = h.workspace.career_reality
    assert session.start(token, selected)
    messages = session.messages[:]
    assert session.start(token, selected) and session.messages == messages
    session.invalidate()
    assert not session.start(token, selected) and not session.messages


def test_duplicate_followup_chip_cannot_replay_old_context(h):
    session = open_reality(h)
    token = session.token()
    assert session.submit("通常跟谁合作？", token=token)
    before = session.messages[:]
    assert session.submit("通常跟谁合作？", token=token)
    assert session.messages == before and session.turns == 1


def test_question_budget_and_credentials_rejected_without_echo(h):
    session = open_reality(h)
    before = session.messages[:]
    for value in (None, 1, "x" * 2001, "关于刚才的工作情境，sk-" + "A1b2C3d4" * 4):
        assert session.submit(value)
        assert session.messages == before


def test_late_result_does_not_resurrect_deleted_conversation(h):
    session = h.workspace.career_reality
    token, selected = select(h)
    entered, release = Event(), Event()
    original = session.service.reply
    def delayed(*args, **kwargs):
        entered.set(); assert release.wait(3)
        return original(*args, **kwargs)
    session.service.reply = delayed
    worker = Thread(target=session.start, args=(token, selected))
    worker.start(); assert entered.wait(3)
    try:
        h.workspace.delete_thread(h.workspace.thread.thread_id)
    finally:
        release.set(); worker.join(3)
    assert not worker.is_alive() and not session.messages and session.binding is None


def test_bounded_followups_and_safe_events_no_persistence(h):
    session = open_reality(h)
    for _ in range(20): session.submit("平时主要做什么？")
    assert session.turns == 16 and session.status == Status.LIMIT_REACHED
    assert len(session.messages) <= 40 and len(session.events) <= 40
    serialized = json.dumps([asdict(e) for e in session.events])
    assert not any(text in serialized for text in ("平时主要做什么", "工单", "Business Analysis"))
    assert "career_reality" not in json.dumps(h.workspace._snapshot())


def test_public_source_and_readonly_dependency_boundary():
    import ast
    root = Path(__file__).resolve().parents[1]
    forbidden = {"QwenProvider", "load_llm_settings", "load_dotenv", "requests", "httpx", "socket",
        "MockJobDataProvider", "MatchResult", "save_confirmed_profile", "create_confirmed", "create_candidate", "supersede", "retrieve_context"}
    for path in (root / "career_reality").glob("*.py"):
        text = path.read_text(); tree = ast.parse(text)
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert not names & forbidden
        assert ".env.local" not in text
