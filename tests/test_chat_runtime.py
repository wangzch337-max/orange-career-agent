"""Offline persistent chat/workflow compatibility using isolated synthetic stores."""

from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from memory.errors import InvalidMemoryTransitionError
from memory.models import StructuredSessionSignal
from ui.chat_runtime import DEFAULT_CHAT_ROOT, PersistentChatWorkspace, Workspace, flatten_payload
from ui.conversation import ConversationStage
from ui.conversation_shell import CONFIRM, INITIAL_SUGGESTIONS, REVISE
from ui.conversation_store import ConversationNotFoundError, ConversationStoreError
from workflows.langgraph_state import GraphWorkflowStatus


@pytest.fixture
def owner():
    return str(uuid4())


@pytest.fixture
def workspace(tmp_path, owner):
    value = Workspace(owner, tmp_path / "chat")
    yield value
    value.close()


def reach_review(workspace):
    for choice in (
        INITIAL_SUGGESTIONS[2], "把一个想法真正做成系统", "把多个 API / 模块连起来",
        "用现有 AI / LLM 做真正的应用", "Campus Helper Prototype",
        "Python、API integration", "大部分时间亲手实现东西", "做出真正可使用的产品",
    ):
        workspace.submit(choice)
    assert workspace.controller.state["workflow_status"] == GraphWorkflowStatus.WAITING_FOR_HUMAN.value


def provider_counts(workspace):
    dependencies = workspace.controller.dependencies
    return tuple(agent.llm_provider.call_count for agent in (
        dependencies.self_discovery_agent, dependencies.job_intelligence_agent,
        dependencies.match_insight_agent,
    ))


def test_empty_workspace_creates_real_scoped_thread_without_domain_execution(workspace, owner):
    assert isinstance(workspace, PersistentChatWorkspace)
    assert workspace.thread.owner_scope_id == owner
    assert len(workspace.threads) == 1 and not workspace.chat.messages
    assert workspace.controller.state is None and provider_counts(workspace) == (0, 0, 0)
    assert workspace.controller.conversation.stage == ConversationStage.CAREER_QUESTION
    assert workspace.memory_service.profile_store.list_profile_history(workspace.subject_id) == []
    assert not workspace.memory_service.memory_store.list_active(workspace.subject_id)


def test_runtime_resources_are_separate_and_owner_scoped(workspace, owner):
    runtime = workspace.root / "runtime" / UUID(owner).hex
    assert workspace.runtime_root == runtime
    assert workspace.memory_service.database.path == runtime / "memory.sqlite3"
    assert workspace.memory_service.vector_index.path == runtime / "vectors.sqlite3"
    assert (runtime / "checkpoints.sqlite3").is_file()
    assert workspace.store.path == workspace.root / "conversations.sqlite3"
    assert DEFAULT_CHAT_ROOT.parts[-3:] == ("data", "local", "chat")


def test_submit_persists_user_reply_and_turn_suggestions(workspace):
    workspace.submit(INITIAL_SUGGESTIONS[0], source="suggestion")
    persisted = workspace.store.list_messages(workspace.owner_scope_id, workspace.thread.thread_id)
    assert len(persisted) == 2
    assert persisted[0].content == INITIAL_SUGGESTIONS[0]
    assert persisted[0].metadata == {"source": "suggestion"}
    assert persisted[1].metadata["suggestions"] == list(workspace.chat.messages[-1].suggestions)
    assert persisted[1].metadata["kind"] == "text"
    assert workspace.thread.title == INITIAL_SUGGESTIONS[0]


def test_refresh_resumes_guided_state_and_messages_without_replaying(workspace, monkeypatch):
    workspace.submit(INITIAL_SUGGESTIONS[2])
    workspace.submit("分析数据、找规律")
    before_chat, before_thread = asdict(workspace.chat), workspace.thread
    root, owner = workspace.root, workspace.owner_scope_id
    workspace.close()
    # Guided state is restored directly; reopening must not submit prior answers.
    def reject_replay(*_args, **_kwargs):
        raise AssertionError("Historical answer replay is forbidden.")
    monkeypatch.setattr("ui.demo_controller.DemoController.submit_conversation_answer", reject_replay)
    with Workspace(owner, root) as restored:
        assert asdict(restored.chat) == before_chat
        assert restored.thread == before_thread
        assert restored.controller.conversation.stage == ConversationStage.AI_INTEREST
        assert provider_counts(restored) == (0, 0, 0)


