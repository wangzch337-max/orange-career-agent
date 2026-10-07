"""Public-only exact source, bounded routing, authority and D.4 lifecycle tests."""

from dataclasses import asdict, replace
import json
from pathlib import Path
from threading import Event, Thread
from uuid import uuid4
import pytest
from specific_role.models import Dimension, Authority, Status, Inventory
from specific_role.sources import SOURCE_PATH, SpecificRoleRegistry
from specific_role.service import SpecificRoleService, classify, reference_id
from career_reality.models import Dimension as RealityDimension
from career_reality.service import followup_dimension
from tests.test_role_landscape import h, offline, opened, DIRECTIONS, OLD_ROLES

COVERAGE = [(title, index) for title in DIRECTIONS for index in range(3)]


def expanded(h, title=DIRECTIONS[0], index=0):
    opened(h, title)
    s = h.workspace.specific_role
    assert s.submit(f"详细讲讲第{index + 1}种角色") and s.current()
    return s


@pytest.mark.parametrize("title,index", COVERAGE)
def test_all_nine_exact_independent_memberships_progressive_information_increment(h, title, index):
    s = expanded(h, title, index)
    parent = h.workspace.role_landscape
    role = parent.source.roles[index]
    source, reply = s.source, s.messages[-1].reply
    assert source.parent_archetype_id == role.role_id == reply.archetype_id
    assert source.parent_direction_id == parent.binding.direction_id
    assert source.membership.direction_archetype_evidence and source.membership.archetype_role_evidence
    assert source.provenance == "independently_authored_fictional_specific_role"
    assert len(reply.blocks) == 2 and {b.field for b in reply.blocks} == {"purpose", "work_situations"}
    assert not {"inputs", "outputs", "work_rhythm", "decision_scope"} & {b.field for b in reply.blocks}
    assert all(v not in source.model_dump_json() for v in OLD_ROLES)
    # Concrete input/output, decision/escalation, rhythm and tool-depth facts
    # are independent additions, not expanded or copied D.3 prose.
    for name in ("decision_scope", "inputs", "outputs", "work_rhythm", "technical_involvement", "work_situations"):
        assert getattr(source, name)
        assert all(text not in role.model_dump_json() for text in getattr(source, name))
    assert s.binding.discovery_request_id == h.workspace.career_reality.binding.discovery_request_id
    assert s.binding.reality_generation == h.workspace.career_reality.generation
    assert s.binding.landscape_generation == parent.generation


@pytest.mark.parametrize("dimension", list(Dimension))
def test_all_dimensions_exact_field_and_membership_ownership(dimension):
    service = SpecificRoleService()
    for source in SpecificRoleRegistry().inventory().records:
        reply = service.reply(source, dimension)
        assert service.validate(reply, source) == reply
        for block in reply.blocks:
            field, index = block.source_ref.rsplit(":", 2)[-2:]
            value = getattr(source, field)
            assert block.text == (value[int(index)] if isinstance(value, tuple) else value)
            assert block.source_ref.startswith(f"{source.source_id}@1:{source.representative_role_id}:")
            assert len(block.membership_refs) == 2 and all(ref.startswith(f"{source.source_id}@1:membership:") for ref in block.membership_refs)
            if dimension == Dimension.UNKNOWN:
                assert block.authority == Authority.UNKNOWN


