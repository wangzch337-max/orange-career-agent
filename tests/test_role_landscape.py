"""Public-only grounding, authority, reference and lifecycle regression tests."""

from dataclasses import asdict
import json
import socket
from threading import Event, Thread
from uuid import uuid4
import pytest
from role_landscape.models import Dimension, Status, Authority
from role_landscape.service import RoleLandscapeService, NOTICE
from role_landscape.sources import RoleLandscapeRegistry, SOURCE_PATH
from career_reality.sources import direction_id
from tests.career_discovery_doubles import prepared
from tests.test_career_reality import open_reality

DIRECTIONS = ("Business Analysis", "Knowledge Operations", "Process Improvement")
OLD_ROLES = ("AI Product Intern", "AI Application Engineer", "Data Analyst")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def blocked(*a, **k):
        pytest.fail("D.3 forbids network/config/live providers")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr("providers.models.load_llm_settings", blocked)
    monkeypatch.setattr("resume_evidence.session._qwen_provider", blocked)


@pytest.fixture
def h(tmp_path):
    harness = prepared(tmp_path)
    yield harness
    harness.close()


def opened(h, title="Business Analysis"):
    open_reality(h, title)
    session = h.workspace.role_landscape
    assert session.submit("这个方向有哪些岗位？") and session.current()
    return session


@pytest.mark.parametrize("title", DIRECTIONS)
def test_exact_membership_three_directions_not_old_jobs(title):
    registry = RoleLandscapeRegistry()
    source = registry.resolve(title, title, direction_id(title, title))
    assert source is not None and len(source.roles) == 3
    assert {r.role_id for r in source.roles} == {m.role_id for m in source.memberships}
    assert all(m.evidence and "本合成资料" in m.evidence for m in source.memberships)
    assert not any(name in source.model_dump_json() for name in OLD_ROLES)
    assert "顺序" in NOTICE and "不是排名" in NOTICE
    assert registry.resolve(title + "s", title, direction_id(title + "s", title)) is None
    with pytest.raises(ValueError): registry.resolve(title, title, "direction_bad")


@pytest.mark.parametrize("mutation", ["missing_membership", "wrong_membership", "duplicate_link", "duplicate_role", "duplicate_source", "duplicate_direction", "duplicate_alias", "provenance", "status", "type", "unsafe", "extra", "too_few", "too_many"])
def test_invalid_source_rejected_without_repair(tmp_path, mutation):
    data = json.loads(SOURCE_PATH.read_text())
    source = data["records"][0]
    if mutation == "missing_membership": source["memberships"].pop()
    if mutation == "wrong_membership": source["memberships"][0]["role_id"] = "role_unrelated"
    if mutation == "duplicate_link": source["memberships"][1] = source["memberships"][0]
    if mutation == "duplicate_role": source["roles"][1] = source["roles"][0]
    if mutation == "duplicate_source": data["records"].append(source)
    if mutation == "duplicate_direction": data["records"][1]["direction_identity"] = source["direction_identity"]
    if mutation == "duplicate_alias": source["roles"][1]["reference_aliases"] = source["roles"][0]["reference_aliases"]
    if mutation == "provenance": source["provenance"] = "real_market_taxonomy"
    if mutation == "status": source["status"] = "unapproved"
    if mutation == "type": source["source_type"] = "live_jobs"
    if mutation == "unsafe": source["roles"][0]["primary_problem"] = "你适合这个岗位"
    if mutation == "extra": source["roles"][0]["ranking"] = 1
    if mutation == "too_few": source["roles"] = source["roles"][:1]
    if mutation == "too_many": source["roles"] *= 2
    path = tmp_path / "public_sources.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError): RoleLandscapeRegistry(path).inventory()


@pytest.mark.parametrize("dimension", list(Dimension))
def test_every_claim_owned_by_role_source_and_membership(dimension):
    service = RoleLandscapeService()
    for source in RoleLandscapeRegistry().inventory().records:
        reply = service.reply(source, dimension)
        assert service.validate(reply, source) == reply
        assert reply.role_ids == tuple(r.role_id for r in source.roles)
        for b in reply.blocks:
            assert b.membership_ref == f"{source.source_id}@{source.version}:memberships:{b.role_id}"
            assert b.source_ref.startswith(f"{source.source_id}@{source.version}:roles:{b.role_id}:")
            assert b.authority in (Authority.SOURCE_FACT, Authority.EXAMPLE, Authority.UNKNOWN)
        if dimension == Dimension.OVERVIEW:
            assert {b.field for b in reply.blocks} == {"primary_problem", "work_emphasis", "distinction"}


