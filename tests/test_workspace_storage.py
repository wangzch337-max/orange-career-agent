"""Shared offline contracts; every profile is reviewed from public synthetic input."""

from pathlib import Path
from uuid import uuid4
import builtins
import socket
import sqlite3
import tempfile
import pysqlite3
import pytest

from ui.chat_runtime import Workspace
from storage.workspace import ephemeral_storage, sqlite_storage
from storage.settings import ConsentCategory
from storage.contracts import StorageClosedError
from memory.errors import ProfileVersionConflictError, InvalidMemoryTransitionError, MemoryConflictError
from memory.models import ProfileReference, MemoryType
from data.models import EvidenceSourceType
from career_background_evaluation.harness import CareerHarness
from career_background_evaluation.scenarios import SCENARIOS


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def blocked(*a, **k): raise AssertionError("Storage contracts forbid network/config/provider access.")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr("providers.models.load_llm_settings", blocked)
    monkeypatch.setattr("resume_evidence.session._qwen_provider", blocked)


@pytest.fixture(params=("sqlite", "ephemeral"))
def w(request, tmp_path):
    owner = str(uuid4())
    adapters = sqlite_storage(owner, tmp_path / "workspace") if request.param == "sqlite" else ephemeral_storage(owner)
    with Workspace(owner, storage_adapters=adapters) as workspace:
        yield workspace


def confirmed(w, root):
    h = CareerHarness(root, SCENARIOS[3], workspace=w)
    h.prepare()
    assert h.current() is None and not h.memories()
    assert w.profile_refinement.confirm(w.profile_refinement.token(), confirmed_by_user=False) is None
    h.resolve_all(); profile = h.confirm(memory=True)
    assert h.current() == profile and profile.confirmed and h.memories()
    return h, profile


def record(w, **kwargs):
    return dict(subject_id=w.subject_id, memory_type=MemoryType.GOAL, content="公开合成职业目标", source_type=EvidenceSourceType.EXPLICIT_USER_INPUT, **kwargs)


def test_actual_confirmation_and_profile_versions(w, tmp_path):
    h, p = confirmed(w, tmp_path)
    store = w.memory_service.profile_store
    with pytest.raises(ProfileVersionConflictError): store.save_confirmed_profile(w.subject_id, p.create_revision())
    assert store.save_confirmed_profile(w.subject_id, p, expected_current=None).created is False
    # Replay cannot bypass the existing subject/version base validation.
    stale = ProfileReference(subject_id="foreign_subject", profile_id=p.profile_id, version=99)
    with pytest.raises(ProfileVersionConflictError): store.save_confirmed_profile(w.subject_id, p, expected_current=stale)
    with pytest.raises(ProfileVersionConflictError):
        store.save_confirmed_profile(w.subject_id, p.create_revision().confirm(), expected_current=None)
    reference = ProfileReference(subject_id=w.subject_id, profile_id=p.profile_id, version=p.version)
    revision = p.create_revision(education_summary="公开合成版本更新").confirm()
    count = []
    def guard():
        assert store.get_current_confirmed_profile(w.subject_id) == p
        count.append(1)
    store.save_confirmed_profile(w.subject_id, revision, expected_current=reference, confirmation_guard=guard)
    assert len(count) == 2 and store.get_current_confirmed_profile(w.subject_id) == revision
    with pytest.raises(ProfileVersionConflictError): store.save_confirmed_profile(w.subject_id, revision, expected_current=None)
    assert store.save_confirmed_profile(w.subject_id, revision, expected_current=reference).created is False
    assert store.get_profile_version(w.subject_id, p.profile_id, p.version) == p
    assert len(h.history()) == 2
    with pytest.raises(ProfileVersionConflictError): store.save_confirmed_profile(w.subject_id, p.model_copy(update={"education_summary": "冲突"}))
    copy = store.get_current_confirmed_profile(w.subject_id); copy.skills.clear(); copy.evidence.clear()
    assert store.get_current_confirmed_profile(w.subject_id) == revision


@pytest.mark.parametrize("fail_at", (1, 2))
def test_guard_failure_rolls_back_version_and_pointer(w, tmp_path, fail_at):
    h, p = confirmed(w, tmp_path); before = h.history(); calls = []
    def guard():
        calls.append(1)
        if len(calls) == fail_at: raise ValueError("Synthetic stale review.")
    ref = ProfileReference(subject_id=w.subject_id, profile_id=p.profile_id, version=p.version)
    with pytest.raises(ValueError):
        w.memory_service.profile_store.save_confirmed_profile(w.subject_id, p.create_revision().confirm(), expected_current=ref, confirmation_guard=guard)
    assert h.current() == p and h.history() == before