@pytest.mark.parametrize("mutation", ["membership", "direction", "archetype", "role", "parent", "version", "provenance", "extra", "missing", "duplicate", "bytes"])
def test_mutated_missing_or_unapproved_source_never_establishes_authority(h, tmp_path, mutation):
    opened(h)
    data = json.loads(SOURCE_PATH.read_text())
    source = data["records"][0]
    if mutation == "membership": source["membership"]["archetype_id"] = "role_unrelated"
    if mutation == "direction": source["parent_direction_id"] = "direction_unknown"
    if mutation == "archetype": source["parent_archetype_id"] = "role_unrelated"
    if mutation == "role": source["representative_role_id"] = "specific_role_unrelated"
    if mutation == "parent": source["parent_source_fingerprint"] = "0" * 64
    if mutation == "version": source["version"] = 2
    if mutation == "provenance": source["provenance"] = "live_jobs"
    if mutation == "extra": source["fit_score"] = 90
    if mutation == "duplicate": data["records"][1] = source
    if mutation == "bytes": source["purpose"] = "new unapproved public prose"
    if mutation == "missing": data["records"].pop()
    path = tmp_path / "public_d4.json"
    path.write_text(json.dumps(data))
    s = h.workspace.specific_role
    s.registry = SpecificRoleRegistry(path)
    assert s.submit("详细讲讲第一种角色")
    assert s.binding is None and s.messages[-1].reply is None
    assert "没有换成旧岗位" in s.messages[-1].text
    assert not h.workspace.chat.messages


@pytest.mark.parametrize("mutation", ["membership", "version", "provenance", "extra", "missing"])
def test_strict_schema_itself_rejects_invalid_membership_and_metadata(mutation):
    data = json.loads(SOURCE_PATH.read_text())
    if mutation == "membership": data["records"][0]["membership"]["representative_role_id"] = "other"
    if mutation == "version": data["records"][0]["version"] = 2
    if mutation == "provenance": data["records"][0]["provenance"] = "real_market"
    if mutation == "extra": data["records"][0]["ranking"] = 1
    if mutation == "missing": data["records"].pop()
    with pytest.raises(ValueError): Inventory.model_validate(data)


@pytest.mark.parametrize("mutation", ["text", "ref", "membership", "authority", "role", "archetype", "source", "version", "fingerprint", "duplicate", "order"])
def test_no_semantic_repair_or_source_id_substitution(mutation):
    source = SpecificRoleRegistry().inventory().records[0]
    service = SpecificRoleService()
    reply = service.reply(source, Dimension.OVERVIEW)
    changes = {"text":{"text":"unsupported prose"}, "ref":{"source_ref":"other"},
               "membership":{"membership_refs":("other", "other")}, "authority":{"authority":Authority.EXPLANATION}}
    if mutation in changes:
        reply = reply.model_copy(update={"blocks":(reply.blocks[0].model_copy(update=changes[mutation]), *reply.blocks[1:])})
    fields = {"role":"representative_role_id", "archetype":"archetype_id", "source":"source_id", "version":"source_version", "fingerprint":"source_fingerprint"}
    if mutation in fields: reply = reply.model_copy(update={fields[mutation]:99 if mutation == "version" else "other"})
    if mutation == "duplicate": reply = reply.model_copy(update={"blocks":(*reply.blocks, reply.blocks[0])})
    if mutation == "order": reply = reply.model_copy(update={"blocks":tuple(reversed(reply.blocks))})
    with pytest.raises(ValueError): service.validate(reply, source)


@pytest.mark.parametrize("question,dimension", [
    ("这个角色具体每天做什么？",Dimension.WORK), ("它一般和谁合作？",Dimension.COLLABORATION),
    ("这个角色最后要交付什么？",Dimension.IO), ("会不会一直写代码？",Dimension.TECHNICAL),
    ("这个角色能决定什么？",Dimension.DECISIONS), ("什么时候需要人工介入？",Dimension.DECISIONS),
    ("这个角色工作节奏是什么？",Dimension.RHYTHM), ("这个角色需要哪些能力？",Dimension.CAPABILITIES),
    ("这个角色一天怎么工作？",Dimension.RHYTHM),
    ("这个角色一天大概怎么工作？",Dimension.RHYTHM),
    ("这个角色平时一天怎么过？",Dimension.RHYTHM),
    ("这个角色在不同组织有什么变化？",Dimension.VARIATION), ("这个角色还有什么不确定？",Dimension.UNKNOWN),
    ("这个角色存在的目的是什么？",Dimension.PURPOSE), ("能举个具体例子吗？",Dimension.SITUATION),
    ("服务业务问题分析专员（合成示例）具体每天做什么？",Dimension.WORK),
])
def test_progressive_followups_one_dimension_at_a_time(h, question, dimension):
    s = expanded(h)
    assert s.submit(question)
    assert s.messages[-1].reply.dimension == dimension
    assert s.service.validate(s.messages[-1].reply, s.source)