@pytest.mark.parametrize("mutation", ["text", "role", "ref", "membership", "authority", "version", "source", "duplicate", "order"])
def test_reply_cannot_invent_reassign_or_repair(mutation):
    source = RoleLandscapeRegistry().inventory().records[0]
    service = RoleLandscapeService()
    reply = service.reply(source, Dimension.OVERVIEW)
    b = reply.blocks[0]
    changes = {"text": {"text":"invented work"}, "role":{"role_id":"role_other"},
               "ref":{"source_ref":"unrelated"}, "membership":{"membership_ref":"unrelated"},
               "authority":{"authority":Authority.EXPLANATION}}
    if mutation in changes:
        reply = reply.model_copy(update={"blocks":(b.model_copy(update=changes[mutation]), *reply.blocks[1:])})
    if mutation == "version": reply = reply.model_copy(update={"source_version":99})
    if mutation == "source": reply = reply.model_copy(update={"source_id":"landscape_other"})
    if mutation == "duplicate": reply = reply.model_copy(update={"blocks":(*reply.blocks, b)})
    if mutation == "order": reply = reply.model_copy(update={"blocks":tuple(reversed(reply.blocks))})
    with pytest.raises(ValueError): service.validate(reply, source)


@pytest.mark.parametrize("question", ["Python decorator 是什么？", "Transformer 平时做什么？", "如何分析数据？", "岗位是什么意思？", "这个方向的 Python decorator 是什么？", "第一种主要做什么？另外介绍 Python。"])
def test_unrelated_or_mixed_qa_not_taken(h, question):
    session = opened(h)
    before = session.messages[:]
    assert not session.submit(question)
    assert session.messages == before


@pytest.mark.parametrize("question,dimension,count", [
    ("第一种主要做什么？",Dimension.WORK,1),
    ("第二种和第一种有什么区别？",Dimension.COMPARISON,2),
    ("刚才偏系统的那个呢？",Dimension.TECHNICAL,1),
    ("第二种是不是更偏技术？",Dimension.TECHNICAL,1),
    ("刚才第二种角色平时和谁合作？",Dimension.COLLABORATION,1),
    ("哪个更偏沟通？",Dimension.COLLABORATION,3),
    ("哪个更靠近系统落地？",Dimension.TECHNICAL,3),
    ("第一种的工作成果是什么？",Dimension.OUTPUTS,1),
])
def test_natural_bounded_followups_current_roles(h, question, dimension, count):
    session = opened(h)
    assert session.submit(question)
    reply = session.messages[-1].reply
    assert reply and reply.dimension == dimension and len(reply.role_ids) == count
    assert session.service.validate(reply, session.source)


def test_ambiguous_reference_and_unknown_id_no_guess(h):
    session = opened(h)
    for question in ("这两种有什么区别？", "第四种主要做什么？", "role_bad 平时做什么？", "role_ko_curation 平时做什么？"):
        assert session.submit(question) and session.messages[-1].reply is None
        assert "没有猜测或替换" in session.messages[-1].text
    assert session.submit("第一种和第二种有什么区别？")
    assert session.submit("这两种有什么区别？")
    assert session.messages[-1].reply.role_ids == session.binding.displayed_role_ids[:2]


@pytest.mark.parametrize("title", DIRECTIONS)
def test_zero_authority_change_no_memory_or_role_profile_facts(h, monkeypatch, title):
    open_reality(h, title)
    w, session = h.workspace, h.workspace.role_landscape
    before = h.current(), h.memories(), h.history()
    def forbidden(*a, **k): pytest.fail("No D.3 retrieval/write/job tool")
    for name in ("retrieve_context", "create_candidate", "create_confirmed", "supersede", "save_confirmed_profile"):
        monkeypatch.setattr(w.memory_service, name, forbidden)
    monkeypatch.setattr(w.memory_service.memory_store, "get", forbidden)
    monkeypatch.setattr("career_runtime.tools.ToolRegistry.execute", forbidden)
    assert session.submit("这个方向有哪些岗位？")
    for text in ("第二种比较有意思", "第一种主要做什么？", "那你觉得哪个更适合我？", "还有其他类型吗？", "具体有哪些招聘职位"):
        assert session.submit(text)
    assert session.messages[-1].reply is None
    assert before == (h.current(), h.memories(), h.history())
    assert not w.chat.messages and not w.store.list_messages(w.owner_scope_id, w.thread.thread_id)
    assert "role_landscape" not in json.dumps(w._snapshot())
    assert not w.controller.state or not w.controller.state.get("match_results")
    events = json.dumps([asdict(e) for e in session.events], ensure_ascii=False)
    assert all(text not in events for text in ("第二种", session.source.roles[0].primary_problem, h.scenario.goal_label))