def test_memory_governance_idempotency_and_retrieval(w):
    s = w.memory_service
    m = s.create_candidate(**record(w, memory_id="public_storage_memory"))
    assert not s.retrieve(w.subject_id, "职业目标")
    with pytest.raises(InvalidMemoryTransitionError): s.confirm_candidate(w.subject_id, m.memory_id, confirmed_by_user=False)
    with pytest.raises(InvalidMemoryTransitionError): s.create_confirmed(**record(w), confirmed_by_user=False)
    s.confirm_candidate(w.subject_id, m.memory_id, confirmed_by_user=True)
    assert s.create_candidate(**record(w, memory_id=m.memory_id)).status.value == "confirmed"
    conflict = record(w, memory_id=m.memory_id); conflict["content"] = "另一条合成内容"
    with pytest.raises(MemoryConflictError): s.create_candidate(**conflict)
    assert s.retrieve(w.subject_id, "职业目标")[0].memory.memory_id == m.memory_id
    assert s.retrieve_hybrid(w.subject_id, "职业目标")[0].memory.memory_id == m.memory_id
    from memory.integration import MemoryContextCoordinator
    from memory.models import MemoryUseCase, MemoryConsumer
    context = MemoryContextCoordinator(s).retrieve(subject_id=w.subject_id, use_case=MemoryUseCase.CAREER_DIRECTION_DISCOVERY,
        consumer=MemoryConsumer.CAREER_DIRECTION_DISCOVERY_SERVICE, query="职业目标")
    assert context.items and all(x.authority == "active_confirmed" for x in context.items)
    with pytest.raises(PermissionError):
        MemoryContextCoordinator(s).retrieve(subject_id=w.subject_id, use_case=MemoryUseCase.CAREER_DIRECTION_DISCOVERY,
            consumer=MemoryConsumer.PROFILE_REFINEMENT_SERVICE, query="职业目标")
    replacement = s.supersede(w.subject_id, m.memory_id, content="公开合成新目标", source_type=EvidenceSourceType.EXPLICIT_USER_INPUT, confirmed_by_user=True)
    assert s.memory_store.get(w.subject_id, m.memory_id).status.value == "superseded"
    assert s.vector_index.metadata_for(m.memory_id) is None
    s.archive(w.subject_id, replacement.memory_id)
    assert not s.memory_store.list_active(w.subject_id) and not s.retrieve_hybrid(w.subject_id, "目标")


def test_vector_fingerprint_canonical_validation_and_purge(w, tmp_path):
    h, p = confirmed(w, tmp_path); s = w.memory_service
    m = s.create_confirmed(**record(w), confirmed_by_user=True)
    from memory.vector_index import indexed_content_hash
    assert s.vector_index.metadata_for(m.memory_id).content_hash == indexed_content_hash(m)
    s.memory_store.archive(w.subject_id, m.memory_id)  # Deliberately leave a stale derived row.
    assert not any(r.memory.memory_id == m.memory_id for r in s.retrieve_semantic(w.subject_id, "职业目标"))
    foreign = m.model_copy(update={"subject_id": "foreign_subject"})
    with pytest.raises(ValueError): s.vector_index.index_record(foreign)
    with pytest.raises(ValueError): s.vector_index.query("foreign_subject", [0.0] * s.vector_index.embedding_provider.dimension)
    result = s.purge_subject(w.subject_id)
    assert result.profile_versions_deleted == 1 and result.current_pointer_deleted == 1
    assert not h.history() and not s.memory_store.list_history(w.subject_id) and not s.vector_index.list_entries(w.subject_id)


