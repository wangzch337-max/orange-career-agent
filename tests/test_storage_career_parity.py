"""Same actual confirmation and D.1-D.6 chain under both storage strategies."""

from threading import Event, Thread
from uuid import uuid4
import pytest
from tests.test_workspace_storage import w, offline, confirmed
from tests.test_specific_role import expanded
from specific_role.sources import SpecificRoleRegistry
from evidence_validation.sources import ExperimentRegistry
from evidence_match.models import Relation
from ui.chat_runtime import Workspace
from storage.workspace import ephemeral_storage


SOURCES = SpecificRoleRegistry().inventory().records


def opened(w, root, source):
    h, profile = confirmed(w, root)
    peers = [s for s in SOURCES if s.direction_identity == source.direction_identity]
    expanded(h, source.direction_identity.title, peers.index(source))
    assert w.evidence_match.submit("我有什么经历和这个工作相关？") and w.evidence_match.current()
    parent = w.evidence_match
    validation = w.evidence_validation
    assert validation.submit("我怎么验证这一点？") and validation.target is None
    target = next(t for t in validation.messages[-1].options if ExperimentRegistry().resolve(t, parent.context.work) is not None)
    assert validation.select(validation.messages[-1].token, target.relation_id) and validation.current()
    return h, profile, parent, validation


@pytest.mark.parametrize("source", SOURCES, ids=lambda s: s.representative_role_id)
def test_all_nine_actual_confirmation_to_d6_and_qa_resume(w, tmp_path, source):
    h, profile, parent, validation = opened(w, tmp_path, source)
    before = h.current(), h.memories(), h.history(), parent.result, parent.binding
    assert validation.target.relation_type in (Relation.UNKNOWN, Relation.PARTIAL)
    assert validation.template.role_id == source.representative_role_id
    assert validation.submit("给我一个小任务试试") and validation.experiment_selected
    for text in ("观察：公开合成材料有两条规则未确认", "产出：合成规则表", "反思：仍需了解完整责任", "帮助：阅读给定材料", "完成本次实验", "查看验证摘要"):
        assert validation.submit(text) and validation.current()
    assert validation.outcome.authority == "unverified_session_report"
    assert before == (h.current(), h.memories(), h.history(), parent.result, parent.binding)
    assert not w.store.list_messages(w.owner_scope_id, w.thread.thread_id)
    assert not {"evidence_match", "evidence_validation"} & w._snapshot().keys()
    from tests.agent_doubles import ScriptedProvider, plan, answer
    fake = ScriptedProvider([plan()], answer("公开合成：decorator 是包装函数行为的一种方式。"))
    session = w.agent_session; session.provider_factory = lambda: fake
    session.queue("Python decorator 是什么？", "typed")
    list(session.stream_turn(session.pending))
    assert parent.current() and validation.current()
    assert parent.submit("为什么这里是 unknown？")
    assert validation.submit("查看验证摘要")
    pair = w.store.list_messages(w.owner_scope_id, w.thread.thread_id)
    assert len(pair) == 2 and pair[-1].content.startswith("公开合成：decorator")
    assert "关系relationship_" not in pair[-1].content and "验证摘要" not in pair[-1].content
    assert before == (h.current(), h.memories(), h.history(), parent.result, parent.binding)
    token = validation.token(); old_thread = w.thread.thread_id
    w.create_new_thread()
    assert not parent.messages and not validation.messages and validation.binding is None
    assert validation.submit("完成本次实验", token=token) and not validation.messages
    w.activate(old_thread)
    assert not parent.current() and not validation.current()


@pytest.mark.parametrize("transition", ("switch", "delete", "close", "profile", "source", "template"))
def test_full_chain_invalidates_without_resurrection(w, tmp_path, transition):
    h, profile, parent, validation = opened(w, tmp_path, SOURCES[0])
    token, old_thread = validation.token(), w.thread.thread_id
    if transition == "switch": w.create_new_thread(); w.activate(old_thread)
    elif transition == "delete": w.delete_thread(old_thread)
    elif transition == "close": w.close()
    elif transition == "profile":
        # Existing revision + explicit confirmation APIs, not confirmed=True.
        # Initial authority above was constructed through the full actual review.
        from memory.models import ProfileReference
        revision = profile.create_revision(education_summary="公开合成的已确认更新").confirm()
        w.memory_service.profile_store.save_confirmed_profile(w.subject_id, revision,
            expected_current=ProfileReference(subject_id=w.subject_id, profile_id=profile.profile_id, version=profile.version))
    elif transition == "source":
        w.specific_role.source = w.specific_role.source.model_copy(update={"purpose": "失效的合成来源"})
    elif transition == "template":
        original = validation.registry.resolve
        validation.registry.resolve = lambda *args: original(*args).model_copy(update={"task": "失效的合成模板"})
    assert not validation.current()
    assert validation.submit("完成本次实验", token=token) and not validation.messages


def test_late_d5_result_after_ephemeral_cleanup_never_publishes(tmp_path):
    owner = str(uuid4()); w = Workspace(owner, storage_adapters=ephemeral_storage(owner))
    h, profile = confirmed(w, tmp_path); expanded(h)
    entered, release = Event(), Event()
    original = w.evidence_match.agent_factory
    class Slow:
        def __init__(self, context): self.agent = original(context)
        def analyze_role_relationships(self, *args):
            entered.set(); assert release.wait(3)
            return self.agent.analyze_role_relationships(*args)
    w.evidence_match.agent_factory = Slow
    worker = Thread(target=lambda: w.evidence_match.submit("这个角色适合我吗？"))
    worker.start(); assert entered.wait(3)
    w.close(); release.set(); worker.join(3)
    assert not worker.is_alive() and not w.evidence_match.current() and not w.evidence_match.messages
    assert w.evidence_match.result is None and not w.storage._database.profiles


def test_late_fake_provider_after_ephemeral_cleanup_cannot_publish():
    from tests.agent_doubles import ScriptedProvider, plan, answer
    owner = str(uuid4()); w = Workspace(owner, storage_adapters=ephemeral_storage(owner))
    entered, release = Event(), Event()
    class Slow(ScriptedProvider):
        def generate_structured(self, *args, **kwargs):
            entered.set(); assert release.wait(3)
            return super().generate_structured(*args, **kwargs)
    fake = Slow([plan()], answer())
    session = w.agent_session; session.provider_factory = lambda: fake
    session.set_consent(granted=True); session.queue("公开合成普通问题", "typed")
    pending = session.pending
    session.start_pending(); assert entered.wait(3)
    w.close(); release.set(); assert session._worker_done.wait(3)
    assert session.progress() is None and session.last_result is None
    assert not w.chat.messages and not w.storage._raw_conversations._messages
    assert not w.storage.settings._receipts and not w.storage.settings._consent
    before = (fake.structured_calls, fake.stream_calls)
    list(session.stream_turn(pending))
    assert before == (fake.structured_calls, fake.stream_calls)