def test_guided_pending_note_survives_refresh_without_becoming_canonical_memory(workspace):
    workspace.submit("本轮想先聊聊合成项目")
    before = workspace.memory_service.memory_store.list_history(workspace.subject_id)
    with Workspace(workspace.owner_scope_id, workspace.root) as refreshed:
        assert refreshed.chat.pending_note == "本轮想先聊聊合成项目"
        assert refreshed.controller.conversation.stage == ConversationStage.CAREER_QUESTION
        assert refreshed.memory_service.memory_store.list_history(refreshed.subject_id) == before


def test_new_chat_persists_old_transcript_and_creates_genuine_identity(workspace):
    workspace.submit(INITIAL_SUGGESTIONS[0])
    previous, previous_workflow = workspace.thread, workspace.controller.workflow_id
    previous_messages = workspace.store.list_messages(workspace.owner_scope_id, previous.thread_id)
    current = workspace.create_new_thread()
    assert current.thread_id != previous.thread_id
    assert workspace.controller.workflow_id != previous_workflow
    assert not workspace.chat.messages and workspace.controller.state is None
    assert {thread.thread_id for thread in workspace.threads} == {current.thread_id, previous.thread_id}
    assert workspace.store.list_messages(workspace.owner_scope_id, previous.thread_id) == previous_messages


def test_historical_selection_is_read_only_and_restores_correct_transcript(workspace):
    workspace.submit(INITIAL_SUGGESTIONS[0])
    first, messages = workspace.thread, asdict(workspace.chat)
    second = workspace.create_new_thread()
    workspace.submit(INITIAL_SUGGESTIONS[3])
    workspace.activate(first.thread_id)
    assert workspace.thread == first and asdict(workspace.chat) == messages
    assert provider_counts(workspace) == (0, 0, 0)
    assert workspace.store.get_thread(workspace.owner_scope_id, second.thread_id).thread_id == second.thread_id


def test_rename_does_not_change_messages_workflow_or_canonical_records(workspace):
    workspace.submit(INITIAL_SUGGESTIONS[0])
    transcript = workspace.store.list_messages(workspace.owner_scope_id, workspace.thread.thread_id)
    workflow, events = workspace.controller.workflow_id, list(workspace.memory_service.events)
    renamed = workspace.rename(workspace.thread.thread_id, "  我自己的对话标题  ")
    assert workspace.thread == renamed and renamed.title == "我自己的对话标题"
    assert workspace.controller.workflow_id == workflow
    assert workspace.memory_service.events == events
    assert workspace.store.list_messages(workspace.owner_scope_id, renamed.thread_id) == transcript


def test_profile_review_is_persisted_as_visible_text_not_domain_payload(workspace):
    reach_review(workspace)
    last = workspace.store.list_messages(workspace.owner_scope_id, workspace.thread.thread_id)[-1]
    assert "职业画像" in last.content and "已有证据的能力" in last.content
    assert "待确认" in last.content
    assert last.metadata["kind"] == "profile"
    assert "profile" not in last.metadata
    assert workspace.chat.messages[-1].structured_payload is None
    assert CONFIRM in workspace.chat.messages[-1].suggestions
    assert workspace.thread.profile_id_ref is None


def test_waiting_profile_checkpoint_restores_without_discovery_and_confirms(workspace):
    reach_review(workspace)
    thread, created = workspace.thread, workspace.controller.state["profile"]["created_at"]
    workspace.close()
    with Workspace(workspace.owner_scope_id, workspace.root) as restored:
        assert restored.thread == thread
        assert restored.controller.state["workflow_status"] == "waiting_for_human"
        assert restored.controller.state["profile"]["created_at"] == created
        assert provider_counts(restored) == (0, 0, 0)
        assert restored.controller.profile_review_payload()["kind"] == "profile_review"
        restored.submit(CONFIRM)
        assert restored.controller.state["workflow_status"] == "completed"
        assert restored.controller.dependencies.self_discovery_agent.llm_provider.call_count == 0