def test_conversation_lifecycle_atomicity_history_and_replay(w):
    store, owner, thread = w.store, w.owner_scope_id, w.thread.thread_id
    pair = store.append_turn(owner, thread, "公开合成问题", "公开合成答复", turn_id="public_turn")
    assert store.get_turn(owner, thread, "public_turn") == pair
    assert store.append_turn(owner, thread, pair[0].content, pair[1].content, turn_id="public_turn") == pair
    pair[-1].metadata["kind"] = "mutated"
    assert "kind" not in store.get_turn(owner, thread, "public_turn")[-1].metadata
    with pytest.raises(ValueError): store.append_turn(owner, thread, "不同内容", "不同内容", turn_id="public_turn")
    before = store.get_thread(owner, thread), store.list_messages(owner, thread)
    with pytest.raises(ValueError): store.append_turn(owner, thread, "合成问题", "合成回答", snapshot={"evidence_match": "forbidden"})
    assert before == (store.get_thread(owner, thread), store.list_messages(owner, thread))
    store.rename_thread(owner, thread, "合成名称")
    second = w.create_new_thread()
    assert not store.list_messages(owner, second.thread_id)
    with pytest.raises(Exception): store.append_turn(owner, second.thread_id, "合成问题", "合成回答", turn_id="public_turn")
    store.delete_thread(owner, thread)
    with pytest.raises(ValueError): store.get_thread(owner, thread)
    with pytest.raises(ValueError): store.append_turn(owner, thread, "晚到合成问题", "晚到合成结果")


def test_consent_categories_request_scope_and_receipt_binding(w):
    s, owner, thread = w.settings_store, w.owner_scope_id, w.thread.thread_id
    assert not s.valid(owner, ConsentCategory.AI_CHAT, "v1")
    s.set(owner, ConsentCategory.AI_CHAT, "v1", granted=True)
    assert s.valid(owner, ConsentCategory.AI_CHAT, "v1")
    s.set(owner, ConsentCategory.AI_CHAT, "v1", granted=True, request_scope="public_request_1")
    assert not s.valid(owner, ConsentCategory.AI_CHAT, "v1")
    assert s.valid(owner, ConsentCategory.AI_CHAT, "v1", request_scope="public_request_1")
    s.set(owner, ConsentCategory.AI_CHAT, "v1", granted=True)
    assert not s.valid(owner, ConsentCategory.AI_CHAT, "v1", request_scope="public_request_1")
    assert not s.valid(owner, ConsentCategory.RESUME_ANALYSIS, "v1", request_scope="public_document_1")
    s.set(owner, ConsentCategory.RESUME_ANALYSIS, "v1", granted=True, request_scope="public_document_1")
    assert s.valid(owner, ConsentCategory.RESUME_ANALYSIS, "v1", request_scope="public_document_1")
    assert not s.valid(owner, ConsentCategory.RESUME_ANALYSIS, "v1", request_scope="public_document_2")
    assert not s.valid(owner, ConsentCategory.RESUME_ANALYSIS, "v2", request_scope="public_document_1")
    s.revoke(owner, ConsentCategory.RESUME_ANALYSIS)
    assert not s.valid(owner, ConsentCategory.RESUME_ANALYSIS, "v1", request_scope="public_document_1")
    assert s.valid(owner, ConsentCategory.AI_CHAT, "v1")
    s.record_receipt(owner, thread, "public_receipt", "CANCELLED", "")
    assert s.get_receipt(owner, thread) == ("public_receipt", "CANCELLED", "")
    second = w.create_new_thread()
    with pytest.raises(ValueError): s.record_receipt(owner, second.thread_id, "public_receipt", "COMPLETED", "")
    w.delete_thread(thread)
    with pytest.raises(ValueError): s.get_receipt(owner, thread)


def test_scope_isolation_and_bundle_cannot_be_reused(w, tmp_path):
    owner = str(uuid4())
    other_adapters = ephemeral_storage(owner) if w.storage.ephemeral else sqlite_storage(owner, w.root)
    with Workspace(owner, storage_adapters=other_adapters) as b:
        b.memory_service.create_confirmed(**record(b), confirmed_by_user=True)
        b.settings_store.set(owner, ConsentCategory.AI_CHAT, "v1", granted=True)
        assert not w.settings_store.valid(w.owner_scope_id, ConsentCategory.AI_CHAT, "v1")
        foreign_memory = b.memory_service.memory_store.list_active(b.subject_id)[0]
        assert w.memory_service.memory_store.get(w.subject_id, foreign_memory.memory_id) is None
        assert w.memory_service.vector_index.metadata_for(foreign_memory.memory_id) is None
        for call in (
            lambda: w.store.get_thread(owner, b.thread.thread_id),
            lambda: w.memory_service.get_current_confirmed_profile(b.subject_id),
            lambda: w.memory_service.memory_store.list_active(b.subject_id),
            lambda: w.memory_service.retrieve_hybrid(b.subject_id, "目标"),
            lambda: w.settings_store.valid(owner, ConsentCategory.AI_CHAT, "v1"),
            lambda: w.settings_store.get_receipt(owner, b.thread.thread_id),
            lambda: w.checkpointer.get_tuple({"configurable": {"thread_id": b.thread.workflow_thread_id}}),
        ):
            with pytest.raises(ValueError): call()
        with pytest.raises(ValueError): Workspace(owner, storage_adapters=w.storage)
        with pytest.raises(ValueError): Workspace(w.owner_scope_id, storage_adapters=w.storage)