@pytest.mark.parametrize("question", ["第一种和第二种有什么区别？", "这个方向主要解决什么问题？", "Transformer 的 attention 是什么？", "这个方向整体在解决什么问题？", "第一种具体每天做什么？另外介绍 Python", "岗位是什么意思？", "Transformer 平时做什么？", "详细讲讲 Transformer attention", "这本书适合我吗？"])
def test_non_d4_questions_do_not_spend_turn_or_take_qa(h, question):
    s = expanded(h)
    before = s.messages[:], s.turns
    assert not s.submit(question)
    assert (s.messages, s.turns) == before


@pytest.mark.parametrize("question", [
    "这个方向整体做什么？", "这个方向整体是做什么的？", "这个方向平时主要做什么？",
])
def test_overall_direction_work_keeps_d2_source_and_active_d4(h, question):
    s = expanded(h)
    w = h.workspace
    stamp, messages = s.binding, s.messages[:]
    before = h.current(), h.memories(), h.history()
    assert followup_dimension(question) == RealityDimension.WORK
    assert not s.submit(question) and not w.role_landscape.submit(question)
    assert w.career_reality.submit(question)
    reply = w.career_reality.messages[-1].reply
    assert reply.dimension == RealityDimension.WORK
    assert w.career_reality.service.validate(reply, w.career_reality.source) == reply
    assert s.current() and s.binding == stamp and s.messages == messages
    assert before == (h.current(), h.memories(), h.history())


@pytest.mark.parametrize("question", [
    "Transformer 整体做什么？", "Transformer 一天怎么工作？",
    "Transformer attention 是什么？",
    "这个方向整体做什么？另外解释 Python。",
    "这个角色一天怎么工作？另外解释 Transformer。",
])
def test_new_work_patterns_do_not_take_technical_or_mixed_qa(h, question):
    s = expanded(h)
    w = h.workspace
    before = tuple(session.messages[:] for session in (s, w.role_landscape, w.career_reality))
    assert followup_dimension(question) is None
    assert not s.submit(question)
    assert not w.role_landscape.submit(question)
    assert not w.career_reality.submit(question)
    assert before == tuple(session.messages for session in (s, w.role_landscape, w.career_reality))


@pytest.mark.parametrize("reference,index", [("第一种",0), ("第二个",1), ("刚才偏系统那个",2), ("刚才偏系统的那个",2), ("系统流程分析型",2), ("偏需求那个",1), ("role_ba_problem",0)])
def test_exact_references_only(h, reference, index):
    parent = opened(h)
    s = h.workspace.specific_role
    assert s.submit("详细讲讲" + reference)
    assert s.source.parent_archetype_id == parent.binding.displayed_role_ids[index]


@pytest.mark.parametrize("reference", ["第四种", "这个角色", "需求型", "不选需求转译型", "role_ko_curation", "role_unknown", "第一种和第二种"])
def test_ambiguous_out_of_range_cross_direction_not_guessed(h, reference):
    opened(h)
    s = h.workspace.specific_role
    assert s.submit("详细讲讲" + reference)
    assert s.binding is None and s.messages[-1].reply is None
    assert "没有猜测" in s.messages[-1].text