def test_new_chat_reuses_exact_confirmed_profile_without_reconfirmation_or_conflict(workspace):
    reach_review(workspace)
    workspace.submit(CONFIRM)
    confirmed = workspace.memory_service.get_current_confirmed_profile(workspace.subject_id)
    before_profile = confirmed.model_dump(mode="json")
    before_memory = workspace.memory_service.memory_store.list_history(workspace.subject_id)
    original = workspace.thread
    new = workspace.create_new_thread()
    assert new.profile_id_ref == confirmed.profile_id and new.profile_version_ref == confirmed.version
    assert workspace.controller.state is None and provider_counts(workspace) == (0, 0, 0)
    workspace.submit(INITIAL_SUGGESTIONS[1])
    assert workspace.controller.state["workflow_status"] == "completed"
    assert workspace.controller.state["self_discovery_call_count"] == 0
    assert workspace.controller.state["profile"] == before_profile
    assert CONFIRM not in workspace.chat.messages[-1].suggestions
    assert workspace.memory_service.get_current_confirmed_profile(workspace.subject_id).model_dump(mode="json") == before_profile
    assert workspace.memory_service.memory_store.list_history(workspace.subject_id) == before_memory
    assert len(workspace.memory_service.profile_store.list_profile_history(workspace.subject_id)) == 1
    assert original.thread_id != workspace.thread.thread_id


def test_completed_thread_restart_preserves_exact_pinned_profile_and_selection(workspace):
    reach_review(workspace)
    workspace.submit(CONFIRM)
    workspace.submit("Data Analyst")
    before_chat, before_state = asdict(workspace.chat), workspace.controller.state
    workspace.close()
    with Workspace(workspace.owner_scope_id, workspace.root) as restored:
        assert asdict(restored.chat) == before_chat
        assert restored.controller.state["profile"] == before_state["profile"]
        assert restored.chat.selected_role == "job_013"
        assert provider_counts(restored) == (0, 0, 0)
        restored.submit("看证据关系")
        assert "总体分数" in restored.chat.messages[-1].content
        assert restored.controller.dependencies.self_discovery_agent.llm_provider.call_count == 0


def test_existing_refinement_requires_new_draft_version_and_explicit_confirmation(workspace):
    reach_review(workspace)
    workspace.submit(CONFIRM)
    original_thread = workspace.thread
    canonical = workspace.memory_service.get_current_confirmed_profile(workspace.subject_id)
    original = canonical.model_dump(mode="json")
    workspace.create_new_thread()
    workspace.submit(INITIAL_SUGGESTIONS[1])
    refinement = workspace.controller.profile_refinement_service
    signal = StructuredSessionSignal(
        signal_id="session_signal_synthetic", dimension="work_preference",
        value="system_building", display_label="希望更多亲手构建可运行系统",
        source="explicit_user_input", session_order=1,
    )
    result = refinement.refine(subject_id=workspace.subject_id, current_input=signal)
    assert not result.draft_profile.confirmed
    assert result.draft_profile.profile_id == canonical.profile_id
    assert result.draft_profile.version == canonical.version + 1
    assert workspace.memory_service.get_current_confirmed_profile(workspace.subject_id).model_dump(mode="json") == original
    assert len(workspace.memory_service.profile_store.list_profile_history(workspace.subject_id)) == 1
    with pytest.raises(InvalidMemoryTransitionError):
        refinement.confirm(workspace.subject_id, result, confirmed_by_user=False)
    updated = refinement.confirm(workspace.subject_id, result, confirmed_by_user=True)
    assert updated.confirmed and updated.version == canonical.version + 1
    assert workspace.memory_service.get_current_confirmed_profile(workspace.subject_id) == updated
    assert workspace.memory_service.profile_store.get_profile_version(workspace.subject_id, canonical.profile_id, canonical.version).model_dump(mode="json") == original
    # An older conversation continues referencing the immutable v1 checkpoint;
    # it never adopts a newer canonical pointer just because history is opened.
    workspace.activate(original_thread.thread_id)
    assert workspace.controller.state["profile"] == original
    assert workspace.thread.profile_version_ref == canonical.version
    next_thread = workspace.create_new_thread()
    assert next_thread.profile_id_ref == updated.profile_id
    assert next_thread.profile_version_ref == updated.version