def test_invalid_receipt_is_atomic_and_cleanup_denies_ports(w):
    settings, owner, thread = w.settings_store, w.owner_scope_id, w.thread.thread_id
    with pytest.raises(ValueError): settings.record_receipt(owner, thread, "public_invalid_receipt", "INVALID", "")
    assert settings.get_receipt(owner, thread) is None
    other = w.create_new_thread()
    settings.record_receipt(owner, other.thread_id, "public_invalid_receipt", "UNKNOWN", "")
    assert settings.get_receipt(owner, other.thread_id)[1] == "UNKNOWN"
    service, saver, subject = w.memory_service, w.checkpointer, w.subject_id
    w.close()
    reads = (lambda: service.get_current_confirmed_profile(subject), lambda: service.memory_store.list_active(subject))
    for call in reads:
        if w.storage.ephemeral:
            with pytest.raises(StorageClosedError): call()
        else:
            assert not call()  # Existing SQLite read-only diagnostic compatibility.
    for call in (
        lambda: service.create_confirmed(**record(w), confirmed_by_user=True),
        lambda: service.retrieve_hybrid(subject, "目标"),
        lambda: settings.get_receipt(owner, other.thread_id),
        lambda: saver.get_tuple({"configurable": {"thread_id": other.workflow_thread_id}}),
        lambda: w.store.append_turn(owner, other.thread_id, "晚到", "合成内容"),
    ):
        with pytest.raises(StorageClosedError): call()


def test_checkpoint_roundtrip_stale_write_and_real_guided_confirmation(w):
    from tests.test_chat_runtime import reach_review
    from ui.conversation_shell import CONFIRM
    reach_review(w)
    thread = w.thread; config = {"configurable": {"thread_id": thread.workflow_thread_id}}
    assert w.checkpointer.get_tuple(config) is not None
    w.submit(CONFIRM)
    assert w.memory_service.get_current_confirmed_profile(w.subject_id).confirmed
    w.create_new_thread(); w.delete_thread(thread.thread_id)
    assert w.checkpointer.get_tuple(config) is None
    with pytest.raises(ValueError): w.checkpointer.put_writes(config, [], "public_late_task")


def test_legacy_empty_thread_checkpoint_binding_without_activation_write(w):
    other = w.store.create_thread(w.owner_scope_id)
    assert other.workflow_thread_id is None
    w.activate(other.thread_id)
    config = {"configurable": {"thread_id": w.controller.workflow_id, "checkpoint_id": "public_empty_checkpoint"}}
    assert w.checkpointer.get_tuple(config) is None
    assert w.store.get_thread(w.owner_scope_id, other.thread_id) == other
    w.checkpointer.put_writes(config, [], "public_empty_task")
    w.delete_thread(other.thread_id)
    assert w.checkpointer.get_tuple(config) is None
    with pytest.raises(ValueError): w.checkpointer.put_writes(config, [], "public_late_task")


def test_runtime_uses_same_fake_transport_replay_and_revoke(w):
    from career_runtime.session import AgentSession
    from tests.agent_doubles import ScriptedProvider, plan, answer
    provider = ScriptedProvider([plan()], answer())
    session = AgentSession(w, provider_factory=lambda: provider)
    session.set_consent(granted=True); session.queue("公开合成普通问题", "typed")
    pending = session.pending; list(session.stream_turn(pending))
    assert (provider.structured_calls, provider.stream_calls) == (1, 1)
    list(session.stream_turn(pending))
    assert (provider.structured_calls, provider.stream_calls) == (1, 1)
    session.set_consent(granted=False)
    with pytest.raises(PermissionError): session.queue("第二个合成问题", "typed")
    session.close()