def test_missing_parent_or_file_has_no_legacy_fallback(h, tmp_path, monkeypatch):
    def forbidden(*a, **k): pytest.fail("No generic jobs/tool/provider fallback")
    monkeypatch.setattr("career_runtime.tools.ToolRegistry.execute", forbidden)
    s = h.workspace.specific_role
    assert s.submit("详细讲讲第二种角色") and s.messages[-1].reply is None
    opened(h)
    s.registry = SpecificRoleRegistry(tmp_path / "missing.json")
    assert s.submit("详细讲讲第二种角色") and s.messages[-1].reply is None


@pytest.mark.parametrize("question", ["这个角色适合我吗？", "哪个更适合我？", "你觉得我能做吗？", "帮我推荐岗位", "给我排序角色", "第三种更适合我吗？", "需求转译型适合我吗？", "role_ba_system适合我吗？", "我适合这个角色吗？", "你觉得我能做系统流程分析型吗？", "这个角色不适合我吗？", "那你觉得哪个更适合我？", "服务业务问题分析专员（合成示例）适合我吗？"])
def test_match_boundary_actual_local_response_without_match(h, question):
    s = expanded(h)
    before = h.current(), h.memories(), h.history()
    assert s.submit(question) and s.messages[-1].reply is None
    assert "个人证据与工作证据" in s.messages[-1].text
    assert before == (h.current(), h.memories(), h.history())
    assert not h.workspace.controller.state or not h.workspace.controller.state.get("match_results")


def test_no_role_fact_profile_reads_no_memory_no_authority_mutation(h, monkeypatch):
    opened(h)
    w, s = h.workspace, h.workspace.specific_role
    before = h.current(), h.memories(), h.history()
    def forbidden(*a, **k): pytest.fail("No D.4 authority read/write/tool")
    for name in ("retrieve_context", "create_candidate", "create_confirmed", "supersede", "save_confirmed_profile"):
        monkeypatch.setattr(w.memory_service, name, forbidden)
    monkeypatch.setattr(w.memory_service.memory_store, "get", forbidden)
    monkeypatch.setattr("career_runtime.tools.ToolRegistry.execute", forbidden)
    assert s.submit("详细讲讲第二种角色")
    assert s.submit("这个角色需要哪些能力？")
    assert "不表示你已经具备或缺少" in s.messages[-1].text
    assert s.submit("这个角色很有意思") and s.messages[-1].reply is None
    assert before == (h.current(), h.memories(), h.history())
    assert not w.chat.messages and not w.store.list_messages(w.owner_scope_id, w.thread.thread_id)
    assert "specific_role" not in json.dumps(w._snapshot())
    events = json.dumps([asdict(e) for e in s.events], ensure_ascii=False)
    assert all(v not in events for v in (s.source.purpose, h.scenario.goal_label, "第二种"))


@pytest.mark.parametrize("reference", ["第四种", "第五个角色"])
def test_interest_in_unknown_reference_is_not_silently_accepted(h, reference):
    s = expanded(h)
    stamp = s.binding
    before = h.current(), h.memories(), h.history()
    assert s.submit(reference + "很有意思") and s.messages[-1].reply is None
    assert "没有猜测" in s.messages[-1].text and s.binding == stamp
    assert before == (h.current(), h.memories(), h.history())