def test_transcript_profile_summary_is_not_canonical_source(workspace):
    reach_review(workspace)
    workspace.submit(CONFIRM)
    canonical = workspace.memory_service.get_current_confirmed_profile(workspace.subject_id)
    canonical_payload = canonical.model_dump(mode="json")
    messages = workspace.store.list_messages(workspace.owner_scope_id, workspace.thread.thread_id)
    assert any(message.metadata.get("kind") == "profile" for message in messages)
    workspace.chat.messages.clear()
    workspace.chat.pending_note = "普通聊天补充不改变画像"
    assert workspace.memory_service.get_current_confirmed_profile(workspace.subject_id).model_dump(mode="json") == canonical_payload
    workspace.create_new_thread()
    workspace.submit(INITIAL_SUGGESTIONS[1])
    assert workspace.controller.state["profile"] == canonical_payload
    assert workspace.controller.state["current_profile_ref"]["version"] == canonical.version


def test_revising_profile_review_ui_state_survives_reload(workspace):
    reach_review(workspace)
    workspace.submit(REVISE)
    with Workspace(workspace.owner_scope_id, workspace.root) as refreshed:
        assert refreshed.chat.revising
        refreshed.submit("公开合成的教育背景摘要")
        assert not refreshed.chat.revising
        assert refreshed.controller.state["workflow_status"] == "waiting_for_human"


def test_other_browser_has_separate_conversation_memory_and_checkpoint_scope(workspace):
    workspace.submit(INITIAL_SUGGESTIONS[0])
    with Workspace(str(uuid4()), workspace.root) as other:
        assert other.subject_id != workspace.subject_id
        assert other.runtime_root != workspace.runtime_root
        assert other.threads == (other.thread,) and not other.chat.messages
        with pytest.raises(ConversationNotFoundError):
            other.activate(workspace.thread.thread_id)
        assert other.memory_service.profile_store.list_profile_history(other.subject_id) == []


def test_credential_input_is_rejected_before_controller_or_storage(workspace):
    value = "sk-" + "A1b2C3d4" * 5
    before = workspace.thread
    with pytest.raises(ConversationStoreError):
        workspace.submit(value)
    assert workspace.thread == before and not workspace.chat.messages
    assert provider_counts(workspace) == (0, 0, 0)
    assert workspace.store.list_messages(workspace.owner_scope_id, workspace.thread.thread_id) == ()


def test_close_preserves_files_and_is_idempotent(workspace):
    workspace.submit(INITIAL_SUGGESTIONS[0])
    files = tuple(workspace.root.rglob("*.sqlite3"))
    thread = workspace.thread
    workspace.close()
    workspace.close()
    assert files and all(path.is_file() for path in files)
    with pytest.raises(ConversationStoreError):
        workspace.create_new_thread()
    with Workspace(workspace.owner_scope_id, workspace.root) as restarted:
        assert restarted.thread == thread
        assert len(restarted.chat.messages) == 2


@pytest.mark.parametrize("kind", ["directions", "match", "actions", "memory"])
def test_flattening_projects_only_visible_fields_not_whole_objects(kind):
    secret_hidden = "NOT_A_VISIBLE_FIELD"
    card = SimpleNamespace(title="合成岗位", one_line="岗位摘要", why_explore="探索理由", validated_overlaps=("已有交集",), clarification_need="待澄清", hidden=secret_hidden)
    insight = SimpleNamespace(title="合成关系", description="证据关系描述", hidden=secret_hidden)
    group = SimpleNamespace(label="已有交集", explanation="类别解释", insights=(insight,), hidden=secret_hidden)
    action = SimpleNamespace(description="合成行动", target_label="精确目标", expected_evidence="预期证据", hidden=secret_hidden)
    view = SimpleNamespace(confirmed_capabilities=("Python",), work_preferences=("工作偏好",), current_goals=("当前目标",), user_feedback=("已确认反馈",), hidden=secret_hidden)
    payloads = {"directions": {"cards": (card,)}, "match": {"groups": (group,)}, "actions": {"actions": (action,)}, "memory": {"view": view}}
    rendered = flatten_payload({"kind": kind, **payloads[kind]})
    assert rendered and secret_hidden not in rendered and "SimpleNamespace" not in rendered


def test_unknown_structured_payload_cannot_be_serialized():
    with pytest.raises(ConversationStoreError):
        flatten_payload({"kind": "raw_provider_completion", "content": "forbidden"})