def test_ephemeral_entire_confirmation_flow_has_no_disk_io(tmp_path, monkeypatch, caplog):
    def forbidden(*a, **k): raise AssertionError("Ephemeral storage attempted disk IO.")
    real_open = builtins.open
    def read_only(file, mode="r", *a, **k):
        if any(flag in mode for flag in "wax+"): forbidden()
        return real_open(file, mode, *a, **k)
    monkeypatch.setattr(builtins, "open", read_only)
    monkeypatch.setattr(sqlite3, "connect", forbidden); monkeypatch.setattr(pysqlite3, "connect", forbidden)
    monkeypatch.setattr(tempfile, "TemporaryDirectory", forbidden)
    monkeypatch.setattr("ui.demo_controller.TemporaryDirectory", forbidden)
    for name in ("mkdir", "write_text", "write_bytes"): monkeypatch.setattr(Path, name, forbidden)
    owner = str(uuid4()); adapters = ephemeral_storage(owner)
    with Workspace(owner, storage_adapters=adapters) as workspace:
        h, p = confirmed(workspace, tmp_path)
        workspace.submit("我想继续探索职业方向")
        from tests.agent_doubles import ScriptedProvider, plan, answer
        fake = ScriptedProvider([plan()], answer())
        session = workspace.agent_session
        session.provider_factory = lambda: fake
        session.set_consent(granted=True)
        session.queue("公开合成普通问题", "typed")
        list(session.stream_turn(session.pending))
        assert (fake.structured_calls, fake.stream_calls) == (1, 1)
        assert session.path is None
        assert workspace.root is None and workspace.runtime_root is None
        assert workspace.controller._temporary_directory is None
        assert p.evidence[0].statement not in caplog.text
        controller = workspace.controller
        controller.role_deprioritization_reasons["public_role"] = "公开合成原因"
        controller.action_statuses["public_action"] = "not_started"
        store, profile, vector, settings = workspace.store, workspace.memory_service.profile_store, workspace.memory_service.vector_index, workspace.settings_store
        thread, subject, saver = workspace.thread, workspace.subject_id, workspace.checkpointer
    assert not list(tmp_path.iterdir())
    assert controller.state is None and not controller.role_deprioritization_reasons and not controller.action_statuses
    assert not controller.memory_change_candidates and not controller.role_memory_contexts
    for call in (
        lambda: store.get_thread(owner, thread.thread_id), lambda: profile.get_current_confirmed_profile(subject),
        lambda: vector.list_entries(subject), lambda: settings.valid(owner, ConsentCategory.AI_CHAT, "v1"),
        lambda: saver.get_tuple({"configurable": {"thread_id": thread.workflow_thread_id}}),
        lambda: store.append_turn(owner, thread.thread_id, "晚到", "合成结果"),
    ):
        with pytest.raises(StorageClosedError): call()
    assert not adapters._database.records and not adapters._database.profiles and not adapters._vector._entries


def test_cleanup_races_guard_without_resurrection(tmp_path):
    owner = str(uuid4()); adapters = ephemeral_storage(owner)
    workspace = Workspace(owner, storage_adapters=adapters)
    _, p = confirmed(workspace, tmp_path)
    store, subject = workspace.memory_service.profile_store, workspace.subject_id
    def close_guard(): adapters.close()
    with pytest.raises(StorageClosedError):
        store.save_confirmed_profile(subject, p.create_revision().confirm(), confirmation_guard=close_guard)
    assert not adapters._database.profiles and not adapters._database.current
    workspace.close()


def test_ephemeral_checkpoint_cleanup_drops_all_buckets_despite_thread_delete_failure(monkeypatch):
    from tests.test_chat_runtime import reach_review
    owner = str(uuid4())
    workspace = Workspace(owner, storage_adapters=ephemeral_storage(owner))
    reach_review(workspace)
    saver = workspace.checkpointer.saver
    assert saver.storage and saver.blobs
    def failed_delete(*args, **kwargs):
        raise RuntimeError("Synthetic checkpoint cleanup failure.")
    monkeypatch.setattr(saver, "delete_thread", failed_delete)
    workspace.close()
    assert not saver.storage and not saver.writes and not saver.blobs
    assert not workspace.storage.checkpointer.issued_workflows
    assert workspace.storage._cleanup_complete
    workspace.close()  # Successful disposal remains idempotent.