@pytest.mark.parametrize("operation", ["new", "switch", "delete", "close", "resume", "profile", "owner", "thread", "d1", "d2", "d3", "d3_version", "source_version", "source_bytes"])
def test_lifecycle_stale_parent_invalidates_and_old_token_cannot_replay(h, tmp_path, operation):
    s = expanded(h)
    token, w = s.token(), h.workspace
    if operation == "new": w.create_new_thread()
    if operation == "switch": w.activate(w.thread.thread_id)
    if operation == "delete": w.delete_thread(w.thread.thread_id)
    if operation == "close": w.close()
    if operation == "resume": w.resume_intake.clear()
    if operation == "profile":
        original = w.memory_service.get_current_confirmed_profile
        w.memory_service.get_current_confirmed_profile = lambda owner: original(owner).model_copy(update={"version":999})
    if operation == "owner": w.owner_scope_id = str(uuid4())
    if operation == "thread": w._thread = replace(w.thread, thread_id=str(uuid4()))
    if operation == "d1": w.career_discovery.status = __import__("career_discovery.models", fromlist=["Status"]).Status.STALE
    if operation == "d2": w.career_reality.invalidate()
    if operation == "d3": w.role_landscape.invalidate()
    if operation == "d3_version": w.role_landscape.binding = w.role_landscape.binding.model_copy(update={"source_version":99})
    if operation.startswith("source_"):
        data = json.loads(SOURCE_PATH.read_text())
        if operation == "source_version": data["records"][0]["version"] = 2
        else: data["records"][0]["purpose"] = "changed public prose"
        path = tmp_path / "changed.json"; path.write_text(json.dumps(data))
        s.registry = SpecificRoleRegistry(path)
    assert not s.current() and s.binding is None and not s.messages
    assert s.submit("这个角色通常和谁合作？", token=token) and not s.messages


@pytest.mark.parametrize("operation", ["new", "switch", "delete", "close", "d2", "d3"])
def test_late_reply_cannot_resurrect_state(h, operation):
    s = expanded(h)
    entered, release = Event(), Event()
    original = s.service.reply
    def delayed(*a, **k):
        entered.set(); assert release.wait(5)
        return original(*a, **k)
    s.service.reply = delayed
    worker = Thread(target=s.submit, args=("这个角色最后要交付什么？",))
    worker.start(); assert entered.wait(5)
    w = h.workspace
    if operation == "new": w.create_new_thread()
    if operation == "switch": w.activate(w.thread.thread_id)
    if operation == "delete": w.delete_thread(w.thread.thread_id)
    if operation == "close": w.close()
    if operation == "d2": w.career_reality.invalidate()
    if operation == "d3": w.role_landscape.invalidate()
    release.set(); worker.join(5)
    assert not worker.is_alive()
    assert not s.current() and s.binding is None and not s.messages


@pytest.mark.parametrize("field,value", [("owner","other"), ("thread","other"), ("request_id","other"), ("generation",999), ("context_fingerprint","other")])
def test_foreign_or_replayed_token_consumed_without_qa(h, field, value):
    s = expanded(h)
    before = s.messages[:]
    assert s.submit("这个角色通常和谁合作？", token=s.token().model_copy(update={field:value}))
    assert s.messages == before


def test_replay_role_switch_and_general_qa_resume(h):
    s = expanded(h)
    old = s.token()
    assert s.submit("这个角色最后要交付什么？", token=old)
    before = s.messages[:]
    assert s.submit("这个角色最后要交付什么？", token=old) and s.messages == before
    old = s.token()
    assert s.submit("详细讲讲第二种角色")
    assert s.submit("这个角色最后要交付什么？", token=old) and s.messages[-1].reply.dimension == Dimension.OVERVIEW
    assert s.messages[1].source.parent_archetype_id != s.source.parent_archetype_id
    stamp = s.binding
    assert not s.submit("Transformer 的 attention 是什么？")
    h.workspace.career_discovery.invalidate()
    h.workspace.reload_completed_turn(h.workspace.thread.thread_id)
    assert s.current() and s.binding == stamp
    assert s.submit("这个角色通常和谁合作？") and s.messages[-1].reply.dimension == Dimension.COLLABORATION


def test_budget_busy_and_credentials_never_use_provider(h):
    s = expanded(h)
    before = s.messages[:]
    assert not s.submit("x" * 2001)
    s.busy = True
    assert s.submit("详细讲讲第二种角色") and s.messages == before
    s.busy = False
    assert s.submit("详细讲讲role_bad sk-" + "a1B2c3D4" * 4) and s.messages == before
    for _ in range(24): s.submit("这个角色通常和谁合作？")
    assert s.turns == 24 and s.status == Status.LIMIT_REACHED
    assert len(s.messages) <= 40 and len(s.events) <= 40