def test_inactive_delete_preserves_current_controller_chat_and_guided_state(workspace):
    workspace.submit(INITIAL_SUGGESTIONS[0])
    inactive = workspace.thread
    workspace.create_new_thread()
    workspace.submit("当前对话的合成备注")
    controller, chat, thread = workspace.controller, workspace.chat, workspace.thread
    before, counts = asdict(chat), provider_counts(workspace)
    workspace.delete_thread(inactive.thread_id)
    assert workspace.controller is controller and workspace.chat is chat and workspace.thread is thread
    assert asdict(workspace.chat) == before and provider_counts(workspace) == counts


def test_active_delete_selects_most_recent_updated_not_oldest_or_created(workspace):
    first = workspace.thread
    second = workspace.create_new_thread()
    workspace.submit("B 的合成消息")
    third = workspace.create_new_thread()
    workspace.submit("C 的合成消息")
    workspace.rename(first.thread_id, "A 最近更新")
    workspace.delete_thread(third.thread_id)
    assert workspace.thread.thread_id == first.thread_id
    assert {thread.thread_id for thread in workspace.threads} == {first.thread_id, second.thread_id}
    assert not workspace.chat.messages


def test_only_thread_delete_creates_empty_new_identity_and_new_chat_still_works(workspace):
    workspace.submit(INITIAL_SUGGESTIONS[0])
    deleted, workflow = workspace.thread, workspace.controller.workflow_id
    workspace.delete_thread(deleted.thread_id)
    assert len(workspace.threads) == 1 and workspace.thread.thread_id != deleted.thread_id
    assert workspace.controller.workflow_id != workflow
    assert not workspace.chat.messages and workspace.controller.state is None
    assert not workspace.chat.pending_note and not workspace.chat.revising
    assert workspace.chat.selected_role is None
    assert provider_counts(workspace) == (0, 0, 0)
    created = workspace.create_new_thread()
    workspace.submit(INITIAL_SUGGESTIONS[1])
    assert workspace.thread.thread_id == created.thread_id and len(workspace.chat.messages) == 2


def test_delete_all_conversations_preserves_canonical_profile_versions_memory_and_evidence(workspace):
    reach_review(workspace)
    workspace.submit(CONFIRM)
    workspace.controller._seed_public_memory_scenario()  # Explicit synthetic test data, not automatic UI seeding.
    signal = StructuredSessionSignal(signal_id="session_signal_hotfix_synthetic", dimension="work_preference",
        value="system_building", display_label="希望更多亲手构建系统", source="explicit_user_input", session_order=1)
    refinement = workspace.controller.profile_refinement_service
    result = refinement.refine(subject_id=workspace.subject_id, current_input=signal)
    refinement.confirm(workspace.subject_id, result, confirmed_by_user=True)
    canonical = workspace.memory_service.get_current_confirmed_profile(workspace.subject_id).model_dump(mode="json")
    versions = workspace.memory_service.profile_store.list_profile_history(workspace.subject_id)
    assert len(versions) == 2
    memories = workspace.memory_service.memory_store.list_history(workspace.subject_id)
    assert memories
    authoritative_bytes = workspace.memory_service.database.path.read_bytes()
    vector_bytes = workspace.memory_service.vector_index.path.read_bytes()
    subject = workspace.subject_id
    workspace.create_new_thread()
    for thread in tuple(workspace.threads):
        workspace.delete_thread(thread.thread_id)
    assert len(workspace.threads) == 1 and not workspace.chat.messages
    assert workspace.subject_id == subject
    assert workspace.memory_service.get_current_confirmed_profile(subject).model_dump(mode="json") == canonical
    assert workspace.memory_service.profile_store.list_profile_history(subject) == versions
    assert workspace.memory_service.memory_store.list_history(subject) == memories
    assert workspace.memory_service.database.path.read_bytes() == authoritative_bytes
    assert workspace.memory_service.vector_index.path.read_bytes() == vector_bytes
    # Same canonical version, no discovery, duplicate confirmation or history write.
    workspace.submit(INITIAL_SUGGESTIONS[1])
    assert workspace.controller.state["profile"] == canonical
    assert workspace.controller.state["self_discovery_call_count"] == 0
    assert workspace.memory_service.profile_store.list_profile_history(subject) == versions
    assert workspace.memory_service.memory_store.list_history(subject) == memories