def test_general_qa_reload_preserves_independent_binding(h):
    session = opened(h)
    stamp = session.binding
    assert not session.submit("Python decorator 是什么？")
    h.workspace.career_discovery.invalidate()
    h.workspace.reload_completed_turn(h.workspace.thread.thread_id)
    assert session.current() and session.binding == stamp
    assert session.submit("刚才第二种角色平时和谁合作？")


@pytest.mark.parametrize("operation", ["new", "switch", "delete", "close", "resume", "profile", "owner", "parent", "source_version", "source_bytes"])
def test_lifecycle_rejects_old_reference(h, tmp_path, operation):
    session = opened(h)
    token, w = session.token(), h.workspace
    if operation == "new": w.create_new_thread()
    if operation == "switch": w.activate(w.thread.thread_id)
    if operation == "delete": w.delete_thread(w.thread.thread_id)
    if operation == "close": w.close()
    if operation == "resume": w.resume_intake.clear()
    if operation == "profile":
        current = w.memory_service.get_current_confirmed_profile
        w.memory_service.get_current_confirmed_profile = lambda s: current(s).model_copy(update={"version":999})
    if operation == "owner": w.owner_scope_id = str(uuid4())
    if operation == "parent": w.career_reality.invalidate()
    if operation.startswith("source_"):
        data = json.loads(SOURCE_PATH.read_text())
        if operation == "source_version": data["records"][0]["version"] += 1
        else: data["records"][0]["roles"][0]["primary_problem"] = "changed public source"
        path = tmp_path / "changed_public_source.json"; path.write_text(json.dumps(data))
        session.registry = RoleLandscapeRegistry(path)
    assert not session.current() and not session.messages
    assert session.submit("第一种主要做什么？", token=token)
    assert not session.messages and session.binding is None


@pytest.mark.parametrize("operation", ["new", "delete", "close"])
def test_late_reply_does_not_resurrect(h, operation):
    session = opened(h)
    entered, release = Event(), Event()
    original = session.service.reply
    def delayed(*a, **k):
        entered.set()
        assert release.wait(5)
        return original(*a, **k)
    session.service.reply = delayed
    thread = Thread(target=session.submit, args=("第一种主要做什么？",))
    thread.start(); assert entered.wait(5)
    if operation == "new": h.workspace.create_new_thread()
    if operation == "delete": h.workspace.delete_thread(h.workspace.thread.thread_id)
    if operation == "close": h.workspace.close()
    release.set(); thread.join(5)
    assert not thread.is_alive() and not session.messages and session.binding is None


def test_replay_rejected_and_qa_does_not_spend_turn(h):
    session = opened(h)
    token = session.token()
    assert not session.submit("Python decorator 是什么？") and session.turns == 1
    assert session.submit("第一种主要做什么？", token=token)
    before = session.messages[:]
    assert session.submit("第一种主要做什么？", token=token) and session.messages == before


@pytest.mark.parametrize("issue", ["no_parent", "missing", "invalid", "other_direction"])
def test_unsupported_never_generic_job_fallback(h, tmp_path, issue):
    w, session = h.workspace, h.workspace.role_landscape
    if issue != "no_parent": open_reality(h)
    if issue in ("missing", "invalid"):
        data = json.loads(SOURCE_PATH.read_text())
        if issue == "missing": data["records"].pop(0)
        else: data["records"][0]["memberships"].pop()
        path = tmp_path / "public_source.json"; path.write_text(json.dumps(data))
        session.registry = RoleLandscapeRegistry(path)
    question = "Knowledge Operations有哪些岗位？" if issue == "other_direction" else "这个方向有哪些岗位？"
    assert session.submit(question)
    assert session.messages[-1].reply is None and "没有换成其他岗位" in session.messages[-1].text
    assert not w.chat.messages


def test_credential_and_turn_budget_safety(h):
    session = opened(h)
    before = session.messages[:]
    assert not session.submit("x" * 2001)
    assert session.submit("role_bad sk-" + "a1B2c3D4" * 4)
    assert session.messages == before
    for _ in range(16): session.submit("第一种主要做什么？")
    assert session.status == Status.LIMIT_REACHED and session.turns == 16
    assert len(session.messages) <= 40 and len(session.events) <= 40


def test_invalid_service_output_discarded_no_repair(h):
    session = opened(h)
    original = session.service.reply
    session.service.reply = lambda *a, **k: original(*a, **k).model_copy(update={"source_version":999})
    assert session.submit("第一种主要做什么？")
    assert session.status == Status.INVALID and session.messages[-1].reply is None