@pytest.mark.parametrize("failed_component", ("checkpoint", "settings", "conversation", "canonical", "vector"))
def test_ephemeral_cleanup_failure_cannot_skip_other_stores_and_can_retry(tmp_path, monkeypatch, failed_component):
    owner = str(uuid4())
    workspace = Workspace(owner, storage_adapters=ephemeral_storage(owner))
    confirmed(workspace, tmp_path)
    thread, subject = workspace.thread.thread_id, workspace.subject_id
    workspace.store.append_turn(owner, thread, "公开合成清理问题", "公开合成清理回答")
    settings = workspace.settings_store
    settings.set(owner, ConsentCategory.AI_CHAT, "public_cleanup_v1", granted=True)
    settings.record_receipt(owner, thread, "public_cleanup_request", "UNKNOWN", "")
    bundle = workspace.storage
    components = {"checkpoint": bundle.checkpointer, "settings": settings,
                  "conversation": bundle._raw_conversations, "canonical": bundle._database,
                  "vector": bundle._vector}
    failed = components[failed_component]
    original = failed.clear
    def fail():
        raise RuntimeError("SYNTHETIC_CONTENT_MUST_NOT_ESCAPE")
    monkeypatch.setattr(failed, "clear", fail)
    with pytest.raises(StorageClosedError, match="^Storage cleanup is incomplete\\.$"):
        workspace.close()
    assert bundle.lease.closed and not bundle._cleanup_complete
    if failed_component != "settings":
        assert not settings._consent and not settings._receipts and not settings._requests
    if failed_component != "conversation":
        assert not bundle._raw_conversations._messages and not bundle._raw_conversations._snapshots
    if failed_component != "canonical":
        assert not bundle._database.profiles and not bundle._database.current and not bundle._database.records
    if failed_component != "vector":
        assert not bundle._vector._entries and not bundle._vector._vectors
    for call in (lambda: workspace.store.append_turn(owner, thread, "晚到", "公开合成结果"),
                 lambda: workspace.memory_service.get_current_confirmed_profile(subject),
                 lambda: settings.valid(owner, ConsentCategory.AI_CHAT, "public_cleanup_v1"),
                 lambda: workspace.checkpointer.get_tuple({"configurable": {"thread_id": workspace.controller.workflow_id}})):
        with pytest.raises(StorageClosedError): call()
    monkeypatch.setattr(failed, "clear", original)
    workspace.close()
    assert bundle._cleanup_complete and workspace._closed
    assert not bundle._database.profiles and not bundle._database.current and not bundle._database.records
    assert not bundle._raw_conversations._messages and not bundle._raw_conversations._snapshots
    assert not bundle._vector._entries and not bundle._vector._vectors
    assert not settings._consent and not settings._receipts and not settings._requests
    assert not workspace.chat.messages


def test_sqlite_scoped_consent_failure_preserves_previous_grant(tmp_path):
    owner = str(uuid4())
    with Workspace(owner, storage_adapters=sqlite_storage(owner, tmp_path)) as workspace:
        settings = workspace.settings_store
        settings.set(owner, ConsentCategory.AI_CHAT, "v1", granted=True, request_scope="public_scope")
        db = settings._scoped()
        try:
            with db:
                db.execute("CREATE TRIGGER reject_delete BEFORE DELETE ON scoped_consent BEGIN SELECT RAISE(ABORT, 'Synthetic failure'); END")
        finally:
            db.close()
        with pytest.raises(sqlite3.IntegrityError):
            settings.set(owner, ConsentCategory.AI_CHAT, "v2", granted=True)
        assert settings.valid(owner, ConsentCategory.AI_CHAT, "v1", request_scope="public_scope")
        assert not settings.valid(owner, ConsentCategory.AI_CHAT, "v2")
        with pytest.raises(sqlite3.IntegrityError): settings.revoke(owner, ConsentCategory.AI_CHAT)
        assert settings.valid(owner, ConsentCategory.AI_CHAT, "v1", request_scope="public_scope")


@pytest.mark.parametrize("ephemeral", (False, True))
def test_owner_canonical_form_and_storage_mode_do_not_define_identity(tmp_path, ephemeral):
    from ui.chat_runtime import WorkspaceMode
    owner = str(uuid4())
    factory = ephemeral_storage if ephemeral else lambda o: sqlite_storage(o, tmp_path)
    with pytest.raises(ValueError): factory(owner.upper())
    assert not list(tmp_path.iterdir())
    adapters = ephemeral_storage(owner) if ephemeral else sqlite_storage(owner, tmp_path)
    with Workspace(owner, mode=WorkspaceMode.PUBLIC_SYNTHETIC_DEMO, storage_adapters=adapters) as workspace:
        assert workspace.owner_scope_id == owner
        assert workspace.runtime_mode == WorkspaceMode.PUBLIC_SYNTHETIC_DEMO
        workspace.settings_store.set(workspace.owner_scope_id, ConsentCategory.AI_CHAT, "v1", granted=True)
        assert workspace.settings_store.valid(workspace.owner_scope_id, ConsentCategory.AI_CHAT, "v1")