def test_delete_survives_workspace_restart_and_rename_of_survivor(workspace):
    workspace.submit("A 合成消息")
    survivor = workspace.thread
    workspace.create_new_thread()
    workspace.submit("B 合成消息")
    deleted = workspace.thread
    workspace.delete_thread(deleted.thread_id)
    workspace.rename(survivor.thread_id, "保留 A")
    before = asdict(workspace.chat)
    workspace.close()
    with Workspace(workspace.owner_scope_id, workspace.root) as restarted:
        assert restarted.thread.title == "保留 A" and asdict(restarted.chat) == before
        assert deleted.thread_id not in {thread.thread_id for thread in restarted.threads}
        with pytest.raises(ConversationNotFoundError):
            restarted.activate(deleted.thread_id)
        assert provider_counts(restarted) == (0, 0, 0)


def test_delete_cleans_only_exclusive_workflow_via_installed_public_api(workspace):
    reach_review(workspace)
    deleted = workspace.thread
    config = {"configurable": {"thread_id": deleted.workflow_thread_id}}
    assert workspace.checkpointer.get_tuple(config) is not None
    workspace.create_new_thread()
    reach_review(workspace)
    survivor, current_controller = workspace.thread, workspace.controller
    survivor_config = {"configurable": {"thread_id": survivor.workflow_thread_id}}
    before = workspace.checkpointer.get_tuple(survivor_config)
    workspace.delete_thread(deleted.thread_id)
    assert workspace.last_checkpoint_cleanup == "deleted"
    assert workspace.checkpointer.get_tuple(config) is None
    assert list(workspace.checkpointer.list(config)) == []
    with workspace.checkpointer.cursor(transaction=False) as cur:
        assert cur.execute("SELECT count(*) FROM writes WHERE thread_id = ?", (deleted.workflow_thread_id,)).fetchone()[0] == 0
    assert workspace.checkpointer.get_tuple(survivor_config) == before
    assert workspace.controller is current_controller


def test_shared_checkpoint_is_preserved(workspace, monkeypatch):
    original = workspace.thread
    sibling = workspace.create_new_thread()
    workspace.store.save_snapshot(workspace.owner_scope_id, sibling.thread_id, {},
                                  workflow_thread_id=original.workflow_thread_id)
    monkeypatch.setattr(workspace.checkpointer, "delete_thread", lambda _id: pytest.fail("shared checkpoint deleted"))
    workspace.delete_thread(original.thread_id)
    assert workspace.last_checkpoint_cleanup == "shared_preserved"


def test_cleanup_failure_leaves_unreachable_checkpoint_not_half_deleted_chat(workspace, monkeypatch):
    reach_review(workspace)
    deleted = workspace.thread
    config = {"configurable": {"thread_id": deleted.workflow_thread_id}}
    def fail(_id):
        raise RuntimeError("synthetic cleanup failure")
    monkeypatch.setattr(workspace.checkpointer, "delete_thread", fail)
    workspace.delete_thread(deleted.thread_id)
    assert workspace.last_checkpoint_cleanup == "pending"
    assert workspace.checkpointer.get_tuple(config) is not None
    assert deleted.thread_id not in {thread.thread_id for thread in workspace.threads}
    assert not workspace.chat.messages
    with pytest.raises(ConversationNotFoundError):
        workspace.activate(deleted.thread_id)


def test_delete_rejects_other_owner_without_current_mutation(workspace):
    with Workspace(str(uuid4()), workspace.root) as other:
        other.submit("其他客户端的合成消息")
        before = asdict(other.chat)
        controller, chat = workspace.controller, workspace.chat
        with pytest.raises(ConversationNotFoundError):
            workspace.delete_thread(other.thread.thread_id)
        assert asdict(other.chat) == before
        assert workspace.controller is controller and workspace.chat is chat


def test_failed_store_delete_preserves_active_runtime(workspace, monkeypatch):
    controller, chat, thread = workspace.controller, workspace.chat, workspace.thread
    def fail(*_args):
        raise ConversationStoreError("synthetic transaction failure")
    monkeypatch.setattr(workspace.store, "delete_thread", fail)
    with pytest.raises(ConversationStoreError):
        workspace.delete_thread(thread.thread_id)
    assert workspace.controller is controller and workspace.chat is chat and workspace.thread is thread
    assert workspace.last_checkpoint_cleanup == "not_requested"


def test_closed_workspace_rejects_delete_without_persistent_mutation(workspace):
    thread = workspace.thread
    workspace.close()
    with pytest.raises(ConversationStoreError):
        workspace.delete_thread(thread.thread_id)
    assert workspace.store.get_thread(workspace.owner_scope_id, thread.thread_id) == thread
